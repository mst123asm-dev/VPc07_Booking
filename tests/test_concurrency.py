"""Проверка фактической конкурентной защиты BookingService
через реальный PostgreSQL.

Этот файл НЕ изменяет production-код. Он проверяет, что реализация Stage 2.5
(PostgresDriver.transaction + pg_advisory_xact_lock + детерминированный порядок
блокировок + транзакционные проверки) корректно работает под реальной
конкуренцией, а не на mock-объектах.

Запуск:
    python -m tests.test_concurrency

Тесты используют только реальные PostgreSQL, PostgresDriver, BookingService и
модели User / Table / Booking. Никаких mock, monkeypatch, подмены transaction()
или pg_advisory_xact_lock, SQLite или fake database.

Для каждой конкурентной операции создаются НЕЗАВИСИМЫЕ PostgresDriver и
BookingService, чтобы операции действительно выполнялись через разные
соединения PostgreSQL.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Callable, TypeVar

from backend import BookingService
from models.booking import Booking
from models.table import Table
from models.user import User
from postgres_driver import PostgresDriver
from tests.test_cleanup import TestCleanupTracker
from tests.test_config import create_test_driver
from tests.test_data import unique_phone, unique_table_number


T = TypeVar("T")


def _require_id(value: int | None, entity_name: str) -> int:
    """Проверить, что созданная сущность получила ID из базы данных."""
    if value is None:
        raise AssertionError(
            f"{entity_name} создана без ID из базы данных"
        )
    return value


# ---------------------------------------------------------------------------
# Уникальные идентификаторы тестовых данных (tests/test_data.py)
# ---------------------------------------------------------------------------
def _phone() -> str:
    """Сгенерировать уникальный телефон для тестового пользователя."""
    return unique_phone()


def _table_number() -> str:
    """Сгенерировать уникальный номер для тестового столика."""
    return unique_table_number("C")


# ---------------------------------------------------------------------------
# Подключение и сервисы
# ---------------------------------------------------------------------------
def _make_service(drivers: list[PostgresDriver]) -> BookingService:
    """Создать независимый PostgresDriver + BookingService.

    Созданный драйвер регистрируется в списке ``drivers``, чтобы его можно
    было закрыть по завершении теста.
    """
    driver = create_test_driver()
    drivers.append(driver)
    return BookingService(driver)


def _close_all_drivers(drivers: list[PostgresDriver]) -> None:
    """Закрыть все созданные драйверы, не скрывая ошибки полностью."""
    for driver in drivers:
        try:
            driver.close()
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] не удалось закрыть драйвер: {exc}")
    drivers.clear()


# ---------------------------------------------------------------------------
# Вспомогательный запуск двух операций одновременно
# ---------------------------------------------------------------------------
def _run_two(
    fn_a: Callable[[], T],
    fn_b: Callable[[], T],
    timeout: float = 10.0,
) -> tuple[T | None, BaseException | None, T | None, BaseException | None, bool]:
    """Выполнить две операции одновременно в двух потоках через Barrier(2).

    Возвращает:
        (result_a, error_a, result_b, error_b, timed_out)

    Если хотя бы один поток не завершился за ``timeout``, ``timed_out`` равен
    True — это индикатор зависания/deadlock.
    """
    barrier = threading.Barrier(2)
    results: list[T | None] = [None, None]
    errors: list[BaseException | None] = [None, None]

    def worker(idx: int, fn: Callable[[], T]) -> None:
        try:
            barrier.wait(timeout=timeout)
            results[idx] = fn()
        except BaseException as exc:  # noqa: BLE001
            errors[idx] = exc

    thread_a = threading.Thread(target=worker, args=(0, fn_a), daemon=True)
    thread_b = threading.Thread(target=worker, args=(1, fn_b), daemon=True)
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=timeout)
    thread_b.join(timeout=timeout)

    timed_out = thread_a.is_alive() or thread_b.is_alive()
    return results[0], errors[0], results[1], errors[1], timed_out


def _count_bookings_for_table(
    service: BookingService,
    table_id: int,
) -> int:
    """Посчитать количество бронирований конкретного столика через backend."""
    return sum(
        1
        for booking in service.get_all_bookings()
        if booking.table_id == table_id
    )


# ---------------------------------------------------------------------------
# Тест 1 — два одновременных бронирования одного столика (race condition)
# ---------------------------------------------------------------------------
def test_concurrent_same_table() -> None:
    """Ровно одно из двух конкурирующих бронирований должно создаться.

    Сценарий: два разных пользователя одновременно (Barrier) создают
    бронирование на один и тот же столик и один и тот же интервал.
    Реализация Stage 2.5 обязана сериализовать операции через
    pg_advisory_xact_lock(table_id) и транзакционную проверку overlap,
    поэтому второе бронирование должно получить ValueError.
    """
    print("\n=== TEST 1: concurrent create on same table (race condition) ===")

    drivers: list[PostgresDriver] = []
    setup = _make_service(drivers)
    tracker = TestCleanupTracker()

    user_a = setup.create_user(User(None, "CC User A", _phone()))
    user_a_id = _require_id(user_a.id, "User A")
    tracker.register_user(user_a_id)

    user_b = setup.create_user(User(None, "CC User B", _phone()))
    user_b_id = _require_id(user_b.id, "User B")
    tracker.register_user(user_b_id)

    table = setup.create_table(
        Table(None, _table_number(), 4, "CC Test")
    )
    table_id = _require_id(table.id, "Table")
    tracker.register_table(table_id)

    start = datetime(2026, 12, 1, 18, 0)
    end = datetime(2026, 12, 1, 20, 0)

    svc1 = _make_service(drivers)
    svc2 = _make_service(drivers)

    try:
        def make_a() -> Booking:
            return svc1.create_booking(
                Booking(None, user_a_id, table_id, 2, start, end)
            )

        def make_b() -> Booking:
            return svc2.create_booking(
                Booking(None, user_b_id, table_id, 2, start, end)
            )

        res_a, err_a, res_b, err_b, timed_out = _run_two(make_a, make_b)

        for result in (res_a, res_b):
            if result is not None:
                result_id = _require_id(result.id, "Concurrent booking")
                tracker.register_booking(result_id)

        assert not timed_out, (
            "Операция зависла (таймаут) вместо корректного завершения"
        )

        outcomes = [(res_a, err_a), (res_b, err_b)]
        successes = [result for result, error in outcomes if result is not None]
        failures = [error for result, error in outcomes if error is not None]

        assert len(successes) == 1, (
            f"Ожидался ровно 1 успех, получено {len(successes)}; "
            f"ошибки: {[repr(error) for error in failures]}"
        )
        assert len(failures) == 1, (
            f"Ожидался ровно 1 отказ, получено {len(failures)}; "
            f"успехи: {successes}"
        )
        assert isinstance(failures[0], ValueError), (
            f"Ожидался ValueError (пересечение), получен "
            f"{type(failures[0]).__name__}: {failures[0]!r}"
        )

        count = _count_bookings_for_table(setup, table_id)
        assert count == 1, (
            f"В БД должно быть ровно 1 бронирование на этот столик, "
            f"найдено {count} — это race condition"
        )

        print("PASS")

    finally:
        try:
            cleanup_errors = tracker.cleanup(drivers[0])
            for error in cleanup_errors:
                print(f"  [cleanup error] {error}")
        finally:
            _close_all_drivers(drivers)


# ---------------------------------------------------------------------------
# Тест 2 — соседние интервалы должны успешно создаваться
# ---------------------------------------------------------------------------
def test_adjacent_intervals() -> None:
    """Проверка, что полуоткрытые интервалы [18:00,20:00) и [20:00,22:00)
    не считаются пересечением и оба бронирования создаются успешно."""
    print("\n=== TEST 2: adjacent intervals allowed ===")

    drivers: list[PostgresDriver] = []
    setup = _make_service(drivers)
    tracker = TestCleanupTracker()

    user = setup.create_user(User(None, "CC User Adj", _phone()))
    user_id = _require_id(user.id, "Adjacent user")
    tracker.register_user(user_id)

    table = setup.create_table(
        Table(None, _table_number(), 4, "CC Adj")
    )
    table_id = _require_id(table.id, "Adjacent table")
    tracker.register_table(table_id)

    try:
        b1 = setup.create_booking(
            Booking(
                None,
                user_id,
                table_id,
                2,
                datetime(2026, 12, 2, 18, 0),
                datetime(2026, 12, 2, 20, 0),
            )
        )
        print(f"  booking1 = {b1}")
        b1_id = _require_id(b1.id, "First booking")
        tracker.register_booking(b1_id)
        print("  booking1 PASS")

        b2 = setup.create_booking(
            Booking(
                None,
                user_id,
                table_id,
                2,
                datetime(2026, 12, 2, 20, 0),
                datetime(2026, 12, 2, 22, 0),
            )
        )
        print(f"  booking2 = {b2}")
        b2_id = _require_id(b2.id, "Second booking")
        tracker.register_booking(b2_id)
        print("  booking2 PASS")

        print("PASS")

    finally:
        try:
            cleanup_errors = tracker.cleanup(drivers[0])
            for error in cleanup_errors:
                print(f"  [cleanup error] {error}")
        finally:
            _close_all_drivers(drivers)


# ---------------------------------------------------------------------------
# Тест 3 — конкурентный перенос бронирований между двумя столиками (deadlock)
# ---------------------------------------------------------------------------
def test_concurrent_swap_between_tables() -> None:
    """Проверка отсутствия deadlock при встречном переносе двух бронирований.

    booking1 на столике A (18:00-20:00), booking2 на столике B (20:00-22:00).
    Одновременно: booking1 A->B, booking2 B->A. Интервалы соседние, поэтому
    overlap-конфликта нет. Обе транзакции должны брать advisory locks на
    {A, B} в одинаковом (отсортированном) порядке, что исключает deadlock.
    """
    print("\n=== TEST 3: concurrent swap between two tables (deadlock) ===")

    drivers: list[PostgresDriver] = []
    setup = _make_service(drivers)
    tracker = TestCleanupTracker()

    user_1 = setup.create_user(User(None, "CC User 1", _phone()))
    user_1_id = _require_id(user_1.id, "User 1")
    tracker.register_user(user_1_id)

    user_2 = setup.create_user(User(None, "CC User 2", _phone()))
    user_2_id = _require_id(user_2.id, "User 2")
    tracker.register_user(user_2_id)

    table_a = setup.create_table(
        Table(None, _table_number(), 4, "CC Swap")
    )
    table_a_id = _require_id(table_a.id, "Table A")
    tracker.register_table(table_a_id)

    table_b = setup.create_table(
        Table(None, _table_number(), 4, "CC Swap")
    )
    table_b_id = _require_id(table_b.id, "Table B")
    tracker.register_table(table_b_id)

    booking_1 = setup.create_booking(
        Booking(
            None,
            user_1_id,
            table_a_id,
            2,
            datetime(2026, 12, 3, 18, 0),
            datetime(2026, 12, 3, 20, 0),
        )
    )
    booking_1_id = _require_id(booking_1.id, "Booking 1")
    tracker.register_booking(booking_1_id)

    booking_2 = setup.create_booking(
        Booking(
            None,
            user_2_id,
            table_b_id,
            2,
            datetime(2026, 12, 3, 20, 0),
            datetime(2026, 12, 3, 22, 0),
        )
    )
    booking_2_id = _require_id(booking_2.id, "Booking 2")
    tracker.register_booking(booking_2_id)

    svc1 = _make_service(drivers)
    svc2 = _make_service(drivers)

    try:
        def swap_1() -> Booking:
            current = svc1.get_booking(booking_1_id)
            assert current is not None
            return svc1.update_booking(
                Booking(
                    booking_1_id,
                    current.user_id,
                    table_b_id,
                    current.guests,
                    current.start_time,
                    current.end_time,
                )
            )

        def swap_2() -> Booking:
            current = svc2.get_booking(booking_2_id)
            assert current is not None
            return svc2.update_booking(
                Booking(
                    booking_2_id,
                    current.user_id,
                    table_a_id,
                    current.guests,
                    current.start_time,
                    current.end_time,
                )
            )

        res_a, err_a, res_b, err_b, timed_out = _run_two(swap_1, swap_2)

        assert not timed_out, (
            "Обнаружено зависание/deadlock: операция не завершилась за таймаут"
        )
        assert err_a is None, (
            f"Перенос booking1 завершился ошибкой: "
            f"{type(err_a).__name__}: {err_a!r}"
        )
        assert err_b is None, (
            f"Перенос booking2 завершился ошибкой: "
            f"{type(err_b).__name__}: {err_b!r}"
        )

        final_1 = setup.get_booking(booking_1_id)
        final_2 = setup.get_booking(booking_2_id)
        assert final_1 is not None and final_2 is not None

        assert final_1.table_id == table_b_id, (
            f"booking1 должен быть на столике B "
            f"({table_b_id}), фактически {final_1.table_id}"
        )
        assert final_2.table_id == table_a_id, (
            f"booking2 должен быть на столике A "
            f"({table_a_id}), фактически {final_2.table_id}"
        )

        print("PASS")

    finally:
        try:
            cleanup_errors = tracker.cleanup(drivers[0])
            for error in cleanup_errors:
                print(f"  [cleanup error] {error}")
        finally:
            _close_all_drivers(drivers)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def _run_test(name: str, fn: Callable[[], None]) -> bool:
    """Выполнить один тест, вернуть True при успехе."""
    try:
        fn()
        return True
    except AssertionError as exc:
        print(f"FAIL: {name}: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {name}: {type(exc).__name__}: {exc}")
        return False


def main() -> None:
    results: dict[str, bool] = {}

    results["TEST 1 (race condition)"] = _run_test(
        "concurrent_same_table", test_concurrent_same_table
    )
    results["TEST 2 (adjacent)"] = _run_test(
        "adjacent_intervals", test_adjacent_intervals
    )
    results["TEST 3 (deadlock)"] = _run_test(
        "concurrent_swap_between_tables", test_concurrent_swap_between_tables
    )

    print("\n" + "=" * 60)
    for name, ok in results.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    print("=" * 60)

    all_pass = all(results.values())
    if all_pass:
        print("STAGE 2.5 CONCURRENCY TEST: PASS")
    else:
        print("STAGE 2.5 CONCURRENCY TEST: FAIL")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
