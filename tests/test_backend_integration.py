"""Интеграционная проверка Backend — Stage 2.7.

Единый последовательный сценарий, использующий реальный PostgreSQL
и существующий BookingService.

Не использует:
- mock / monkeypatch
- SQLite
- дополнительные соединения вне PostgresDriver
- обход BookingService
- изменение production-кода

Запуск:
    python -m tests.test_backend_integration
"""

from __future__ import annotations

from datetime import datetime
import inspect

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
    """Проверить ID созданной сущности и вернуть его как int."""
    if value is None:
        raise AssertionError(
            f"{entity_name} создана без ID из базы данных"
        )
    return value


# ---------------------------------------------------------------------------
# Main integration scenario
# ---------------------------------------------------------------------------

def main() -> None:
    """Выполнить единую интеграционную проверку Backend."""
    driver = create_test_driver()
    service = BookingService(driver)
    tracker = TestCleanupTracker()

    results: dict[str, str] = {}
    status: dict[str, str] = {}

    try:
        # ===================================================================
        # PHASE 1: User CRUD
        # ===================================================================
        print("=" * 60)
        print("PHASE 1: User CRUD")
        print("=" * 60)

        user1 = service.create_user(
            User(
                id=None,
                name=unique_username("Integration User 1"),
                phone=unique_phone(),
            )
        )
        user1_id = _require_id(user1.id, "user1")
        tracker.register_user(user1_id)

        retrieved = service.get_user(user1_id)
        assert retrieved is not None
        assert retrieved.id == user1_id
        assert retrieved.name == user1.name
        print("  create_user / get_user: OK")

        all_users = service.get_all_users()
        assert any(u.id == user1_id for u in all_users)
        print("  get_all_users: OK")

        updated = service.update_user(
            User(
                id=user1_id,
                name="Integration User 1 Updated",
                phone=user1.phone,
            )
        )
        assert updated.name == "Integration User 1 Updated"
        print("  update_user: OK")

        # Create user2 and user3 (keep user1 alive for bookings)
        user2 = service.create_user(
            User(
                id=None,
                name=unique_username("Integration User 2"),
                phone=unique_phone(),
            )
        )
        user2_id = _require_id(user2.id, "user2")
        tracker.register_user(user2_id)

        user3 = service.create_user(
            User(
                id=None,
                name=unique_username("Integration User 3"),
                phone=unique_phone(),
            )
        )
        user3_id = _require_id(user3.id, "user3")
        tracker.register_user(user3_id)

        # Delete user3 to test delete_user
        deleted = service.delete_user(user3_id)
        assert deleted is True
        still_exists = service.get_user(user3_id)
        assert still_exists is None
        print("  delete_user: OK")

        results["1. User CRUD"] = "PASS"
        status["1. User CRUD"] = "PASS"
        print("1. User CRUD: PASS\n")

        # ===================================================================
        # PHASE 2: Table CRUD
        # ===================================================================
        print("=" * 60)
        print("PHASE 2: Table CRUD")
        print("=" * 60)

        table1 = service.create_table(
            Table(
                id=None,
                number=unique_table_number("INTEG1"),
                capacity=4,
                location=unique_table_location("Window"),
            )
        )
        table1_id = _require_id(table1.id, "table1")
        tracker.register_table(table1_id)

        retrieved = service.get_table(table1_id)
        assert retrieved is not None
        assert retrieved.id == table1_id
        assert retrieved.capacity == 4
        print("  create_table / get_table: OK")

        all_tables = service.get_all_tables()
        assert any(t.id == table1_id for t in all_tables)
        print("  get_all_tables: OK")

        updated = service.update_table(
            Table(
                id=table1_id,
                number=table1.number,
                capacity=6,
                location="Center",
            )
        )
        assert updated.capacity == 6
        print("  update_table: OK")

        # Create table2 and table3; keep table1 for booking tests
        table2 = service.create_table(
            Table(
                id=None,
                number=unique_table_number("INTEG2"),
                capacity=2,
                location="Bar",
            )
        )
        table2_id = _require_id(table2.id, "table2")
        tracker.register_table(table2_id)

        table3 = service.create_table(
            Table(
                id=None,
                number=unique_table_number("INTEG3"),
                capacity=8,
                location="VIP",
            )
        )
        table3_id = _require_id(table3.id, "table3")
        tracker.register_table(table3_id)

        # Delete table3 to test delete_table
        deleted = service.delete_table(table3_id)
        assert deleted is True
        still_exists = service.get_table(table3_id)
        assert still_exists is None
        print("  delete_table: OK")

        results["2. Table CRUD"] = "PASS"
        status["2. Table CRUD"] = "PASS"
        print("2. Table CRUD: PASS\n")

        # ===================================================================
        # PHASE 3: Booking CRUD
        # ===================================================================
        print("=" * 60)
        print("PHASE 3: Booking CRUD")
        print("=" * 60)

        base_start = datetime(2026, 12, 15, 18, 0)
        base_end = datetime(2026, 12, 15, 20, 0)

        booking1 = service.create_booking(
            Booking(
                id=None,
                user_id=user1_id,
                table_id=table1_id,
                guests=2,
                start_time=base_start,
                end_time=base_end,
            )
        )
        booking1_id = _require_id(booking1.id, "booking1")
        assert booking1.user_id == user1_id
        assert booking1.table_id == table1_id
        assert booking1.guests == 2
        assert booking1.start_time == base_start
        assert booking1.end_time == base_end
        assert booking1.created_at is not None
        tracker.register_booking(booking1_id)
        print("  create_booking: OK")

        retrieved = service.get_booking(booking1_id)
        assert retrieved is not None
        assert retrieved.id == booking1_id
        assert retrieved.created_at == booking1.created_at
        print("  get_booking: OK")

        all_bookings = service.get_all_bookings()
        assert any(b.id == booking1_id for b in all_bookings)
        print("  get_all_bookings: OK")

        # Create booking2
        booking2 = service.create_booking(
            Booking(
                id=None,
                user_id=user2_id,
                table_id=table1_id,
                guests=3,
                start_time=datetime(2026, 12, 15, 20, 0),
                end_time=datetime(2026, 12, 15, 22, 0),
            )
        )
        booking2_id = _require_id(booking2.id, "booking2")
        tracker.register_booking(booking2_id)
        print("  create_booking #2: OK")

        # Update booking1
        updated_start = datetime(2026, 12, 15, 22, 0)
        updated_end = datetime(2026, 12, 16, 0, 0)

        updated = service.update_booking(
            Booking(
                id=booking1_id,
                user_id=user1_id,
                table_id=table1_id,
                guests=3,
                start_time=updated_start,
                end_time=updated_end,
            )
        )
        assert updated.id == booking1_id
        assert updated.guests == 3
        assert updated.start_time == updated_start
        assert updated.end_time == updated_end
        assert updated.created_at == booking1.created_at
        print("  update_booking: OK")

        results["3. Booking CRUD"] = "PASS"
        status["3. Booking CRUD"] = "PASS"
        print("3. Booking CRUD: PASS\n")

        # ===================================================================
        # PHASE 4: Business rules validation
        # ===================================================================
        print("=" * 60)
        print("PHASE 4: Business rules validation")
        print("=" * 60)

        # 4a) Nonexistent user -> LookupError
        print("  4a) nonexistent user -> LookupError")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=999999999,
                    table_id=table1_id,
                    guests=2,
                    start_time=datetime(2026, 12, 16, 18, 0),
                    end_time=datetime(2026, 12, 16, 20, 0),
                )
            )
            raise AssertionError("Expected LookupError")
        except LookupError:
            pass

        results["4a. User validation"] = "PASS"
        status["4a. User validation"] = "PASS"
        print("4a. User validation: PASS")

        # 4b) Nonexistent table -> LookupError
        print("  4b) nonexistent table -> LookupError")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user1_id,
                    table_id=999999999,
                    guests=2,
                    start_time=datetime(2026, 12, 16, 18, 0),
                    end_time=datetime(2026, 12, 16, 20, 0),
                )
            )
            raise AssertionError("Expected LookupError")
        except LookupError:
            pass

        results["4b. Table validation"] = "PASS"
        status["4b. Table validation"] = "PASS"
        print("4b. Table validation: PASS")

        # 4c) guests > capacity -> ValueError
        print("  4c) guests > capacity -> ValueError")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user1_id,
                    table_id=table2_id,
                    guests=5,
                    start_time=datetime(2026, 12, 16, 18, 0),
                    end_time=datetime(2026, 12, 16, 20, 0),
                )
            )
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

        results["4c. Capacity validation"] = "PASS"
        status["4c. Capacity validation"] = "PASS"
        print("4c. Capacity validation: PASS")

        # 4d) Overlapping intervals -> ValueError
        # booking2 is 20:00-22:00; booking1 is now 22:00-00:00.
        print("  4d) overlapping intervals -> ValueError")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=user2_id,
                    table_id=table1_id,
                    guests=2,
                    start_time=datetime(2026, 12, 15, 21, 0),
                    end_time=datetime(2026, 12, 15, 23, 0),
                )
            )
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

        results["4d. Overlap validation"] = "PASS"
        status["4d. Overlap validation"] = "PASS"
        print("4d. Overlap validation: PASS")

        # 4e) Adjacent intervals are allowed.
        # The end of the new interval equals booking2's start.
        print("  4e) adjacent intervals allowed")
        adj_booking = service.create_booking(
            Booking(
                id=None,
                user_id=user2_id,
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 19, 0),
                end_time=datetime(2026, 12, 15, 20, 0),
            )
        )
        adj_booking_id = _require_id(adj_booking.id, "adj_booking")
        tracker.register_booking(adj_booking_id)

        results["4e. Adjacent intervals"] = "PASS"
        status["4e. Adjacent intervals"] = "PASS"
        print("4e. Adjacent intervals: PASS")

        # 4f) Update to a free interval is allowed.
        print("  4f) update to free interval allowed")
        free_start = datetime(2026, 12, 17, 10, 0)
        free_end = datetime(2026, 12, 17, 12, 0)

        updated = service.update_booking(
            Booking(
                id=booking1_id,
                user_id=user1_id,
                table_id=table1_id,
                guests=2,
                start_time=free_start,
                end_time=free_end,
            )
        )
        assert updated.id == booking1_id
        assert updated.start_time == free_start
        assert updated.end_time == free_end

        results["4f. Booking update free"] = "PASS"
        status["4f. Booking update free"] = "PASS"
        print("4f. Booking update free: PASS")

        # 4g) Update to an overlapping interval is denied.
        print("  4g) update to overlapping interval denied")
        try:
            service.update_booking(
                Booking(
                    id=booking1_id,
                    user_id=user1_id,
                    table_id=table1_id,
                    guests=2,
                    start_time=datetime(2026, 12, 15, 21, 0),
                    end_time=datetime(2026, 12, 15, 23, 0),
                )
            )
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

        results["4g. Booking update overlap"] = "PASS"
        status["4g. Booking update overlap"] = "PASS"
        print("4g. Booking update overlap: PASS")

        # 4h) Update nonexistent booking -> LookupError
        print("  4h) update nonexistent booking -> LookupError")
        try:
            service.update_booking(
                Booking(
                    id=999999999,
                    user_id=user1_id,
                    table_id=table1_id,
                    guests=2,
                    start_time=datetime(2026, 12, 17, 10, 0),
                    end_time=datetime(2026, 12, 17, 12, 0),
                )
            )
            raise AssertionError("Expected LookupError")
        except LookupError:
            pass

        results["4h. Update nonexistent"] = "PASS"
        status["4h. Update nonexistent"] = "PASS"
        print("4h. Update nonexistent: PASS")

        print()

        # ===================================================================
        # PHASE 5: check_table_availability
        # ===================================================================
        print("=" * 60)
        print("PHASE 5: check_table_availability")
        print("=" * 60)

        if not hasattr(service, "check_table_availability"):
            print("  check_table_availability: NOT FOUND in BookingService")
            results["5. Availability"] = "SKIPPED"
            status["5. Availability"] = "MISSING REQUIREMENT"
            print("5. Availability: MISSING REQUIREMENT")
            print()
        else:
            sig = inspect.signature(service.check_table_availability)
            print(f"  Signature: check_table_availability{sig}")

            # 5a) Free table / free interval -> True
            print("  5a) free table, free interval")
            avail = service.check_table_availability(
                table_id=table2_id,
                guests=2,
                start_time=datetime(2026, 12, 18, 18, 0),
                end_time=datetime(2026, 12, 18, 20, 0),
            )
            assert avail is True, f"Expected True, got {avail}"
            results["5a. Free interval"] = "PASS"
            status["5a. Free interval"] = "PASS"
            print("5a. Free interval: PASS")

            # 5b) Full overlap with adj_booking 19:00-20:00
            print("  5b) full overlap (adj_booking 19:00-20:00)")
            avail = service.check_table_availability(
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 19, 0),
                end_time=datetime(2026, 12, 15, 20, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5b. Full overlap"] = "PASS"
            status["5b. Full overlap"] = "PASS"
            print("5b. Full overlap: PASS")

            # 5c) Partial overlap from left.
            print("  5c) partial overlap from left (18:30-19:30)")
            avail = service.check_table_availability(
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 18, 30),
                end_time=datetime(2026, 12, 15, 19, 30),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5c. Partial overlap left"] = "PASS"
            status["5c. Partial overlap left"] = "PASS"
            print("5c. Partial overlap left: PASS")

            # 5d) Partial overlap from right against booking2 20:00-22:00.
            print("  5d) partial overlap from right (21:00-23:00)")
            avail = service.check_table_availability(
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 21, 0),
                end_time=datetime(2026, 12, 15, 23, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5d. Partial overlap right"] = "PASS"
            status["5d. Partial overlap right"] = "PASS"
            print("5d. Partial overlap right: PASS")

            # 5e) Request inside existing booking.
            print("  5e) request inside existing (19:15-19:45)")
            avail = service.check_table_availability(
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 19, 15),
                end_time=datetime(2026, 12, 15, 19, 45),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5e. Inside existing"] = "PASS"
            status["5e. Inside existing"] = "PASS"
            print("5e. Inside existing: PASS")

            # 5f) Existing booking inside requested interval.
            print("  5f) existing inside request (18:00-21:00)")
            avail = service.check_table_availability(
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 18, 0),
                end_time=datetime(2026, 12, 15, 21, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5f. Existing inside request"] = "PASS"
            status["5f. Existing inside request"] = "PASS"
            print("5f. Existing inside request: PASS")

            # 5g) Adjacent interval: request ends when adj_booking starts.
            print("  5g) adjacent interval (17:00-19:00)")
            avail = service.check_table_availability(
                table_id=table1_id,
                guests=2,
                start_time=datetime(2026, 12, 15, 17, 0),
                end_time=datetime(2026, 12, 15, 19, 0),
            )
            assert avail is True, f"Expected True, got {avail}"
            results["5g. Adjacent interval"] = "PASS"
            status["5g. Adjacent interval"] = "PASS"
            print("5g. Adjacent interval: PASS")

            # 5h) Insufficient capacity: table2.capacity=2, guests=5.
            print("  5h) guests > capacity (table2 cap=2, guests=5)")
            avail = service.check_table_availability(
                table_id=table2_id,
                guests=5,
                start_time=datetime(2026, 12, 18, 18, 0),
                end_time=datetime(2026, 12, 18, 20, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5h. Guests > capacity"] = "PASS"
            status["5h. Guests > capacity"] = "PASS"
            print("5h. Guests > capacity: PASS")

            # 5i) Nonexistent table -> False.
            print("  5i) nonexistent table")
            avail = service.check_table_availability(
                table_id=999999999,
                guests=2,
                start_time=datetime(2026, 12, 18, 18, 0),
                end_time=datetime(2026, 12, 18, 20, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5i. Nonexistent table"] = "PASS"
            status["5i. Nonexistent table"] = "PASS"
            print("5i. Nonexistent table: PASS")

            # 5j) Invalid interval: start >= end.
            print("  5j) invalid interval (start >= end)")
            avail = service.check_table_availability(
                table_id=table2_id,
                guests=2,
                start_time=datetime(2026, 12, 18, 20, 0),
                end_time=datetime(2026, 12, 18, 18, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5j. Invalid interval"] = "PASS"
            status["5j. Invalid interval"] = "PASS"
            print("5j. Invalid interval: PASS")

            # 5k) Invalid guest count: guests <= 0.
            print("  5k) invalid guests (guests <= 0)")
            avail = service.check_table_availability(
                table_id=table2_id,
                guests=0,
                start_time=datetime(2026, 12, 18, 18, 0),
                end_time=datetime(2026, 12, 18, 20, 0),
            )
            assert avail is False, f"Expected False, got {avail}"
            results["5k. Invalid guests"] = "PASS"
            status["5k. Invalid guests"] = "PASS"
            print("5k. Invalid guests: PASS")

            # Verify service state after negative results.
            print("  5l) state recovery after failures")
            avail = service.check_table_availability(
                table_id=table2_id,
                guests=2,
                start_time=datetime(2026, 12, 18, 18, 0),
                end_time=datetime(2026, 12, 18, 20, 0),
            )
            assert avail is True, f"Expected True after failures, got {avail}"
            results["5l. State recovery"] = "PASS"
            status["5l. State recovery"] = "PASS"
            print("5l. State recovery: PASS")

            results["5. Availability"] = "PASS"
            status["5. Availability"] = "PASS"
            print("\n5. Availability: PASS")
            print()

        # ===================================================================
        # PHASE 6: Recovery after errors
        # ===================================================================
        print("=" * 60)
        print("PHASE 6: Recovery after errors")
        print("=" * 60)

        recovery_user = service.create_user(
            User(
                id=None,
                name=unique_username("Recovery User"),
                phone=unique_phone(),
            )
        )
        recovery_user_id = _require_id(recovery_user.id, "recovery_user")
        tracker.register_user(recovery_user_id)

        recovery_table = service.create_table(
            Table(
                id=None,
                number=unique_table_number("REC"),
                capacity=2,
                location=unique_table_location("Recovery"),
            )
        )
        recovery_table_id = _require_id(recovery_table.id, "recovery_table")
        tracker.register_table(recovery_table_id)

        rec_start = datetime(2026, 12, 20, 18, 0)
        rec_end = datetime(2026, 12, 20, 20, 0)

        # 6a) After CREATE fails, normal CREATE works.
        print("  6a) recovery after failed CREATE")
        try:
            service.create_booking(
                Booking(
                    id=None,
                    user_id=recovery_user_id,
                    table_id=recovery_table_id,
                    guests=5,
                    start_time=rec_start,
                    end_time=rec_end,
                )
            )
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

        recovery_booking = service.create_booking(
            Booking(
                id=None,
                user_id=recovery_user_id,
                table_id=recovery_table_id,
                guests=2,
                start_time=rec_start,
                end_time=rec_end,
            )
        )
        recovery_booking_id = _require_id(
            recovery_booking.id,
            "recovery_booking",
        )
        tracker.register_booking(recovery_booking_id)

        loaded = service.get_booking(recovery_booking_id)
        assert loaded is not None
        assert loaded.guests == 2
        print("  Recovery after CREATE: OK")
        results["6a. Recovery after CREATE"] = "PASS"
        status["6a. Recovery after CREATE"] = "PASS"
        print("6a. Recovery after CREATE: PASS")

        # 6b) After UPDATE fails, normal UPDATE works.
        print("  6b) recovery after failed UPDATE")
        try:
            service.update_booking(
                Booking(
                    id=recovery_booking_id,
                    user_id=recovery_user_id,
                    table_id=recovery_table_id,
                    guests=5,
                    start_time=rec_start,
                    end_time=rec_end,
                )
            )
            raise AssertionError("Expected ValueError")
        except ValueError:
            pass

        new_end = datetime(2026, 12, 20, 21, 0)
        updated = service.update_booking(
            Booking(
                id=recovery_booking_id,
                user_id=recovery_user_id,
                table_id=recovery_table_id,
                guests=2,
                start_time=rec_start,
                end_time=new_end,
            )
        )
        assert updated.end_time == new_end

        verified = service.get_booking(recovery_booking_id)
        assert verified is not None
        assert verified.end_time == new_end
        print("  Recovery after UPDATE: OK")
        results["6b. Recovery after UPDATE"] = "PASS"
        status["6b. Recovery after UPDATE"] = "PASS"
        print("6b. Recovery after UPDATE: PASS")

        print()

        # ===================================================================
        # PHASE 7: Final state check
        # ===================================================================
        print("=" * 60)
        print("PHASE 7: Final state check")
        print("=" * 60)

        all_bookings = service.get_all_bookings()
        print(f"  Total bookings in DB: {len(all_bookings)}")

        b1 = service.get_booking(booking1_id)
        assert b1 is not None
        assert b1.start_time == free_start
        assert b1.end_time == free_end
        print(
            f"  booking1 (updated): start={b1.start_time}, "
            f"end={b1.end_time} — OK"
        )

        b2 = service.get_booking(booking2_id)
        assert b2 is not None
        assert b2.guests == 3
        print(f"  booking2: guests={b2.guests} — OK")

        results["7. Final state"] = "PASS"
        status["7. Final state"] = "PASS"
        print("7. Final state: PASS\n")

    finally:
        print("=" * 60)
        print("CLEANUP — удаление зарегистрированных тестовых данных")
        print("=" * 60)

        cleanup_errors = tracker.cleanup(driver)
        if cleanup_errors:
            for error in cleanup_errors:
                print(f"  [cleanup error] {error}")
            results["12. Cleanup"] = "FAIL"
        else:
            print("  Все зарегистрированные объекты удалены")
            results["12. Cleanup"] = "PASS"

        status["12. Cleanup"] = results["12. Cleanup"]
        print(f"12. Cleanup: {results['12. Cleanup']}\n")

        driver.close()

    # ===================================================================
    # FINAL REPORT
    # ===================================================================
    print("=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    for key in sorted(status):
        print(f"  {key}: {status[key]}")
    print()

    all_ok = all(s in ("PASS", "SKIPPED") for s in results.values())
    has_missing = (
        status.get("5. Availability") == "MISSING REQUIREMENT"
    )

    if has_missing:
        print("STAGE 2.7 BACKEND INTEGRATION: BLOCKED")
        print()
        print("MISSING REQUIREMENT:")
        print("  check_table_availability")
    elif all_ok:
        print("STAGE 2.7 BACKEND INTEGRATION: PASS")
    else:
        print("STAGE 2.7 BACKEND INTEGRATION: FAIL")
        failed = [
            name
            for name, result in status.items()
            if result not in ("PASS", "SKIPPED")
        ]
        print(f"  Failed: {failed}")


def test_backend_integration() -> None:
    """Pytest-точка входа: интеграционная проверка Stage 2.7."""
    main()


if __name__ == "__main__":
    main()
