"""Tkinter GUI приложения системы бронирования столиков.

Этот модуль отображает пользовательский интерфейс для управления
пользователями, столиками и бронированиями. GUI обращается к
бизнес-логике через BookingService и не содержит SQL-кода.
"""

import logging
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

from psycopg2.errors import ForeignKeyViolation

from backend import BookingService
from models.booking import Booking
from models.user import User
from models.table import Table

logger = logging.getLogger(__name__)


def _parse_datetime(value: str) -> datetime | None:
    """Парсит строку в формате YYYY-MM-DD HH:MM.

    Args:
        value: Строка даты и времени.

    Returns:
        Объект datetime или None при ошибке парсинга.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


class BookingApp:
    """Главное окно Tkinter приложения бронирования.

    Args:
        root: Корневой виджет Tkinter.
        service: Экземпляр BookingService для доступа к бизнес-логике.
    """

    def __init__(self, root: tk.Tk, service: BookingService) -> None:
        self._root = root
        self._service = service

        self._users: list = []
        self._tables: list = []
        self._bookings: list = []

        self._create_widgets()
        self._load_data()

        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------------------------------------------------------
    # Widgets layout
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        self._root.title("Booking System")
        self._root.geometry("1160x600")
        self._root.minsize(1000, 480)

        top = ttk.Frame(self._root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        bottom = ttk.Frame(self._root, padding=10)
        bottom.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._create_booking_frame(top)
        self._create_clients_frame(top)
        self._create_tables_frame(top)

        self._create_bookings_list(bottom)

    def _create_booking_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Бронирование", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        row = 0

        ttk.Label(frame, text="Клиент:").grid(row=row, sticky="w")
        row += 1

        self._user_cb = ttk.Combobox(frame, width=22, state="readonly")
        self._user_cb.grid(row=row, column=0, sticky="ew")
        ttk.Button(
            frame,
            text="+ Новый клиент",
            command=self._on_add_client_quick,
        ).grid(row=row, column=1, sticky="w", padx=(4, 0))
        row += 1

        ttk.Label(frame, text="Столик:").grid(row=row, sticky="w")
        row += 1

        self._table_cb = ttk.Combobox(frame, width=22, state="readonly")
        self._table_cb.grid(row=row, sticky="ew")
        row += 1

        ttk.Label(frame, text="Гостей:").grid(row=row, sticky="w")
        row += 1

        self._guests_entry = ttk.Entry(frame, width=24)
        self._guests_entry.grid(row=row, sticky="ew")
        row += 1

        ttk.Label(frame, text="Начало (YYYY-MM-DD HH:MM):").grid(
            row=row, sticky="w"
        )
        row += 1

        self._start_entry = ttk.Entry(frame, width=24)
        self._start_entry.grid(row=row, sticky="ew")
        row += 1

        ttk.Label(frame, text="Окончание (YYYY-MM-DD HH:MM):").grid(
            row=row, sticky="w"
        )
        row += 1

        self._end_entry = ttk.Entry(frame, width=24)
        self._end_entry.grid(row=row, sticky="ew")
        row += 1

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, columnspan=2, pady=(10, 0))

        ttk.Button(
            btn_frame, text="Забронировать", command=self._on_create_booking
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            btn_frame, text="Проверить доступность",
            command=self._on_check_availability,
        ).pack(side=tk.LEFT)

        self._msg_label = ttk.Label(frame, text="", foreground="gray")
        self._msg_label.grid(row=row + 1, columnspan=2, sticky="w")

    def _create_bookings_list(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Бронирования", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        columns = ("id", "user", "table", "guests", "start", "end")
        self._tree = ttk.Treeview(
            frame, columns=columns, show="headings", height=16
        )

        self._tree.heading("id", text="ID")
        self._tree.heading("user", text="Клиент")
        self._tree.heading("table", text="Стол")
        self._tree.heading("guests", text="Гостей")
        self._tree.heading("start", text="Начало")
        self._tree.heading("end", text="Окончание")

        self._tree.column("id", width=40, anchor="center")
        self._tree.column("user", width=160)
        self._tree.column("table", width=100)
        self._tree.column("guests", width=60, anchor="center")
        self._tree.column("start", width=160)
        self._tree.column("end", width=160)

        scrollbar = ttk.Scrollbar(
            frame, orient=tk.VERTICAL, command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        ttk.Button(
            btn_frame, text="Обновить список",
            command=self._load_data,
        ).pack(pady=(0, 5))

        ttk.Button(
            btn_frame, text="Удалить выбранное",
            command=self._on_delete_booking,
        ).pack(pady=(0, 5))

    def _create_clients_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Клиенты", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("id", "name", "phone")
        self._clients_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=8
        )

        self._clients_tree.heading("id", text="ID")
        self._clients_tree.heading("name", text="Имя")
        self._clients_tree.heading("phone", text="Телефон")

        self._clients_tree.column("id", width=40, anchor="center")
        self._clients_tree.column("name", width=170)
        self._clients_tree.column("phone", width=140)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self._clients_tree.yview
        )
        self._clients_tree.configure(yscrollcommand=scrollbar.set)

        self._clients_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))

        ttk.Button(
            btn_frame, text="Добавить", command=self._on_add_client
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="Изменить", command=self._on_edit_client
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="Удалить", command=self._on_delete_client
        ).pack(side=tk.LEFT)

    def _create_tables_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Столики", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("id", "number", "capacity", "location")
        self._tables_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=8
        )

        self._tables_tree.heading("id", text="ID")
        self._tables_tree.heading("number", text="Номер")
        self._tables_tree.heading("capacity", text="Мест")
        self._tables_tree.heading("location", text="Расположение")

        self._tables_tree.column("id", width=40, anchor="center")
        self._tables_tree.column("number", width=70, anchor="center")
        self._tables_tree.column("capacity", width=60, anchor="center")
        self._tables_tree.column("location", width=140)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self._tables_tree.yview
        )
        self._tables_tree.configure(yscrollcommand=scrollbar.set)

        self._tables_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))

        ttk.Button(
            btn_frame, text="Добавить", command=self._on_add_table
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="Редактировать", command=self._on_edit_table
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="Удалить", command=self._on_delete_table
        ).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Datetime parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        return _parse_datetime(value)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self) -> None:
        self._users = self._service.get_all_users()
        self._tables = self._service.get_all_tables()
        self._bookings = self._service.get_all_bookings()

        user_items = [f"{u.name} (id={u.id})" for u in self._users]
        self._user_cb["values"] = user_items
        if user_items:
            self._user_cb.current(0)
        else:
            self._user_cb.set("")

        table_items = [
            f"{t.number} — {t.capacity} мест" for t in self._tables
        ]
        self._table_cb["values"] = table_items
        if table_items:
            self._table_cb.current(0)
        else:
            self._table_cb.set("")

        for item in self._tree.get_children():
            self._tree.delete(item)

        user_map = {u.id: u.name for u in self._users}
        table_map = {t.id: t.number for t in self._tables}

        for b in self._bookings:
            user_name = user_map.get(b.user_id, "?")
            table_num = table_map.get(b.table_id, "?")
            start_str = (
                b.start_time.strftime("%Y-%m-%d %H:%M")
                if b.start_time
                else ""
            )
            end_str = (
                b.end_time.strftime("%Y-%m-%d %H:%M")
                if b.end_time
                else ""
            )
            self._tree.insert("", tk.END, values=(
                b.id, user_name, table_num, b.guests, start_str, end_str,
            ))

        self._refresh_clients_tree()
        self._refresh_tables_tree()

    # ------------------------------------------------------------------
    # Create booking
    # ------------------------------------------------------------------

    def _on_create_booking(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            return

        table_id = self._get_selected_table_id()
        if table_id is None:
            return

        guests = self._parse_guests()
        if guests is None:
            return

        start_time = self._parse_datetime(self._start_entry.get().strip())
        if start_time is None:
            self._show_msg("Неверный формат начала (YYYY-MM-DD HH:MM)", "red")
            return

        end_time = self._parse_datetime(self._end_entry.get().strip())
        if end_time is None:
            self._show_msg("Неверный формат окончания (YYYY-MM-DD HH:MM)", "red")
            return

        try:
            booking = Booking(
                id=None,
                user_id=user_id,
                table_id=table_id,
                guests=guests,
                start_time=start_time,
                end_time=end_time,
            )
            result = self._service.create_booking(booking)
            self._show_msg(
                f"Бронирование №{result.id} успешно создано.", "green"
            )
            self._load_data()
        except ValueError as exc:
            self._show_msg(str(exc), "red")
        except LookupError as exc:
            self._show_msg(str(exc), "red")
        except RuntimeError as exc:
            self._show_msg(str(exc), "red")

    # ------------------------------------------------------------------
    # Check availability
    # ------------------------------------------------------------------

    def _on_check_availability(self) -> None:
        table_id = self._get_selected_table_id()
        if table_id is None:
            return

        guests = self._parse_guests()
        if guests is None:
            return

        start_time = self._parse_datetime(self._start_entry.get().strip())
        if start_time is None:
            self._show_msg("Неверный формат начала (YYYY-MM-DD HH:MM)", "red")
            return

        end_time = self._parse_datetime(self._end_entry.get().strip())
        if end_time is None:
            self._show_msg("Неверный формат окончания (YYYY-MM-DD HH:MM)", "red")
            return

        if not self._service.check_table_availability(
            table_id, guests, start_time, end_time
        ):
            self._show_msg("Столик недоступен в указанное время.", "red")
        else:
            self._show_msg("Столик доступен.", "green")

    # ------------------------------------------------------------------
    # Delete booking
    # ------------------------------------------------------------------

    def _on_delete_booking(self) -> None:
        selection = self._tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите бронирование.")
            return

        item = self._tree.item(selection[0])
        booking_id = int(item["values"][0])

        if messagebox.askyesno(
            "Подтверждение", "Удалить выбранное бронирование?"
        ):
            try:
                self._service.delete_booking(booking_id)
                self._load_data()
            except Exception as exc:
                messagebox.showerror("Ошибка", str(exc))

    # ------------------------------------------------------------------
    # Clients management
    # ------------------------------------------------------------------

    def _refresh_clients_tree(self) -> None:
        for item in self._clients_tree.get_children():
            self._clients_tree.delete(item)

        for user in self._users:
            self._clients_tree.insert(
                "", tk.END, values=(user.id, user.name, user.phone)
            )

    def _on_add_client(self) -> None:
        if self._open_client_dialog() is not None:
            self._load_data()

    def _on_edit_client(self) -> None:
        selection = self._clients_tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите клиента.")
            return

        item = self._clients_tree.item(selection[0])
        user_id = int(item["values"][0])

        user = self._service.get_user(user_id)
        if user is None:
            messagebox.showerror("Ошибка", "Клиент не найден.")
            self._load_data()
            return

        if self._open_client_dialog(user) is not None:
            self._load_data()

    def _on_delete_client(self) -> None:
        selection = self._clients_tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите клиента.")
            return

        item = self._clients_tree.item(selection[0])
        user_id = int(item["values"][0])
        name = item["values"][1]

        if not messagebox.askyesno(
            "Подтверждение", f"Удалить клиента «{name}»?"
        ):
            return

        try:
            deleted = self._service.delete_user(user_id)
        except ForeignKeyViolation:
            messagebox.showerror(
                "Невозможно удалить",
                "Клиента нельзя удалить, пока существуют связанные "
                "бронирования.",
            )
            return
        except Exception:
            logger.exception(
                "Не удалось удалить клиента id=%s", user_id
            )
            messagebox.showerror(
                "Ошибка", "Не удалось удалить клиента. Попробуйте позже."
            )
            return

        if not deleted:
            messagebox.showinfo("Информация", "Клиент уже отсутствует.")
            self._load_data()
            return

        self._load_data()

    def _on_add_client_quick(self) -> None:
        created = self._open_client_dialog()
        if created is None:
            return

        prev_table_idx = self._table_cb.current()

        self._load_data()

        if 0 <= prev_table_idx < len(self._tables):
            self._table_cb.current(prev_table_idx)

        if created.id is None:
            return

        for idx, user in enumerate(self._users):
            if user.id == created.id:
                self._user_cb.current(idx)
                break

    def _open_client_dialog(self, user: User | None = None) -> User | None:
        dialog = tk.Toplevel(self._root)
        dialog.title("Новый клиент" if user is None else "Изменение клиента")
        dialog.transient(self._root)
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Имя:").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        name_entry = ttk.Entry(frame, width=30)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        ttk.Label(frame, text="Телефон:").grid(
            row=1, column=0, sticky="w", pady=(0, 6)
        )
        phone_entry = ttk.Entry(frame, width=30)
        phone_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        if user is not None:
            name_entry.insert(0, user.name)
            phone_entry.insert(0, user.phone)

        result: dict = {"user": None}

        def on_save() -> None:
            name = name_entry.get().strip()
            phone = phone_entry.get().strip()
            try:
                if user is None:
                    saved = self._service.create_user(
                        User(id=None, name=name, phone=phone)
                    )
                else:
                    saved = self._service.update_user(
                        User(id=user.id, name=name, phone=phone)
                    )
            except (ValueError, LookupError, RuntimeError) as exc:
                messagebox.showerror("Ошибка", str(exc), parent=dialog)
                return
            result["user"] = saved
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="e", pady=(6, 0))

        ttk.Button(
            btn_frame, text="Сохранить", command=on_save
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="Отмена", command=on_cancel
        ).pack(side=tk.LEFT)

        name_entry.focus_set()
        dialog.grab_set()
        dialog.wait_window()
        return result["user"]

    # ------------------------------------------------------------------
    # Tables management
    # ------------------------------------------------------------------

    def _refresh_tables_tree(self) -> None:
        for item in self._tables_tree.get_children():
            self._tables_tree.delete(item)

        for table in self._tables:
            self._tables_tree.insert(
                "", tk.END, values=(
                    table.id,
                    table.number,
                    table.capacity,
                    table.location or "",
                ),
            )

    def _on_add_table(self) -> None:
        if self._open_table_dialog() is not None:
            self._load_data()

    def _on_edit_table(self) -> None:
        selection = self._tables_tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите столик.")
            return

        item = self._tables_tree.item(selection[0])
        table_id = int(item["values"][0])

        table = self._service.get_table(table_id)
        if table is None:
            messagebox.showerror("Ошибка", "Столик не найден.")
            self._load_data()
            return

        if self._open_table_dialog(table) is not None:
            self._load_data()

    def _on_delete_table(self) -> None:
        selection = self._tables_tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите столик.")
            return

        item = self._tables_tree.item(selection[0])
        table_id = int(item["values"][0])
        number = item["values"][1]

        if not messagebox.askyesno(
            "Подтверждение", f"Удалить столик «{number}»?"
        ):
            return

        try:
            deleted = self._service.delete_table(table_id)
        except ForeignKeyViolation:
            messagebox.showerror(
                "Невозможно удалить",
                "Столик нельзя удалить, пока на него ссылаются "
                "существующие бронирования.",
            )
            return
        except Exception:
            logger.exception(
                "Не удалось удалить столик id=%s", table_id
            )
            messagebox.showerror(
                "Ошибка", "Не удалось удалить столик. Попробуйте позже."
            )
            return

        if not deleted:
            messagebox.showinfo("Информация", "Столик уже отсутствует.")
            self._load_data()
            return

        self._load_data()

    def _open_table_dialog(self, table: Table | None = None) -> Table | None:
        dialog = tk.Toplevel(self._root)
        dialog.title("Новый столик" if table is None else "Изменение столика")
        dialog.transient(self._root)
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Номер:").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        number_entry = ttk.Entry(frame, width=30)
        number_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        ttk.Label(frame, text="Вместимость:").grid(
            row=1, column=0, sticky="w", pady=(0, 6)
        )
        capacity_entry = ttk.Entry(frame, width=30)
        capacity_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        ttk.Label(frame, text="Расположение:").grid(
            row=2, column=0, sticky="w", pady=(0, 6)
        )
        location_entry = ttk.Entry(frame, width=30)
        location_entry.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        if table is not None:
            number_entry.insert(0, table.number)
            capacity_entry.insert(0, str(table.capacity))
            if table.location:
                location_entry.insert(0, table.location)

        result: dict = {"table": None}

        def on_save() -> None:
            number = number_entry.get().strip()
            capacity_raw = capacity_entry.get().strip()
            location = location_entry.get().strip()

            try:
                capacity = int(capacity_raw)
            except ValueError:
                messagebox.showerror(
                    "Ошибка", "Вместимость должна быть числом.", parent=dialog
                )
                return

            location_value = location or None

            try:
                if table is None:
                    saved = self._service.create_table(
                        Table(
                            id=None,
                            number=number,
                            capacity=capacity,
                            location=location_value,
                        )
                    )
                else:
                    saved = self._service.update_table(
                        Table(
                            id=table.id,
                            number=number,
                            capacity=capacity,
                            location=location_value,
                        )
                    )
            except (ValueError, LookupError, RuntimeError) as exc:
                messagebox.showerror("Ошибка", str(exc), parent=dialog)
                return

            result["table"] = saved
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="e", pady=(6, 0))

        ttk.Button(
            btn_frame, text="Сохранить", command=on_save
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            btn_frame, text="Отмена", command=on_cancel
        ).pack(side=tk.LEFT)

        number_entry.focus_set()
        dialog.grab_set()
        dialog.wait_window()
        return result["table"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_selected_user_id(self) -> int | None:
        idx = self._user_cb.current()
        if idx < 0 or idx >= len(self._users):
            messagebox.showwarning("Внимание", "Выберите клиента.")
            return None
        return self._users[idx].id

    def _get_selected_table_id(self) -> int | None:
        idx = self._table_cb.current()
        if idx < 0 or idx >= len(self._tables):
            messagebox.showwarning("Внимание", "Выберите столик.")
            return None
        return self._tables[idx].id

    def _parse_guests(self) -> int | None:
        raw = self._guests_entry.get().strip()
        try:
            guests = int(raw)
        except ValueError:
            self._show_msg("Количество гостей должно быть числом.", "red")
            return None
        if guests <= 0:
            self._show_msg(
                "Количество гостей должно быть больше нуля.", "red"
            )
            return None
        return guests

    def _show_msg(self, text: str, color: str) -> None:
        self._msg_label.config(text=text, foreground=color)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_closing(self) -> None:
        self._root.destroy()
