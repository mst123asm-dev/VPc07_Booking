"""Идемпотентное создание SQL-схемы базы данных.

Этот модуль создаёт необходимые таблицы PostgreSQL при запуске приложения.
Использует CREATE TABLE IF NOT EXISTS для идемпотентности —
повторный запуск не вызывает ошибок при существующих таблицах.
"""

from postgres_driver import PostgresDriver

# Создание таблицы пользователей
_CREATE_USERS_TABLE = """\
CREATE TABLE IF NOT EXISTS users (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE
);
"""

# Создание таблицы столиков ресторана
_CREATE_TABLES_TABLE = """\
CREATE TABLE IF NOT EXISTS restaurant_tables (
    id       SERIAL PRIMARY KEY,
    number   TEXT NOT NULL UNIQUE,
    capacity INT NOT NULL CHECK (capacity > 0),
    location TEXT
);
"""

# Создание таблицы бронирований
_CREATE_BOOKINGS_TABLE = """\
CREATE TABLE IF NOT EXISTS bookings (
    id         SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    table_id   INT NOT NULL REFERENCES restaurant_tables(id) ON DELETE RESTRICT,
    guests     INT NOT NULL CHECK (guests > 0),
    start_time TIMESTAMP NOT NULL,
    end_time   TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK (start_time < end_time)
);
"""


def init(driver: PostgresDriver) -> None:
    """Создать таблицы базы данных, если они ещё не существуют.

    Таблицы создаются в порядке зависимостей:
    1. users
    2. restaurant_tables
    3. bookings

    Args:
        driver: Экземпляр PostgreSQLDriver для выполнения SQL-запросов.
    """
    driver.execute_query(_CREATE_USERS_TABLE)
    driver.execute_query(_CREATE_TABLES_TABLE)
    driver.execute_query(_CREATE_BOOKINGS_TABLE)
