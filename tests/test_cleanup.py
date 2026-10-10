"""Инфраструктура очистки тестовых данных.

Предназначена для удаления объектов, явно созданных конкретным тестом.

Правила:
- Работает ТОЛЬКО с объектами, созданными тестом (явные ID).
- НЕ делает DELETE FROM table, get_all_* и массового удаления.
- Учитывает порядок FK-зависимостей: bookings → tables → users.
- Ошибки при удалении одного объекта не прерывают удаление остальных.
- Все ошибки собираются в список и возвращаются вызывающему коду.
- Использует явные SQL-запросы через driver.execute() с параметризацией.

Вспомогательные функции для удаления объектов по ID и класс для сбора ошибок.

Пример использования:
    from tests.test_cleanup import delete_bookings_by_ids, delete_tables_by_ids, delete_users_by_ids

    errors: list[Exception] = []
    delete_bookings_by_ids(driver, [1, 2, 3], errors)
    delete_tables_by_ids(driver, [10, 11], errors)
    delete_users_by_ids(driver, [100, 101], errors)
    if errors:
        raise ExceptionGroup("Ошибки при очистке", errors)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from postgres_driver import PostgresDriver


# ---------------------------------------------------------------------------
# Внутренний хелпер
# ---------------------------------------------------------------------------

def _delete_by_ids(
    driver: PostgresDriver,
    table: str,
    ids: list[int],
    errors: list[Exception],
) -> None:
    """Удалить записи из таблицы по списку ID.

    Использует параметризованный SQL через driver.execute().
    При ошибке удаления одной записи добавляет исключение в errors
    и продолжает обработку остальных ID.

    Args:
        driver: Экземпляр PostgresDriver.
        table: Имя таблицы.
        ids: Список ID для удаления.
        errors: Список для сбора ошибок (изменяется на месте).
    """
    for obj_id in ids:
        try:
            # Таблица подставляется как литерал (без user input), ID — как параметр
            driver.execute_query(
                f"DELETE FROM {table} WHERE id = %s",
                (obj_id,),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                RuntimeError(
                    f"Ошибка удаления id={obj_id} из {table}: {exc}"
                )
            )


# ---------------------------------------------------------------------------
# Публичные функции удаления (по порядку FK-зависимостей)
# ---------------------------------------------------------------------------

def delete_bookings_by_ids(
    driver: PostgresDriver,
    ids: list[int],
    errors: list[Exception],
) -> None:
    """Удалить записи бронирований по списку ID.

    Вызывать ПЕРВЫМ — bookings зависят от tables и users.
    Ошибки добавляются в errors, удаление продолжается для остальных ID.

    Args:
        driver: Экземпляр PostgresDriver.
        ids: Явный список ID бронирований, созданных тестом.
        errors: Список для сбора ошибок (изменяется на месте).
    """
    _delete_by_ids(driver, "bookings", ids, errors)


def delete_tables_by_ids(
    driver: PostgresDriver,
    ids: list[int],
    errors: list[Exception],
) -> None:
    """Удалить записи столиков по списку ID.

    Вызывать ВТОРЫМ — tables не зависят от bookings.
    Ошибки добавляются в errors, удаление продолжается для остальных ID.

    Args:
        driver: Экземпляр PostgresDriver.
        ids: Явный список ID столиков, созданных тестом.
        errors: Список для сбора ошибок (изменяется на месте).
    """
    _delete_by_ids(driver, "restaurant_tables", ids, errors)


def delete_users_by_ids(
    driver: PostgresDriver,
    ids: list[int],
    errors: list[Exception],
) -> None:
    """Удалить записи пользователей по списку ID.

    Вызывать ПОСЛЕДНИМ — users не зависят от tables и bookings.
    Ошибки добавляются в errors, удаление продолжается для остальных ID.

    Args:
        driver: Экземпляр PostgresDriver.
        ids: Явный список ID пользователей, созданных тестом.
        errors: Список для сбора ошибок (изменяется на месте).
    """
    _delete_by_ids(driver, "users", ids, errors)


# ---------------------------------------------------------------------------
# Класс-обёртка для автоматического сбора ID и очистки
# ---------------------------------------------------------------------------

class TestCleanupTracker:
    """Трекер объектов, созданных тестом, с автоматической очисткой.

    Позволяет регистрировать ID объектов и удалять их все разом
    в правильном FK-порядке. Не удаляет объекты, не зарегистрированные
    этим экземпляром трекера.

    Пример:
        tracker = TestCleanupTracker()
        tracker.register_booking(1)
        tracker.register_table(10)
        tracker.register_user(100)
        errors = tracker.cleanup(driver)
    """
    __test__ = False

    def __init__(self) -> None:
        self._booking_ids: list[int] = []
        self._table_ids: list[int] = []
        self._user_ids: list[int] = []

    def register_booking(self, booking_id: int) -> None:
        self._booking_ids.append(booking_id)

    def register_table(self, table_id: int) -> None:
        self._table_ids.append(table_id)

    def register_user(self, user_id: int) -> None:
        self._user_ids.append(user_id)

    def cleanup(self, driver: PostgresDriver) -> list[Exception]:
        """Удалить все зарегистрированные объекты в FK-порядке.

        Порядок: bookings → tables → users.
        Возвращает список ошибок (пустой при успешной очистке).
        Удаляются только ID, зарегистрированные этим экземпляром.
        """
        errors: list[Exception] = []
        delete_bookings_by_ids(driver, self._booking_ids, errors)
        delete_tables_by_ids(driver, self._table_ids, errors)
        delete_users_by_ids(driver, self._user_ids, errors)
        return errors
