"""Проверка восстановления после ошибок внутри транзакций.

Stage 2.6 — Transaction Recovery.

Цель — доказать четыре свойства поведения PostgreSQL-транзакций:
1. Ошибка внутри транзакции приводит к ROLLBACK.
2. Частично выполненные изменения не остаются в БД.
3. После ошибки соединение остаётся пригодным для дальнейшей работы.
4. Следующая успешная операция через тот же BookingService
   выполняется нормально.

Все тесты используют настоящий PostgreSQL.
Не используются mock, monkeypatch, fake database, подмена transaction().
Production-код не изменяется.
"""

from datetime import datetime

import psycopg2

from backend import BookingService
from models.booking import Booking
from models.table import Table
from models.user import User
from tests.test_cleanup import TestCleanupTracker
from tests.test_config import create_test_driver
from tests.test_data import (
    unique_phone,
    unique_table_location,
    unique_table_number,
    unique_username,
)


def _require_id(value: int | None, entity_name: str) -> int:
    """Проверить, что созданная сущность получила ID из базы данных."""
    if value is None:
        raise AssertionError(
            f"{entity_name} создана без ID из базы данных"
        )
    return value


def main() -> None:
    driver = create_test_driver()
    service = BookingService(driver)
    tracker = TestCleanupTracker()

    results: dict[str, str] = {}

    try:
        # ====== TEST 1 ======
        print("=" * 60)
        print(
            "TEST 1 — ошибка CREATE не оставляет бронирование (rollback)"
        )
        print("=" * 60)

        user = service.create_user(
            User(
                id=None,
                name=unique_username("TR User"),
                phone=unique_phone(),
            )
        )
        user_id = _require_id(user.id, "User")
        tracker.register_user(user_id)

        table = service.create_table(
            Table(
                id=None,
                number=unique_table_number("TRT"),
                capacity=2,
                location=unique_table_location("TR"),
            )
        )
        table_id = _require_id(table.id, "Table")
        tracker.register_table(table_id)

        base_start = datetime(2026, 11, 1, 18, 0)
        base_end = datetime(2026, 11, 1, 20, 0)

        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user_id,
                    table_id=table_id,
                    guests=5,  # capacity=2 → ValueError
                    start_time=base_start,
                    end_time=base_end,
                )
            )
            raise AssertionError(
                "Ожидался ValueError при guests > capacity"
            )
        except ValueError:
            print("Получен ожидаемый ValueError")

        own_bookings = [
            booking
            for booking in service.get_all_bookings()
            if booking.table_id == table_id
        ]
        assert len(own_bookings) == 0, (
            f"Ожидалось 0 бронирований тестового столика после ошибки, "
            f"но найдено {len(own_bookings)}"
        )
        print(
            "Бронирований тестового столика после ошибки: 0 —"
            " ROLLBACK сработал"
        )
        results["TEST 1 — CREATE rollback"] = "PASS"
        print("TEST 1: PASS")

        # ====== TEST 2 ======
        print()
        print("=" * 60)
        print(
            "TEST 2 — после ошибки CREATE тот же сервис продолжает"
            " работать"
        )
        print("=" * 60)

        booking = service.create_booking(
            Booking(
                id=None,
                user_id=user_id,
                table_id=table_id,
                guests=2,
                start_time=base_start,
                end_time=base_end,
            )
        )
        print(f"Создано корректное бронирование: {booking}")

        booking_id = _require_id(booking.id, "Booking")
        tracker.register_booking(booking_id)

        loaded = service.get_booking(booking_id)
        assert loaded is not None
        assert loaded.id == booking_id
        assert loaded.user_id == user_id
        assert loaded.table_id == table_id
        assert loaded.guests == 2

        print("Бронирование успешно загружено через get_booking")
        results[
            "TEST 2 — service works after failed CREATE"
        ] = "PASS"
        print("TEST 2: PASS")

        # ====== TEST 3 ======
        print()
        print("=" * 60)
        print(
            "TEST 3 — ошибка UPDATE не повреждает существующее"
            " бронирование"
        )
        print("=" * 60)

        original_guests = loaded.guests
        original_start = loaded.start_time
        original_end = loaded.end_time
        original_table_id = loaded.table_id
        original_user_id = loaded.user_id

        try:
            service.update_booking(
                Booking(
                    id=booking_id,
                    user_id=user_id,
                    table_id=table_id,
                    guests=5,  # capacity=2 → ValueError
                    start_time=original_start,
                    end_time=original_end,
                )
            )
            raise AssertionError(
                "Ожидался ValueError при guests > capacity"
                " в update_booking"
            )
        except ValueError:
            print("Получен ожидаемый ValueError")

        restored = service.get_booking(booking_id)
        assert restored is not None
        assert restored.user_id == original_user_id
        assert restored.table_id == original_table_id
        assert restored.guests == original_guests
        assert restored.start_time == original_start
        assert restored.end_time == original_end

        print(
            f"Бронирование осталось неизменным: "
            f"guests={restored.guests}, "
            f"start={restored.start_time}, "
            f"end={restored.end_time}"
        )
        results["TEST 3 — UPDATE rollback"] = "PASS"
        print("TEST 3: PASS")

        # ====== TEST 4 ======
        print()
        print("=" * 60)
        print(
            "TEST 4 — после ошибки UPDATE следующий UPDATE работает"
        )
        print("=" * 60)

        new_end = datetime(2026, 11, 1, 21, 0)
        updated = service.update_booking(
            Booking(
                id=booking_id,
                user_id=user_id,
                table_id=table_id,
                guests=2,
                start_time=original_start,
                end_time=new_end,
            )
        )
        print(f"Обновлённое бронирование: {updated}")
        assert updated.end_time == new_end

        verified = service.get_booking(booking_id)
        assert verified is not None
        assert verified.end_time == new_end
        assert verified.guests == 2

        print("Обновление подтверждено из БД")
        results[
            "TEST 4 — service works after failed UPDATE"
        ] = "PASS"
        print("TEST 4: PASS")

        # ====== TEST 5 ======
        print()
        print("=" * 60)
        print(
            "TEST 5 — реальная ошибка PostgreSQL внутри транзакции"
        )
        print("=" * 60)
        print(
            "Сценарий: вызвать реальную ошибку PostgreSQL через"
            " публичный API PostgresDriver.transaction() без изменения"
            " production-кода."
        )
        print()

        db_error_caught = False
        try:
            with driver.transaction() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 / 0")
        except psycopg2.Error as exc:
            db_error_caught = True
            assert isinstance(exc, psycopg2.errors.DivisionByZero), (
                f"Ожидался DivisionByZero, получен {type(exc).__name__}"
            )
            print(
                f"Получен ожидаемый psycopg2.Error: "
                f"{type(exc).__name__}"
            )

        assert db_error_caught, (
            "Ожидался psycopg2.Error при 'SELECT 1 / 0' "
            "внутри driver.transaction()"
        )

        probe = driver.fetch_one("SELECT 1 AS value")
        assert probe is not None and probe["value"] == 1, (
            "Соединение непригодно после ошибки транзакции"
        )
        print(
            "Следующая операция через тот же драйвер выполнена успешно —"
            " восстановление подтверждено"
        )

        results["TEST 5 — real DB error recovery"] = "PASS"
        print("TEST 5: PASS")

        # ====== ИТОГ ======
        print()
        print("=" * 60)
        print("ИТОГОВЫЙ ОТЧЁТ")
        print("=" * 60)
        for test_name, status in results.items():
            print(f"  {test_name}: {status}")
        print()

        all_pass = all(
            status in ("PASS", "SKIPPED")
            for status in results.values()
        )
        if all_pass:
            print("STAGE 2.6 TRANSACTION RECOVERY: PASS")
        else:
            print("STAGE 2.6 TRANSACTION RECOVERY: FAIL")
            failed = [
                name
                for name, status in results.items()
                if status not in ("PASS", "SKIPPED")
            ]
            print(f"Провалились: {failed}")

    finally:
        try:
            cleanup_errors = tracker.cleanup(driver)
            for error in cleanup_errors:
                print(f"  [cleanup error] {error}")
            if not cleanup_errors:
                print("  Все зарегистрированные объекты удалены")
        finally:
            driver.close()


def test_transaction_recovery() -> None:
    """Pytest-точка входа: проверки восстановления транзакций Stage 2.6."""
    main()


if __name__ == "__main__":
    main()
