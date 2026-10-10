"""Модель пользователя системы бронирования."""

from typing import Self


class User:
    """Пользователь ресторана.

    Attributes:
        id: Уникальный идентификатор пользователя (генерируется БД).
        name: Имя пользователя (обязательное, не пустое).
        phone: Телефон пользователя (обязательный, уникальный на уровне БД).
    """

    def __init__(self, id: int | None, name: str, phone: str) -> None:
        """Инициализировать пользователя.

        Args:
            id: Идентификатор пользователя или None для нового пользователя.
            name: Имя пользователя.
            phone: Телефон пользователя.
        """
        self.id = id
        self.name = name
        self.phone = phone

    @classmethod
    def from_row(cls, row: dict) -> Self:
        """Создать объект User из строки результата запроса БД.

        Args:
            row: Словарь с колонками 'id', 'name', 'phone'.

        Returns:
            Экземпляр User.
        """
        return cls(id=row["id"], name=row["name"], phone=row["phone"])

    def validate(self) -> None:
        """Проверить локальные ограничения модели.

        Raises:
            ValueError: Если имя или телефон пустые.
        """
        if not self.name or not self.name.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        if not self.phone or not self.phone.strip():
            raise ValueError("Телефон пользователя не может быть пустым")

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name!r}, phone={self.phone!r})"
