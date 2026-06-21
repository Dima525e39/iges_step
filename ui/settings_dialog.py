from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QVBoxLayout,
)

from settings.settings_manager import SettingsManager


class GeneralSettingsDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Общие параметры расчета")
        self.resize(480, 260)

        ui = settings_manager.get("ui", default={}) or {}
        geometry = settings_manager.get("geometry", default={}) or {}
        pricing = settings_manager.get("pricing", default={}) or {}

        self.theme = QComboBox()
        self.theme.addItem("Светлая", "light")
        self.theme.addItem("Темная", "dark")
        current_theme = str(ui.get("theme", "light"))
        index = self.theme.findData(current_theme)
        self.theme.setCurrentIndex(max(0, index))

        self.global_markup = _spin(float(pricing.get("markup_percent", 0.0) or 0.0), "%")
        self.thickness_tolerance = _spin(
            float(pricing.get("thickness_tolerance_mm", 0.25) or 0.25), " мм"
        )
        self.include_end_cuts = QCheckBox()
        self.include_end_cuts.setChecked(bool(geometry.get("include_end_cuts", True)))
        self.count_open_slots = QCheckBox()
        self.count_open_slots.setChecked(bool(geometry.get("count_open_slots_as_pierces", True)))

        form = QFormLayout()
        form.addRow("Тема интерфейса", self.theme)
        form.addRow("Общая наценка", self.global_markup)
        form.addRow("Допуск подбора толщины", self.thickness_tolerance)
        form.addRow("Торцы считаются всегда", self.include_end_cuts)
        form.addRow("Открытый паз = 1 врезка", self.count_open_slots)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        pricing = dict(self.settings_manager.get("pricing", default={}) or {})
        pricing["markup_percent"] = self.global_markup.value()
        pricing["thickness_tolerance_mm"] = self.thickness_tolerance.value()
        geometry = dict(self.settings_manager.get("geometry", default={}) or {})
        geometry["include_end_cuts"] = self.include_end_cuts.isChecked()
        geometry["count_open_slots_as_pierces"] = self.count_open_slots.isChecked()
        self.settings_manager.set("ui", "theme", value=self.theme.currentData())
        self.settings_manager.set("pricing", value=pricing)
        self.settings_manager.set("geometry", value=geometry)
        self.settings_manager.save()
        self.accept()


def _spin(value: float, suffix: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 100000.0)
    spin.setDecimals(2)
    spin.setSingleStep(1.0)
    spin.setSuffix(f" {suffix}")
    spin.setValue(value)
    return spin
