"""Модель столика ресторана."""

from typing import Self


class Table:
    """Столик ресторана.

    SQL-имя таблицы в PostgreSQL: restaurant_tables.

    Attributes:
        id: Уникальный идентификатор столика (генерируется БД).
        number: Номер столика (обязательный, уникальный на уровне БД).
        capacity: Вместимость столика (обязательная, больше нуля).
        location: Описание расположения столика (необязательное).
    """

    def __init__(
        self,
        id: int | None,
        number: str,
        capacity: int,
        location: str | None = None,
    ) -> None:
        """Инициализировать столик.

        Args:
            id: Идентификатор столика или None для нового столика.
            number: Номер столика.
            capacity: Вместимость столика.
            location: Описание расположения или None.
        """
        self.id = id
        self.number = number
        self.capacity = capacity
        self.location = location

    @classmethod
    def from_row(cls, row: dict) -> Self:
        """Создать объект Table из строки результата запроса БД.

        Args:
            row: Словарь с колонками 'id', 'number', 'capacity', 'location'.

        Returns:
            Экземпляр Table.
        """
        return cls(
            id=row["id"],
            number=row["number"],
            capacity=row["capacity"],
            location=row.get("location"),
        )

    def validate(self) -> None:
        """Проверить локальные ограничения модели.

        Raises:
            ValueError: Если номер пустой или вместимость не больше нуля.
        """
        if not self.number or not self.number.strip():
            raise ValueError("Номер столика не может быть пустым")
        if self.capacity <= 0:
            raise ValueError("Вместимость столика должна быть больше нуля")

    def __repr__(self) -> str:
        return (
            f"Table(id={self.id}, number={self.number!r}, "
            f"capacity={self.capacity}, location={self.location!r})"
        )
