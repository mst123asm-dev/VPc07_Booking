"""Генератор уникальных тестовых данных.

Использует PID процесса и монотонный счётчик для генерации
детерминированно уникальных значений в пределах одного запуска.
Не использует случайность и реальные персональные данные.

Пример использования:
    from tests.test_data import unique_phone, unique_table_number

    phone = unique_phone()       # "+72642710001"
    phone = unique_phone("+7")   # "+72642710002"
    tbl   = unique_table_number()# "T2642710003"
    name  = unique_username()    # "Test User 2642710004"
"""

from __future__ import annotations

import itertools
import os


# Токен процесса (последние 6 цифр PID) — уникален для каждого запуска.
_TOKEN: str = str(os.getpid())[-6:]
# Монотонный счётчик — гарантирует уникальность внутри одного процесса.
_COUNTER: itertools.count = itertools.count(1)


def _next_value() -> int:
    """Вернуть следующий уникальный номер счётчика."""
    return next(_COUNTER)


def unique_phone(prefix: str = "+7") -> str:
    """Сгенерировать уникальный номер телефона.

    Формат: {prefix}{token}{counter:04d}
    Пример: "+72642710001"

    Аргументы:
        prefix: Префикс номера телефона (по умолчанию "+7").

    Возвращает:
        Уникальный номер телефона в формате строки.
    """
    return f"{prefix}{_TOKEN}{_next_value():04d}"


def unique_table_number(prefix: str = "T") -> str:
    """Сгенерировать уникальный номер столика.

    Формат: {prefix}{token}{counter:04d}
    Пример: "T2642710002"

    Аргументы:
        prefix: Префикс номера (по умолчанию "T").

    Возвращает:
        Уникальный номер столика в формате строки.
    """
    return f"{prefix}{_TOKEN}{_next_value():04d}"


def unique_username(prefix: str = "Test User") -> str:
    """Сгенерировать уникальное имя пользователя.

    Формат: {prefix} {token}{counter:04d}
    Пример: "Test User 2642710003"

    Аргументы:
        prefix: Префикс имени (по умолчанию "Test User").

    Возвращает:
        Уникальное имя пользователя в формате строки.
    """
    return f"{prefix} {_TOKEN}{_next_value():04d}"


def unique_table_location(prefix: str = "Test") -> str:
    """Сгенерировать уникальное описание локации столика.

    Формат: {prefix} {counter:03d}
    Пример: "Test 001"

    Аргументы:
        prefix: Префикс локации (по умолчанию "Test").

    Возвращает:
        Уникальное описание локации в формате строки.
    """
    return f"{prefix} {_next_value():03d}"
