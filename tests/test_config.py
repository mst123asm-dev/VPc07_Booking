"""Конфигурация и безопасная инфраструктура для интеграционных тестов.

Загружает .env, формирует DSN и предоставляет функцию создания
PostgresDriver с защитой от запуска на production-базе данных.

Важно:
- Не подключается к БД автоматически при импорте.
- Подключение происходит только через явный вызов create_test_driver().
- Тестовый драйвер подключается к TEST_DB_NAME, а не к DB_NAME.
- create_test_driver() запрещён, если TEST_DB_NAME не задана,
  не оканчивается на '_test' или совпадает с рабочей базой
  (DB_NAME / fallback POSTGRES_DB).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from postgres_driver import PostgresDriver


class TestConfigError(RuntimeError):
    """Ошибка конфигурации тестовой среды."""


# ---------------------------------------------------------------------------
# Загрузка .env (без подключения к БД)
# ---------------------------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------------------------
# Формирование DSN
# ---------------------------------------------------------------------------

def _working_db_name() -> str:
    """Имя рабочей базы, реально используемое конфигурацией приложения.

    Семантика совпадает с приложением: приоритет у DB_NAME,
    затем fallback POSTGRES_DB.
    """
    return os.getenv("DB_NAME") or os.getenv("POSTGRES_DB") or ""


def _test_db_name() -> str:
    """Имя тестовой базы из TEST_DB_NAME."""
    return os.getenv("TEST_DB_NAME") or ""


def _build_dsn() -> str:
    """Собрать DSN тестового подключения из переменных окружения.

    Формат DSN совпадает с остальным проектом:
    host=... port=... dbname=... user=... password=...

    В качестве dbname используется TEST_DB_NAME, а не DB_NAME,
    чтобы тестовый драйвер не мог подключиться к рабочей базе.
    Поддерживаются альтернативные имена переменных (POSTGRES_*)
    для обратной совместимости с существующим кодом проекта.
    """
    host = os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST") or "localhost"
    port = os.getenv("DB_PORT") or os.getenv("POSTGRES_PORT") or "5432"
    dbname = _test_db_name()
    user = os.getenv("DB_USER") or os.getenv("POSTGRES_USER") or ""
    password = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD") or ""

    return (
        f"host={host} "
        f"port={port} "
        f"dbname={dbname} "
        f"user={user} "
        f"password={password}"
    )


# ---------------------------------------------------------------------------
# Safety guard: проверка TEST_DB_NAME
# ---------------------------------------------------------------------------

def _assert_test_db_allowed() -> None:
    """Проверить, что тесты разрешены на текущей тестовой базе.

    Правила (все проверки — до создания PostgresDriver):
    1. TEST_DB_NAME задана и не пуста.
    2. TEST_DB_NAME оканчивается на '_test'.
    3. TEST_DB_NAME отличается от рабочего имени базы
       (DB_NAME / fallback POSTGRES_DB).

    Не подключается к БД, читает только переменные окружения.
    """
    db_name = _working_db_name()
    test_db_name = _test_db_name()

    if not test_db_name:
        raise TestConfigError(
            "TEST_DB_NAME не задана. "
            "Установите TEST_DB_NAME в .env, чтобы разрешить "
            "запуск интеграционных тестов."
        )

    if not test_db_name.endswith("_test"):
        raise TestConfigError(
            f"TEST_DB_NAME ({test_db_name!r}) не оканчивается на '_test'. "
            "Интеграционные тесты разрешены только на отдельной тестовой "
            "базе с суффиксом '_test'."
        )

    if test_db_name == db_name:
        raise TestConfigError(
            f"TEST_DB_NAME ({test_db_name!r}) совпадает с рабочей базой "
            f"DB_NAME ({db_name!r}). Интеграционные тесты запрещены на "
            "рабочей базе. Укажите отдельную тестовую базу в TEST_DB_NAME."
        )


# ---------------------------------------------------------------------------
# Создание драйвера
# ---------------------------------------------------------------------------

def create_test_driver() -> PostgresDriver:
    """Создать PostgresDriver для интеграционных тестов.

    Вызов запрещён, если safety guard не пройден (см. _assert_test_db_allowed).
    При успешном создании:
        min_conn=1, max_conn=3
    Подключение к БД происходит только при вызове этой функции.
    При импорте модуля подключение не выполняется.

    Возвращает:
        PostgresDriver с указанными параметрами пула.

    Исключения:
        TestConfigError: если TEST_DB_NAME не задана, не оканчивается на
            '_test' или совпадает с рабочей базой (DB_NAME / POSTGRES_DB).
        psycopg2.Error: если сервер PostgreSQL недоступен или учётные данные неверны.
    """
    _assert_test_db_allowed()
    return PostgresDriver(
        dsn=_build_dsn(),
        min_conn=1,
        max_conn=3,
    )
