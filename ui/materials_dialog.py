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

from settings.materials_manager import Material, materials_from_settings
from settings.settings_manager import SettingsManager


class MaterialsDialog(QDialog):
    HEADERS = [
        "Название",
        "Активен",
        "Комментарий",
        "Хлыст, мм",
        "Цена трубы за метр",
        "Цена трубы за хлыст",
        "По умолчанию",
    ]

    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Материалы")
        self.resize(820, 380)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)

        add_button = QPushButton("Добавить")
        remove_button = QPushButton("Удалить")
        add_button.clicked.connect(self._add_row)
        remove_button.clicked.connect(self._remove_selected)

        actions = QHBoxLayout()
        actions.addWidget(add_button)
        actions.addWidget(remove_button)
        actions.addStretch(1)

        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        dialog_buttons.accepted.connect(self._save)
        dialog_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        layout.addWidget(dialog_buttons)
        self._load()

    def _load(self) -> None:
        materials = materials_from_settings(self.settings_manager.as_dict())
        self.table.setRowCount(len(materials))
        for row, material in enumerate(materials):
            values = [
                material.name,
                "да" if material.active else "",
                material.comment,
                f"{material.standard_stock_length_mm:.1f}",
                f"{material.tube_price_per_meter:.2f}",
                f"{material.tube_price_per_stock:.2f}",
                "да" if material.is_default else "",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        defaults = ["Новый материал", "да", "", "6000", "0", "0", ""]
        for column, value in enumerate(defaults):
            self.table.setItem(row, column, QTableWidgetItem(value))

    def _remove_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _save(self) -> None:
        materials: list[dict[str, object]] = []
        default_seen = False
        for row in range(self.table.rowCount()):
            name = _cell(self.table, row, 0) or "Материал"
            is_default = _is_yes(_cell(self.table, row, 6))
            if is_default and default_seen:
                is_default = False
            default_seen = default_seen or is_default
            material = Material(
                id=_slug(name),
                name=name,
                active=_is_yes(_cell(self.table, row, 1)),
                comment=_cell(self.table, row, 2),
                standard_stock_length_mm=_float(_cell(self.table, row, 3), 6000.0),
                tube_price_per_meter=_float(_cell(self.table, row, 4)),
                tube_price_per_stock=_float(_cell(self.table, row, 5)),
                is_default=is_default,
            )
            materials.append(material.to_dict())
        if materials and not any(item.get("is_default") for item in materials):
            materials[0]["is_default"] = True
        self.settings_manager.set("materials", value=materials)
        self.settings_manager.save()
        self.accept()


def _cell(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    return item.text().strip() if item is not None else ""


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return default


def _is_yes(value: str) -> bool:
    return value.strip().lower() in {"да", "yes", "true", "1", "+"}


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return slug or "material"
