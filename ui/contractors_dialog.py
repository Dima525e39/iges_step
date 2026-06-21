from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from settings.contractors_manager import Contractor, contractors_from_settings
from settings.settings_manager import SettingsManager


class ContractorsDialog(QDialog):
    HEADERS = [
        "Название",
        "ИНН",
        "Телефон",
        "Email",
        "Адрес",
        "Комментарий",
        "Наценка, %",
        "Валюта",
        "По умолчанию",
    ]

    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Контрагенты")
        self.resize(920, 420)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)

        add_button = QPushButton("Добавить")
        remove_button = QPushButton("Удалить")
        add_button.clicked.connect(self._add_row)
        remove_button.clicked.connect(self._remove_selected)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch(1)

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        dialog_buttons.accepted.connect(self._save)
        dialog_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons_layout)
        layout.addWidget(self.table)
        layout.addWidget(dialog_buttons)
        self._load()

    def _load(self) -> None:
        contractors = contractors_from_settings(self.settings_manager.as_dict())
        self.table.setRowCount(len(contractors))
        for row, contractor in enumerate(contractors):
            values = [
                contractor.name,
                contractor.inn,
                contractor.phone,
                contractor.email,
                contractor.address,
                contractor.comment,
                f"{contractor.markup_percent:.2f}",
                contractor.currency,
                "да" if contractor.is_default else "",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        defaults = ["Новый контрагент", "", "", "", "", "", "0", "руб.", ""]
        for column, value in enumerate(defaults):
            self.table.setItem(row, column, QTableWidgetItem(value))

    def _remove_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _save(self) -> None:
        contractors: list[dict[str, object]] = []
        default_seen = False
        for row in range(self.table.rowCount()):
            name = _cell(self.table, row, 0) or "Контрагент"
            is_default = _is_yes(_cell(self.table, row, 8))
            if is_default and default_seen:
                is_default = False
            default_seen = default_seen or is_default
            contractor = Contractor(
                id=_slug(name),
                name=name,
                inn=_cell(self.table, row, 1),
                phone=_cell(self.table, row, 2),
                email=_cell(self.table, row, 3),
                address=_cell(self.table, row, 4),
                comment=_cell(self.table, row, 5),
                markup_percent=_float(_cell(self.table, row, 6)),
                currency=_cell(self.table, row, 7) or "руб.",
                is_default=is_default,
            )
            contractors.append(contractor.to_dict())
        if contractors and not any(item.get("is_default") for item in contractors):
            contractors[0]["is_default"] = True
        self.settings_manager.set("contractors", value=contractors)
        self.settings_manager.save()
        self.accept()


def _cell(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    return item.text().strip() if item is not None else ""


def _float(value: str) -> float:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return 0.0


def _is_yes(value: str) -> bool:
    return value.strip().lower() in {"да", "yes", "true", "1", "+"}


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return slug or "contractor"
