"""Точка входа в приложение системы бронирования столиков.

Загружает конфигурацию из .env, создаёт PostgreSQLDriver
и инициализирует схему базы данных.
"""

import os
import sys
import tkinter as tk

from dotenv import load_dotenv

from postgres_driver import PostgresDriver
import schema

# Загрузка переменных окружения из файла .env
load_dotenv()


def build_dsn() -> str:
    """Собрать строку подключения DSN из переменных окружения.

    Поддерживает IPv6-адреса, оборачивая их в квадратные скобки для URL.

    Returns:
        DSN-строка для PostgreSQL.

    Raises:
        ValueError: Если не все обязательные параметры заданы.
    """
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, name, user, password]):
        missing = [
            key
            for key, value in {
                "DB_HOST": host,
                "DB_NAME": name,
                "DB_USER": user,
                "DB_PASSWORD": password,
            }.items()
            if not value
        ]
        raise ValueError(
            f"Не заданы переменные окружения: {', '.join(missing)}"
        )

    # Все переменные не None после проверки all()
    host_str = str(host)
    port_str = str(port)

    # Для IPv6-адресов в URL требуются квадратные скобки
    if ":" in host_str and not host_str.startswith("["):
        host_str = f"[{host_str}]"

    return f"postgresql://{user}:{password}@{host_str}:{port_str}/{name}"


def main() -> None:
    """Запустить приложение: драйвер, схема, сервис, GUI."""
    try:
        dsn = build_dsn()
    except ValueError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        sys.exit(1)

    driver = PostgresDriver(dsn=dsn)

    try:
        schema.init(driver)
    except Exception as exc:
        print(f"Ошибка инициализации схемы: {exc}", file=sys.stderr)
        sys.exit(1)

    from backend import BookingService
    from app import BookingApp

    service = BookingService(driver)

    root = tk.Tk()
    BookingApp(root, service)
    root.mainloop()

    driver.close()


if __name__ == "__main__":
    main()
