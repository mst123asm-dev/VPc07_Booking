"""Автономный драйвер для работы с СУБД PostgreSQL.

Модуль представляет собой независимую, переносимую библиотеку (драйвер),
которую можно без изменений использовать в любых сторонних проектах:
веб-приложениях, CRM-системах, аналитических скриптах и т.д.

Драйвер полностью абстрагирован от бизнес-логики приложения:
он не содержит знаний о конкретных таблицах, пользователях, заказах
и иных предметных сущностях.

Зависимости:
    psycopg2-binary

Пример минимального использования:

    driver = PostgresDriver(dsn="postgresql://user:pass@localhost:5432/dbname")
        rows = driver.fetch_all(
        "SELECT id, name FROM articles WHERE status = %s",
        ("active",),
    )
    driver.close()
"""

import logging
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

QueryParams = Sequence[Any] | Mapping[str, Any] | None


class PostgresDriver:
    """Универсальный драйвер PostgreSQL на основе пула соединений.

    Класс инкапсулирует работу с пулом потокобезопасных соединений
    ``psycopg2.pool.ThreadedConnectionPool`` и предоставляет минимальный,
    достаточный интерфейс для выполнения SQL-запросов.

    Все курсоры пула автоматически используют
    ``psycopg2.extras.RealDictCursor``, поэтому результаты чтения возвращаются
    строго в виде словарей Python с реальными названиями колонок из СУБД.

    Драйвер не вызывает ``load_dotenv()`` и не читает конфигурацию сам:
    строка подключения (DSN) всегда передаётся снаружи в конструктор.

    Attributes:
        _pool: Пул потокобезопасных соединений с СУБД.
    """

    def __init__(
        self,
        dsn: str,
        min_conn: int = 1,
        max_conn: int = 10,
    ) -> None:
        """Инициализировать драйвер и создать пул соединений.

        Пул создаётся ровно один раз — при создании экземпляра класса
        и далее переиспользуется всеми методами.

        Args:
            dsn: Строка подключения в формате DSN (URL), например
                ``postgresql://user:password@host:5432/dbname``.
            min_conn: Минимальное количество соединений в пуле.
            max_conn: Максимальное количество соединений в пуле.

        Raises:
            ValueError: Если DSN пуст или имеет неверный тип.
            psycopg2.Error: Если пул не удалось создать
                (недоступен сервер, неверные учётные данные и т.п.).
        """
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("DSN строка подключения не может быть пустой")
        if not isinstance(min_conn, int) or isinstance(min_conn, bool):
            raise TypeError("min_conn должен быть целым числом")

        if not isinstance(max_conn, int) or isinstance(max_conn, bool):
            raise TypeError("max_conn должен быть целым числом")

        if min_conn < 0:
            raise ValueError("min_conn не может быть отрицательным")

        if max_conn <= 0:
            raise ValueError("max_conn должен быть больше нуля")

        if min_conn > max_conn:
            raise ValueError("min_conn не может быть больше max_conn")

        self._pool: psycopg2.pool.ThreadedConnectionPool = (
            psycopg2.pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                dsn=dsn,
                # Все курсоры, созданные из соединений этого пула,
                # будут возвращать строки в виде RealDictRow (dict).
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
        )

        self._closed = False
        self._active_connections = 0
        self._pool_lock = threading.Lock()

        logger.info(
            "PostgresDriver: пул соединений создан (min=%d, max=%d)",
            min_conn,
            max_conn,
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg2.extensions.connection]:
        """Выдать соединение из пула и корректно завершить транзакцию.

        При успешном завершении контекста выполняется COMMIT.
        При исключении выполняется ROLLBACK.
        После этого соединение возвращается в пул.

        Если close() был вызван во время активного соединения,
        окончательное закрытие пула откладывается до возврата
        последнего активного соединения.
        """
        with self._pool_lock:
            if self._closed:
                raise RuntimeError("PostgresDriver уже закрыт")

            conn = self._pool.getconn()
            self._active_connections += 1

        primary_error = None

        try:
            yield conn
            conn.commit()
        except Exception as exc:
            primary_error = exc

            try:
                conn.rollback()
            except Exception:
                logger.error(
                    "PostgresDriver: не удалось выполнить rollback "
                    "соединения после ошибки",
                    exc_info=True,
                )
        finally:
            try:
                self._pool.putconn(conn)
            except Exception as putconn_error:
                logger.error(
                    "PostgresDriver: не удалось вернуть соединение "
                    "в пул",
                    exc_info=True,
                )

                try:
                    self._pool.putconn(conn, close=True)
                except Exception:
                    logger.error(
                        "PostgresDriver: не удалось закрыть "
                        "соединение после ошибки возврата в пул",
                        exc_info=True,
                    )

                if primary_error is None:
                    raise putconn_error
            finally:
                with self._pool_lock:
                    self._active_connections -= 1

                    if self._closed and self._active_connections == 0:
                        try:
                            self._pool.closeall()
                        except psycopg2.Error:
                            logger.error(
                                "PostgresDriver: не удалось закрыть пул "
                                "соединений",
                                exc_info=True,
                            )

        if primary_error is not None:
            raise primary_error

    @contextmanager
    def transaction(self) -> Iterator[psycopg2.extensions.connection]:
        """Предоставить соединение для явной транзакции.

        Соединение автоматически возвращается в пул.
        При успешном завершении выполняется COMMIT.
        При исключении выполняется ROLLBACK.

        Yields:
            Активное соединение PostgreSQL для выполнения нескольких
            связанных SQL-команд в рамках одной транзакции.
        """
        with self._connection() as conn:
            yield conn

    def execute_query(self, query: str, params: QueryParams = None) -> bool:
        """Выполнить SQL-команду, не возвращающую строки.

        Подходит для команд ``CREATE``, ``INSERT``, ``UPDATE``, ``DELETE``,
        ``DROP`` и иных управляющих/модифицирующих запросов.

        Успешное выполнение подтверждается транзакцией (COMMIT), при ошибке
        выполняется автоматический откат (ROLLBACK). Исключение логируется
        и повторно поднимается наружу.

        Args:
            query: SQL-команда. Для передаваемых значений используются
                параметризованные плейсхолдеры ``%s``.
            params: Последовательность значений или отображение имён
                параметров для параметризованного запроса либо ``None``.

        Returns:
            ``True`` при успешном выполнении.

        Raises:
            psycopg2.Error: Если выполнение SQL-команды завершилось ошибкой.
        """
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
            return True
        except psycopg2.Error:
            logger.error(
                "PostgresDriver: ошибка выполнения SQL-команды: %s",
                query,
                exc_info=True,
            )
            raise

    def fetch_all(self, query: str, params: QueryParams = None) -> list[dict]:
        """Выполнить SELECT-запрос и вернуть все найденные строки.

        Args:
            query: SQL-запрос ``SELECT``. Для передаваемых значений
                используются параметризованные плейсхолдеры ``%s``.
            params: Последовательность значений или отображение имён
                параметров для параметризованного запроса либо ``None``.

        Returns:
            Список словарей ``list[dict]``, где каждый словарь — строка
            результата, а ключи — реальные названия колонок из СУБД.
            Пустой список ``[]`` возвращается, если строки не найдены.

        Raises:
            psycopg2.Error: Если выполнение SELECT-запроса завершилось
                ошибкой.
        """
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
            # RealDictRow -> чистый dict для предсказуемого типа результата.
            return [dict(row) for row in rows]
        except psycopg2.Error:
            logger.error(
                "PostgresDriver: ошибка выполнения SELECT-запроса: %s",
                query,
                exc_info=True,
            )
            raise

    def fetch_one(self, query: str, params: QueryParams = None) -> dict | None:
        """Выполнить SELECT-запрос и вернуть одну строку.

        Args:
            query: SQL-запрос ``SELECT``. Для передаваемых значений
                используются параметризованные плейсхолдеры ``%s``.
            params: Последовательность значений или отображение имён
                параметров для параметризованного запроса либо ``None``.

        Returns:
            Словарь ``dict`` с реальными названиями колонок из СУБД
            в качестве ключей либо ``None``, если строки не найдены.

        Raises:
            psycopg2.Error: Если выполнение SELECT-запроса завершилось
                ошибкой.
        """
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
            return dict(row) if row is not None else None
        except psycopg2.Error:
            logger.error(
                "PostgresDriver: ошибка выполнения SELECT-запроса: %s",
                query,
                exc_info=True,
            )
            raise

    def close(self) -> None:
        """Закрыть пул соединений после завершения активных операций.

        После вызова этого метода новые соединения не выдаются.
        Уже активные соединения завершают текущие операции,
        после чего пул закрывается окончательно.
        """
        with self._pool_lock:
            if self._closed:
                return

            if self._active_connections == 0:
                self._pool.closeall()
                self._closed = True
                logger.info("PostgresDriver: все соединения в пуле закрыты")
                return

            self._closed = True
