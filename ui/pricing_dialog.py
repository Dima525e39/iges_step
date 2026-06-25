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
from settings.pricing_manager import PriceRule, pricing_rules_from_settings
from settings.settings_manager import SettingsManager


class PricingDialog(QDialog):
    HEADERS = [
        "Контрагент",
        "Материал",
        "Толщина, мм",
        "Цена за метр",
        "Цена за врезку",
        "Минимум",
        "Подготовка",
        "Коэф. сложности",
        "Активно",
        "По умолчанию",
    ]

    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Цены")
        self.resize(980, 420)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.materials = self._material_choices()

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
        rules = pricing_rules_from_settings(self.settings_manager.as_dict())
        self.table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            values = [
                rule.contractor,
                rule.material,
                f"{rule.thickness_mm:.2f}",
                f"{rule.price_per_meter:.2f}",
                f"{rule.price_per_pierce:.2f}",
                f"{rule.minimum_price:.2f}",
                f"{rule.setup_price:.2f}",
                f"{rule.complexity_factor:.2f}",
                "да" if rule.active else "",
                "да" if rule.is_default else "",
            ]
            for column, value in enumerate(values):
                if column == 1:
                    self._set_material_combo(row, value)
                else:
                    self.table.setItem(row, column, QTableWidgetItem(value))

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        default_material_name = default_material(self.settings_manager.as_dict()).name
        defaults = [
            "По умолчанию",
            default_material_name,
            "1.5",
            "120",
            "15",
            "0",
            "0",
            "1",
            "да",
            "",
        ]
        for column, value in enumerate(defaults):
            if column == 1:
                self._set_material_combo(row, value)
            else:
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _remove_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _save(self) -> None:
        rules: list[dict[str, object]] = []
        default_seen = False
        for row in range(self.table.rowCount()):
            is_default = _is_yes(_cell(self.table, row, 9))
            if is_default and default_seen:
                is_default = False
            default_seen = default_seen or is_default
            rule = PriceRule(
                contractor=_cell(self.table, row, 0) or "По умолчанию",
                material=_cell(self.table, row, 1) or "Сталь",
                thickness_mm=_float(_cell(self.table, row, 2), 1.5),
                price_per_meter=_float(_cell(self.table, row, 3), 120.0),
                price_per_pierce=_float(_cell(self.table, row, 4), 15.0),
                minimum_price=_float(_cell(self.table, row, 5)),
                setup_price=_float(_cell(self.table, row, 6)),
                complexity_factor=_float(_cell(self.table, row, 7), 1.0),
                active=_is_yes(_cell(self.table, row, 8)),
                is_default=is_default,
            )
            rules.append(rule.to_dict())
        if rules and not any(item.get("is_default") for item in rules):
            rules[0]["is_default"] = True
        pricing = dict(self.settings_manager.get("pricing", default={}) or {})
        pricing["rules"] = rules
        if rules:
            pricing["price_per_meter"] = rules[0]["price_per_meter"]
            pricing["price_per_pierce"] = rules[0]["price_per_pierce"]
            pricing["minimum_price"] = rules[0]["minimum_price"]
            pricing["setup_price"] = rules[0]["setup_price"]
            pricing["complexity_factor"] = rules[0]["complexity_factor"]
        self.settings_manager.set("pricing", value=pricing)
        self.settings_manager.save()
        self.accept()

    def _material_choices(self) -> list[str]:
        settings = self.settings_manager.as_dict()
        materials = materials_from_settings(settings)
        choices = [material.name for material in materials if material.active]
        default = default_material(settings).name
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
        self.table.setCellWidget(row, 1, combo)
        self.table.setItem(row, 1, QTableWidgetItem(combo.currentText()))


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
