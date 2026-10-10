"""Слой бизнес-логики системы бронирования столиков.

Модуль `backend.py` содержит класс `BookingService`, который реализует
операции CRUD для предметных сущностей приложения и работает с PostgreSQL
исключительно через публичный API `PostgresDriver`.

Здесь нет SQL-конкатенации, кода пользовательского интерфейса и бизнес-правил
в драйвере — каждый слой отвечает за свою часть задачи.
"""

from psycopg2.errors import UniqueViolation

from models.booking import Booking
from models.table import Table
from models.user import User
from postgres_driver import PostgresDriver


class BookingService:
    """Сервис бизнес-логики системы бронирования.

    Отвечает за валидацию входных данных, выполнение CRUD-операций и
    обработку бизнес-ошибок. Все SQL-запросы параметризованы.

    Атрибуты:
        _driver: Экземпляр драйвера PostgreSQL для доступа к БД.
    """

    def __init__(self, driver: PostgresDriver) -> None:
        """Инициализировать сервис.

        Аргументы:
            driver: Экземпляр `PostgresDriver` для работы с базой данных.
        """
        self._driver = driver

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    def create_user(self, user: User) -> User:
        """Создать пользователя.

        Выполняет локальную валидацию модели, вставляет запись и возвращает
        объект пользователя с проставленным идентификатором из базы данных.

        Аргументы:
            user: Объект пользователя. Поле `id` должно быть `None`.

        Возвращает:
            Тот же объект `user` с заполненным атрибутом `id`.

        Исключения:
            ValueError: Если данные пользователя некорректны
                (пустые имя или телефон).
            RuntimeError: Если телефон уже занят другим пользователем
                (нарушение уникальности).
        """
        user.validate()

        insert_sql = (
            "INSERT INTO users (name, phone) VALUES (%s, %s) RETURNING id"
        )

        try:
            row = self._driver.fetch_one(insert_sql, (user.name, user.phone))
        except UniqueViolation as exc:
            raise RuntimeError(
                f"Пользователь с телефоном {user.phone!r} уже существует"
            ) from exc

        if row is None:
            raise RuntimeError(
                "Не удалось получить идентификатор созданного пользователя"
            )

        user.id = row["id"]
        return user

    def get_user(self, user_id: int) -> User | None:
        """Получить пользователя по идентификатору.

        Аргументы:
            user_id: Идентификатор пользователя.

        Возвращает:
            Объект `User` либо `None`, если пользователь не найден.
        """
        row = self._driver.fetch_one(
            "SELECT id, name, phone FROM users WHERE id = %s",
            (user_id,),
        )
        return User.from_row(row) if row is not None else None

    def get_all_users(self) -> list[User]:
        """Получить всех пользователей.

        Возвращает:
            Список объектов `User` в порядке возрастания идентификаторов.
        """
        rows = self._driver.fetch_all(
            "SELECT id, name, phone FROM users ORDER BY id"
        )
        return [User.from_row(row) for row in rows]

    def update_user(self, user: User) -> User:
        """Обновить существующего пользователя.

        Аргументы:
            user: Объект пользователя с заполненным `id` и новыми значениями
                `name` и `phone`.

        Возвращает:
            Тот же объект `user`.

        Исключения:
            ValueError: Если данные некорректны или `id` равен `None`.
            LookupError: Если пользователь с таким `id` не найден.
            RuntimeError: Если новый телефон уже занят другим пользователем.
        """
        if user.id is None:
            raise ValueError("Для обновления пользователя требуется id")
        user.validate()

        update_sql = (
            "UPDATE users SET name = %s, phone = %s WHERE id = %s "
            "RETURNING id"
        )

        try:
            row = self._driver.fetch_one(
                update_sql, (user.name, user.phone, user.id)
            )
        except UniqueViolation as exc:
            raise RuntimeError(
                f"Телефон {user.phone!r} уже занят другим пользователем"
            ) from exc

        if row is None:
            raise LookupError(f"Пользователь с id={user.id} не найден")

        return user

    def delete_user(self, user_id: int) -> bool:
        """Удалить пользователя по идентификатору.

        Аргументы:
            user_id: Идентификатор пользователя.

        Возвращает:
            True — если запись действительно была удалена;
            False — если пользователя с таким id не существовало.
        """
        row = self._driver.fetch_one(
            "DELETE FROM users WHERE id = %s RETURNING id",
            (user_id,),
        )
        return row is not None

    # ------------------------------------------------------------------
    # Table CRUD
    # ------------------------------------------------------------------

    def create_table(self, table: Table) -> Table:
        """Создать столик.

        Выполняет локальную валидацию модели, вставляет запись и возвращает
        объект столика, собранный из данных, подтверждённых базой данных.

        Аргументы:
            table: Объект столика. Поле `id` должно быть `None`.

        Возвращает:
            Новый объект `Table` с идентификатором из базы данных.

        Исключения:
            ValueError: Если номер пустой или вместимость не больше нуля.
            RuntimeError: Если номер столика уже занят (нарушение уникальности
                `number`) либо вставка неожиданно не вернула созданную запись.
        """
        table.validate()

        insert_sql = (
            "INSERT INTO restaurant_tables (number, capacity, location) "
            "VALUES (%s, %s, %s) "
            "RETURNING id, number, capacity, location"
        )

        try:
            row = self._driver.fetch_one(
                insert_sql, (table.number, table.capacity, table.location)
            )
        except UniqueViolation as exc:
            raise RuntimeError(
                f"Столик с номером {table.number!r} уже существует"
            ) from exc

        if row is None:
            raise RuntimeError(
                "Не удалось получить созданный столик из базы данных"
            )

        return Table.from_row(row)

    def get_table(self, table_id: int) -> Table | None:
        """Получить столик по идентификатору.

        Аргументы:
            table_id: Идентификатор столика.

        Возвращает:
            Объект `Table` либо `None`, если столик не найден.
        """
        row = self._driver.fetch_one(
            "SELECT id, number, capacity, location "
            "FROM restaurant_tables WHERE id = %s",
            (table_id,),
        )
        return Table.from_row(row) if row is not None else None

    def get_all_tables(self) -> list[Table]:
        """Получить все столики.

        Возвращает:
            Список объектов `Table` в порядке возрастания идентификаторов.
            Если столиков нет — пустой список.
        """
        rows = self._driver.fetch_all(
            "SELECT id, number, capacity, location "
            "FROM restaurant_tables ORDER BY id"
        )
        return [Table.from_row(row) for row in rows]

    def update_table(self, table: Table) -> Table:
        """Обновить существующий столик.

        Аргументы:
            table: Объект столика с заполненным `id` и новыми значениями
                `number`, `capacity` и `location`.

        Возвращает:
            Объект `Table`, собранный из данных, подтверждённых базой данных.

        Исключения:
            ValueError: Если `id` равен `None` либо данные столика
                некорректны.
            LookupError: Если столик с таким `id` не найден.
            RuntimeError: Если новый номер уже занят другим столиком
                (нарушение уникальности `number`).
        """
        if table.id is None:
            raise ValueError("Для обновления столика требуется id")
        table.validate()

        update_sql = (
            "UPDATE restaurant_tables "
            "SET number = %s, capacity = %s, location = %s "
            "WHERE id = %s "
            "RETURNING id, number, capacity, location"
        )

        try:
            row = self._driver.fetch_one(
                update_sql,
                (table.number, table.capacity, table.location, table.id),
            )
        except UniqueViolation as exc:
            raise RuntimeError(
                f"Номер {table.number!r} уже занят другим столиком"
            ) from exc

        if row is None:
            raise LookupError(f"Столик с id={table.id} не найден")

        return Table.from_row(row)

    def delete_table(self, table_id: int) -> bool:
        """Удалить столик по идентификатору.

        Аргументы:
            table_id: Идентификатор столика.

        Возвращает:
            True — если запись действительно была удалена;
            False — если столика с таким id не существовало.
        """
        row = self._driver.fetch_one(
            "DELETE FROM restaurant_tables WHERE id = %s RETURNING id",
            (table_id,),
        )
        return row is not None

    # ------------------------------------------------------------------
    # Booking CRUD
    # ------------------------------------------------------------------

    def _ensure_booking_exists(self, booking_id: int) -> None:
        """Проверить существование бронирования.

        Аргументы:
            booking_id: Идентификатор бронирования.

        Исключения:
            LookupError: Если бронирование с таким id не найдено.
        """
        row = self._driver.fetch_one(
            "SELECT id FROM bookings WHERE id = %s",
            (booking_id,),
        )
        if row is None:
            raise LookupError(f"Бронирование с id={booking_id} не найдено")

    def _ensure_user_exists(self, user_id: int) -> None:
        """Проверить существование пользователя.

        Аргументы:
            user_id: Идентификатор пользователя.

        Исключения:
            LookupError: Если пользователь с таким id не найден.
        """
        row = self._driver.fetch_one(
            "SELECT id FROM users WHERE id = %s",
            (user_id,),
        )
        if row is None:
            raise LookupError(f"Пользователь с id={user_id} не найден")

    def _ensure_capacity(self, table_id: int, guests: int) -> None:
        """Проверить существование столика и допустимость количества гостей.

        Аргументы:
            table_id: Идентификатор столика.
            guests: Количество гостей.

        Исключения:
            LookupError: Если столик с таким id не найден.
            ValueError: Если количество гостей превышает вместимость столика.
        """
        row = self._driver.fetch_one(
            "SELECT id, capacity FROM restaurant_tables WHERE id = %s",
            (table_id,),
        )
        if row is None:
            raise LookupError(f"Столик с id={table_id} не найден")

        capacity = row["capacity"]
        if guests > capacity:
            raise ValueError(
                f"Количество гостей ({guests}) превышает "
                f"вместимость столика ({capacity})"
            )

    def _ensure_no_overlap(
        self, booking: Booking, exclude_id: int | None = None
    ) -> None:
        """Проверить отсутствие пересекающихся бронирований этого столика.

        Интервалы считаются полуоткрытыми `[start_time, end_time)`, поэтому
        соседние бронирования вида 18:00–20:00 и 20:00–22:00 пересечением
        не являются.

        Аргументы:
            booking: Проверяемое бронирование.
            exclude_id: Идентификатор бронирования, которое нужно исключить из
                проверки (для обновления текущего бронирования).

        Исключения:
            ValueError: Если для столика найдено пересекающееся бронирование.
        """
        if exclude_id is None:
            sql = (
                "SELECT id FROM bookings "
                "WHERE table_id = %s AND start_time < %s AND end_time > %s "
                "LIMIT 1"
            )
            params: tuple = (
                booking.table_id,
                booking.end_time,
                booking.start_time,
            )
        else:
            sql = (
                "SELECT id FROM bookings "
                "WHERE table_id = %s AND id <> %s "
                "AND start_time < %s AND end_time > %s "
                "LIMIT 1"
            )
            params = (
                booking.table_id,
                exclude_id,
                booking.end_time,
                booking.start_time,
            )

        row = self._driver.fetch_one(sql, params)
        if row is not None:
            raise ValueError(
                f"Столик с id={booking.table_id} уже забронирован "
                f"на указанное время"
            )

    # ------------------------------------------------------------------
    # Cursor-based helpers for transactional (race-safe) operations
    # ------------------------------------------------------------------

    @staticmethod
    def _lock_table_xact(cursor, table_id: int) -> None:
        """Получить advisory xact блокировку на столик.

        Блокировка автоматически освобождается PostgreSQL после
        COMMIT или ROLLBACK текущей транзакции.

        Args:
            cursor: Активный курсор в рамках транзакции.
            table_id: Идентификатор столика для блокировки.
        """
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (table_id,),
        )

    @staticmethod
    def _lock_tables_xact(cursor, table_ids: set[int]) -> None:
        """Получить advisory xact блокировки на набор столиков.

        Блокировки берутся в детерминированном порядке
        (по возрастанию table_id) для исключения deadlock.

        Args:
            cursor: Активный курсор в рамках транзакции.
            table_ids: Множество идентификаторов столиков.
        """
        for table_id in sorted(table_ids):
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (table_id,),
            )

    @staticmethod
    def _ensure_user_exists_xact(cursor, user_id: int) -> None:
        """Проверить существование пользователя через cursor.

        Args:
            cursor: Активный курсор в рамках транзакции.
            user_id: Идентификатор пользователя.

        Raises:
            LookupError: Если пользователь не найден.
        """
        cursor.execute(
            "SELECT id FROM users WHERE id = %s",
            (user_id,),
        )
        if cursor.fetchone() is None:
            raise LookupError(f"Пользователь с id={user_id} не найден")

    @staticmethod
    def _ensure_capacity_xact(cursor, table_id: int, guests: int) -> None:
        """Проверить столик и вместимость через cursor.

        Args:
            cursor: Активный курсор в рамках транзакции.
            table_id: Идентификатор столика.
            guests: Количество гостей.

        Raises:
            LookupError: Если столик не найден.
            ValueError: Если гости превышают вместимость.
        """
        cursor.execute(
            "SELECT id, capacity FROM restaurant_tables WHERE id = %s",
            (table_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Столик с id={table_id} не найден")

        capacity = row["capacity"]
        if guests > capacity:
            raise ValueError(
                f"Количество гостей ({guests}) превышает "
                f"вместимость столика ({capacity})"
            )

    @staticmethod
    def _ensure_no_overlap_xact(
        cursor,
        table_id: int,
        start_time,
        end_time,
        exclude_id: int | None = None,
    ) -> None:
        """Проверить отсутствие пересечений через cursor.

        Args:
            cursor: Активный курсор в рамках транзакции.
            table_id: Идентификатор столика.
            start_time: Начало интервала.
            end_time: Конец интервала.
            exclude_id: Идентификатор исключаемого бронирования.

        Raises:
            ValueError: Если найдено пересекающееся бронирование.
        """
        if exclude_id is None:
            sql = (
                "SELECT id FROM bookings "
                "WHERE table_id = %s AND start_time < %s AND end_time > %s "
                "LIMIT 1"
            )
            params: tuple = (table_id, end_time, start_time)
        else:
            sql = (
                "SELECT id FROM bookings "
                "WHERE table_id = %s AND id <> %s "
                "AND start_time < %s AND end_time > %s "
                "LIMIT 1"
            )
            params = (table_id, exclude_id, end_time, start_time)

        cursor.execute(sql, params)
        if cursor.fetchone() is not None:
            raise ValueError(
                f"Столик с id={table_id} уже забронирован "
                f"на указанное время"
            )

    def create_booking(self, booking: Booking) -> Booking:
        """Создать бронирование.

        Выполняет локальную валидацию модели, вставляет запись и возвращает
        объект бронирования, собранный из данных, подтверждённых базой данных.
        Поле `created_at` устанавливается PostgreSQL автоматически.

        Аргументы:
            booking: Объект бронирования. Поле `id` должно быть `None`.

        Возвращает:
            Новый объект `Booking` с идентификатором из базы данных.

        Исключения:
            ValueError: Если количество гостей не больше нуля либо время
                начала не раньше времени окончания, либо количество гостей
                превышает вместимость столика, либо столик уже забронирован
                на пересекающееся время.
            LookupError: Если пользователь или столик с указанными id
                не найдены.
            RuntimeError: Если вставка неожиданно не вернула созданную запись.
        """
        booking.validate()

        insert_sql = (
            "INSERT INTO bookings "
            "(user_id, table_id, guests, start_time, end_time) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, user_id, table_id, guests, start_time, end_time, "
            "created_at"
        )

        with self._driver.transaction() as conn:
            with conn.cursor() as cursor:
                self._lock_table_xact(cursor, booking.table_id)
                self._ensure_user_exists_xact(cursor, booking.user_id)
                self._ensure_capacity_xact(
                    cursor, booking.table_id, booking.guests
                )
                self._ensure_no_overlap_xact(
                    cursor,
                    booking.table_id,
                    booking.start_time,
                    booking.end_time,
                )
                cursor.execute(
                    insert_sql,
                    (
                        booking.user_id,
                        booking.table_id,
                        booking.guests,
                        booking.start_time,
                        booking.end_time,
                    ),
                )
                row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "Не удалось получить созданное бронирование из базы данных"
            )

        return Booking.from_row(row)

    def get_booking(self, booking_id: int) -> Booking | None:
        """Получить бронирование по идентификатору.

        Аргументы:
            booking_id: Идентификатор бронирования.

        Возвращает:
            Объект `Booking` либо `None`, если бронирование не найдено.
        """
        row = self._driver.fetch_one(
            "SELECT id, user_id, table_id, guests, start_time, end_time, "
            "created_at FROM bookings WHERE id = %s",
            (booking_id,),
        )
        return Booking.from_row(row) if row is not None else None

    def get_all_bookings(self) -> list[Booking]:
        """Получить все бронирования.

        Возвращает:
            Список объектов `Booking` в порядке возрастания идентификаторов.
            Если бронирований нет — пустой список.
        """
        rows = self._driver.fetch_all(
            "SELECT id, user_id, table_id, guests, start_time, end_time, "
            "created_at FROM bookings ORDER BY id"
        )
        return [Booking.from_row(row) for row in rows]

    def update_booking(self, booking: Booking) -> Booking:
        """Обновить существующее бронирование.

        Обновляет запись и возвращает объект, собранный из данных,
        подтверждённых базой данных. Поле `created_at` остаётся исходным
        значением из базы данных и не изменяется этим методом.

        Аргументы:
            booking: Объект бронирования с заполненным `id`.

        Возвращает:
            Обновлённый объект `Booking`, собранный из данных запроса UPDATE.

        Исключения:
            LookupError: Если бронирование с таким `id` не найдено.
            ValueError: Если модель не проходит локальную валидацию,
                если переданный `id` равен `None`, если количество гостей
                превышает вместимость столика, либо если новый интервал
                пересекается с другим активным бронированием столика.
                Собственное бронирование с тем же `id` из проверки исключается.
            RuntimeError: Если запрос UPDATE неожиданно не вернул ни одной
                обновлённой строки.
        """
        if booking.id is None:
            raise ValueError("Поле 'id' обязательно для обновления")

        booking.validate()

        update_sql = (
            "UPDATE bookings "
            "SET user_id = %s, table_id = %s, guests = %s, "
            "start_time = %s, end_time = %s "
            "WHERE id = %s "
            "RETURNING id, user_id, table_id, guests, start_time, end_time, "
            "created_at"
        )

        with self._driver.transaction() as conn:
            with conn.cursor() as cursor:
                # Читаем существующую запись для получения старого table_id.
                cursor.execute(
                    "SELECT table_id FROM bookings WHERE id = %s",
                    (booking.id,),
                )
                existing_row = cursor.fetchone()
                if existing_row is None:
                    raise LookupError(
                        f"Бронирование с id={booking.id} не найдено"
                    )

                old_table_id: int = existing_row["table_id"]

                # Берём блокировки на все затронутые столики
                # в детерминированном порядке (sorted).
                affected_tables = {old_table_id, booking.table_id}
                self._lock_tables_xact(cursor, affected_tables)

                self._ensure_user_exists_xact(cursor, booking.user_id)
                self._ensure_capacity_xact(
                    cursor, booking.table_id, booking.guests
                )
                self._ensure_no_overlap_xact(
                    cursor,
                    booking.table_id,
                    booking.start_time,
                    booking.end_time,
                    exclude_id=booking.id,
                )

                cursor.execute(
                    update_sql,
                    (
                        booking.user_id,
                        booking.table_id,
                        booking.guests,
                        booking.start_time,
                        booking.end_time,
                        booking.id,
                    ),
                )
                row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Бронирование с id={booking.id} не найдено"
            )

        return Booking.from_row(row)

    def delete_booking(self, booking_id: int) -> bool:
        """Удалить бронирование по идентификатору.

        Аргументы:
            booking_id: Идентификатор бронирования.

        Возвращает:
            True — если запись действительно была удалена;
            False — если бронирования с таким id не существовало.
        """
        row = self._driver.fetch_one(
            "DELETE FROM bookings WHERE id = %s RETURNING id",
            (booking_id,),
        )
        return row is not None

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def check_table_availability(
        self,
        table_id: int,
        guests: int,
        start_time,
        end_time,
    ) -> bool:
        """Проверить доступность столика для заданного временного интервала.

        Проверяет:
        * корректность временного интервала;
        * корректность количества гостей;
        * существование столика;
        * вместимость столика;
        * отсутствие пересекающихся бронирований.

        Интервалы считаются полуоткрытыми ``[start_time, end_time)``, поэтому
        соседние бронирования вида 18:00–20:00 и 20:00–22:00 не считаются
        пересечением.

        Аргументы:
            table_id: Идентификатор столика.
            guests: Количество гостей.
            start_time: Время начала интервала.
            end_time: Время окончания интервала.

        Возвращает:
            ``True`` — столик доступен для указанного интервала и количества
            гостей; ``False`` — столик недоступен по любой причине
            (не существует, недостаточная вместимость, некорректный интервал,
            некорректное количество гостей, пересекающееся бронирование).

        Примечание:
            Метод не изменяет состояние БД и не создаёт транзакцию.
            Он отвечает только на вопрос «доступен ли стол».
        """
        # 1. Валидация временного интервала
        if start_time >= end_time:
            return False

        # 2. Валидация количества гостей
        if guests <= 0:
            return False

        # 3. Существование столика и вместимость
        try:
            self._ensure_capacity(table_id, guests)
        except (LookupError, ValueError):
            return False

        # 4. Проверка пересечения с существующими бронированиями
        sql = (
            "SELECT id FROM bookings "
            "WHERE table_id = %s AND start_time < %s AND end_time > %s "
            "LIMIT 1"
        )
        params: tuple = (table_id, end_time, start_time)
        row = self._driver.fetch_one(sql, params)
        return row is None
