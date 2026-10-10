from datetime import datetime

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

    try:
        user = service.create_user(
            User(
                id=None,
                name=unique_username("Stage 2.4 User"),
                phone=unique_phone(),
            )
        )
        user_id = _require_id(user.id, "User")
        tracker.register_user(user_id)

        second_user = service.create_user(
            User(
                id=None,
                name=unique_username("Stage 2.4 Second User"),
                phone=unique_phone(),
            )
        )
        second_user_id = _require_id(second_user.id, "Second User")
        tracker.register_user(second_user_id)

        table = service.create_table(
            Table(
                id=None,
                number=unique_table_number("S24"),
                capacity=4,
                location=unique_table_location("Stage 2.4"),
            )
        )
        table_id = _require_id(table.id, "Table")
        tracker.register_table(table_id)

        small_table = service.create_table(
            Table(
                id=None,
                number=unique_table_number("S24S"),
                capacity=2,
                location=unique_table_location("Stage 2.4"),
            )
        )
        small_table_id = _require_id(small_table.id, "Small table")
        tracker.register_table(small_table_id)

        base_start = datetime(2026, 10, 10, 18, 0)
        base_end = datetime(2026, 10, 10, 20, 0)

        print("1. CREATE VALID BOOKING")
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
        booking_id = _require_id(booking.id, "Booking")
        tracker.register_booking(booking_id)

        print(booking)
        assert booking.id == booking_id
        assert booking.user_id == user_id
        assert booking.table_id == table_id
        assert booking.guests == 2
        assert booking.start_time == base_start
        assert booking.end_time == base_end
        assert booking.created_at is not None
        print("PASS")

        print("\n2. NON-EXISTING USER")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=999999999,
                    table_id=table_id,
                    guests=2,
                    start_time=datetime(2026, 10, 11, 18, 0),
                    end_time=datetime(2026, 10, 11, 20, 0),
                )
            )
        except LookupError:
            print("Получен ожидаемый LookupError")
            print("PASS")
        else:
            raise AssertionError("Ожидался LookupError")

        print("\n3. NON-EXISTING TABLE")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user_id,
                    table_id=999999999,
                    guests=2,
                    start_time=datetime(2026, 10, 11, 18, 0),
                    end_time=datetime(2026, 10, 11, 20, 0),
                )
            )
        except LookupError:
            print("Получен ожидаемый LookupError")
            print("PASS")
        else:
            raise AssertionError("Ожидался LookupError")

        print("\n4. GUESTS EXCEED TABLE CAPACITY")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user_id,
                    table_id=small_table_id,
                    guests=3,
                    start_time=datetime(2026, 10, 11, 18, 0),
                    end_time=datetime(2026, 10, 11, 20, 0),
                )
            )
        except ValueError:
            print("Получен ожидаемый ValueError")
            print("PASS")
        else:
            raise AssertionError("Ожидался ValueError")

        print("\n5. OVERLAPPING BOOKING")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=second_user_id,
                    table_id=table_id,
                    guests=2,
                    start_time=datetime(2026, 10, 10, 19, 0),
                    end_time=datetime(2026, 10, 10, 21, 0),
                )
            )
        except ValueError:
            print("Получен ожидаемый ValueError")
            print("PASS")
        else:
            raise AssertionError("Ожидался ValueError")

        print("\n6. ADJACENT BOOKING IS ALLOWED")
        second_booking = service.create_booking(
            Booking(
                id=None,
                user_id=second_user_id,
                table_id=table_id,
                guests=2,
                start_time=datetime(2026, 10, 10, 20, 0),
                end_time=datetime(2026, 10, 10, 22, 0),
            )
        )
        second_booking_id = _require_id(
            second_booking.id,
            "Second booking",
        )
        tracker.register_booking(second_booking_id)

        print(second_booking)
        assert second_booking.id == second_booking_id
        assert second_booking.start_time == datetime(2026, 10, 10, 20, 0)
        assert second_booking.end_time == datetime(2026, 10, 10, 22, 0)
        print("PASS")

        print("\n7. UPDATE TO FREE INTERVAL")
        updated_start = datetime(2026, 10, 10, 22, 0)
        updated_end = datetime(2026, 10, 11, 0, 0)

        updated = service.update_booking(
            Booking(
                id=booking_id,
                user_id=user_id,
                table_id=table_id,
                guests=3,
                start_time=updated_start,
                end_time=updated_end,
            )
        )

        print(updated)
        assert updated.id == booking_id
        assert updated.guests == 3
        assert updated.start_time == updated_start
        assert updated.end_time == updated_end
        assert updated.created_at == booking.created_at
        print("PASS")

        print("\n8. UPDATE TO OVERLAPPING INTERVAL")
        try:
            service.update_booking(
                Booking(
                    id=booking_id,
                    user_id=user_id,
                    table_id=table_id,
                    guests=2,
                    start_time=datetime(2026, 10, 10, 21, 0),
                    end_time=datetime(2026, 10, 10, 23, 0),
                )
            )
        except ValueError:
            print("Получен ожидаемый ValueError")
            print("PASS")
        else:
            raise AssertionError("Ожидался ValueError")

        print("\n9. UPDATE SAME BOOKING WITHOUT OVERLAP")
        unchanged_interval = service.update_booking(
            Booking(
                id=booking_id,
                user_id=user_id,
                table_id=table_id,
                guests=3,
                start_time=updated_start,
                end_time=updated_end,
            )
        )

        assert unchanged_interval.id == booking_id
        assert unchanged_interval.start_time == updated_start
        assert unchanged_interval.end_time == updated_end
        print("PASS")

        print("\n10. UPDATE NON-EXISTING BOOKING")
        try:
            service.update_booking(
                Booking(
                    id=999999999,
                    user_id=user_id,
                    table_id=table_id,
                    guests=2,
                    start_time=datetime(2026, 10, 10, 19, 0),
                    end_time=datetime(2026, 10, 10, 21, 0),
                )
            )
        except LookupError:
            print("Получен ожидаемый LookupError")
            print("PASS")
        else:
            raise AssertionError("Ожидался LookupError")

        print("\n11. INVALID BOOKING")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user_id,
                    table_id=table_id,
                    guests=0,
                    start_time=base_start,
                    end_time=base_end,
                )
            )
        except ValueError:
            print("Получен ожидаемый ValueError")
            print("PASS")
        else:
            raise AssertionError("Ожидался ValueError")

        print("\n12. GET BOOKING")
        loaded = service.get_booking(booking_id)
        print(loaded)
        assert loaded is not None
        assert loaded.id == booking_id
        assert loaded.created_at == booking.created_at
        print("PASS")

        print("\n13. GET ALL BOOKINGS")
        bookings = service.get_all_bookings()
        print(f"Найдено бронирований: {len(bookings)}")
        assert any(item.id == booking_id for item in bookings)
        assert any(item.id == second_booking_id for item in bookings)
        print("PASS")

        print("\n14. DELETE BOOKING")
        deleted = service.delete_booking(booking_id)
        print(f"Первое удаление: {deleted}")
        assert deleted is True

        deleted_again = service.delete_booking(booking_id)
        print(f"Повторное удаление: {deleted_again}")
        assert deleted_again is False
        print("PASS")

        print("\n15. DELETE SECOND BOOKING")
        deleted_second = service.delete_booking(second_booking_id)
        print(f"Удаление второго бронирования: {deleted_second}")
        assert deleted_second is True
        print("PASS")

        print("\nSTAGE 2.4 BOOKING BUSINESS VALIDATION: PASS")

    finally:
        try:
            cleanup_errors = tracker.cleanup(driver)
            for error in cleanup_errors:
                print(f"[cleanup error] {error}")
        finally:
            driver.close()


def test_bookings() -> None:
    """Pytest-точка входа: полный сценарий Stage 2.4."""
    main()


if __name__ == "__main__":
    main()
