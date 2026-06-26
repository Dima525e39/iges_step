from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from settings.materials_manager import default_material, materials_from_settings
from settings.settings_manager import SettingsManager
from settings.tube_price_manager import TubePriceRule, tube_price_rules_from_settings


class TubePriceDialog(QDialog):
    HEADERS = [
        "Материал",
        "Размер трубы",
        "Толщина, мм",
        "Хлыст, мм",
        "Цена за метр",
        "Цена за хлыст",
        "Активно",
    ]

    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.materials = self._material_choices()
        self.setWindowTitle("Прайс труб")
        self.resize(920, 420)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        layout.addWidget(buttons)
        self._load()

    def _load(self) -> None:
        rules = tube_price_rules_from_settings(self.settings_manager.as_dict())
        self.table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            self._set_material_combo(row, rule.material)
            values = [
                rule.tube_size,
                f"{rule.wall_thickness_mm:.2f}",
                f"{rule.standard_stock_length_mm:.1f}",
                f"{rule.tube_price_per_meter:.2f}",
                f"{rule.tube_price_per_stock:.2f}",
                "да" if rule.active else "",
            ]
            for offset, value in enumerate(values, start=1):
                self.table.setItem(row, offset, QTableWidgetItem(value))

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_material_combo(row, default_material(self.settings_manager.as_dict()).name)
        defaults = ["Ø35.0", "2.50", "6000", "0", "0", "да"]
        for offset, value in enumerate(defaults, start=1):
            self.table.setItem(row, offset, QTableWidgetItem(value))

    def _remove_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _save(self) -> None:
        rules: list[dict[str, object]] = []
        for row in range(self.table.rowCount()):
            rule = TubePriceRule(
                material=_cell(self.table, row, 0) or "Сталь",
                tube_size=_cell(self.table, row, 1),
                wall_thickness_mm=_float(_cell(self.table, row, 2)),
                standard_stock_length_mm=_float(_cell(self.table, row, 3), 6000.0),
                tube_price_per_meter=_float(_cell(self.table, row, 4)),
                tube_price_per_stock=_float(_cell(self.table, row, 5)),
                active=_is_yes(_cell(self.table, row, 6)),
            )
            if rule.tube_size:
                rules.append(rule.to_dict())
        self.settings_manager.set("tube_prices", value=rules)
        self.settings_manager.save()
        self.accept()

    def _material_choices(self) -> list[str]:
        materials = materials_from_settings(self.settings_manager.as_dict())
        choices = [material.name for material in materials if material.active]
        default = default_material(self.settings_manager.as_dict()).name
        if default and default not in choices:
            choices.insert(0, default)
        return choices or ["Сталь"]

    def _set_material_combo(self, row: int, value: str) -> None:
        combo = QComboBox(self.table)
        values = list(self.materials)
        if value and value not in values:
            values.insert(0, value)
        combo.addItems(values)
        if value:
            combo.setCurrentText(value)
        self.table.setCellWidget(row, 0, combo)
        self.table.setItem(row, 0, QTableWidgetItem(combo.currentText()))


def _cell(table: QTableWidget, row: int, column: int) -> str:
    widget = table.cellWidget(row, column)
    if isinstance(widget, QComboBox):
        return widget.currentText().strip()
    item = table.item(row, column)
    return item.text().strip() if item is not None else ""


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return default


def _is_yes(value: str) -> bool:
    return value.strip().lower() in {"да", "yes", "true", "1", "+"}
