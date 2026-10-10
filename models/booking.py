"""Модель бронирования столика."""

from datetime import datetime

from typing import Self


class Booking:
    """Бронирование столика пользователем.

    Attributes:
        id: Уникальный идентификатор бронирования (генерируется БД).
        user_id: Идентификатор пользователя, создавшего бронирование.
        table_id: Идентификатор столика.
        guests: Количество гостей (обязательное, больше нуля).
        start_time: Время начала бронирования.
        end_time: Время окончания бронирования.
        created_at: Время создания записи в БД (устанавливается автоматически).
    """

    def __init__(
        self,
        id: int | None,
        user_id: int,
        table_id: int,
        guests: int,
        start_time: datetime,
        end_time: datetime,
        created_at: datetime | None = None,
    ) -> None:
        """Инициализировать бронирование.

        Args:
            id: Идентификатор бронирования или None для нового бронирования.
            user_id: Идентификатор пользователя.
            table_id: Идентификатор столика.
            guests: Количество гостей.
            start_time: Время начала.
            end_time: Время окончания.
            created_at: Время создания или None.
        """
        self.id = id
        self.user_id = user_id
        self.table_id = table_id
        self.guests = guests
        self.start_time = start_time
        self.end_time = end_time
        self.created_at = created_at

    @classmethod
    def from_row(cls, row: dict) -> Self:
        """Создать объект Booking из строки результата запроса БД.

        Args:
            row: Словарь с колонками 'id', 'user_id', 'table_id',
                 'guests', 'start_time', 'end_time', 'created_at'.

        Returns:
            Экземпляр Booking.
        """
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            table_id=row["table_id"],
            guests=row["guests"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            created_at=row.get("created_at"),
        )

    def validate(self) -> None:
        """Проверить локальные ограничения модели.

        Raises:
            ValueError: Если количество гостей меньше нуля или
                время начала не раньше времени окончания.
        """
        if self.guests <= 0:
            raise ValueError("Количество гостей должно быть больше нуля")
        if self.start_time >= self.end_time:
            raise ValueError("Время начала должно быть раньше времени окончания")

    def __repr__(self) -> str:
        return (
            f"Booking(id={self.id}, user_id={self.user_id}, "
            f"table_id={self.table_id}, guests={self.guests}, "
            f"start_time={self.start_time}, end_time={self.end_time})"
        )
