from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QVBoxLayout,
)

from settings.settings_manager import SettingsManager
from settings.tube_purchase_settings import TubePurchaseSettings


class TubePurchaseSettingsDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Закупка трубы")
        self.resize(480, 360)
        data = TubePurchaseSettings.from_settings(settings_manager.as_dict())

        self.stock_length = _spin(data.standard_stock_length_mm, 100.0, 100000.0, " мм")
        self.chuck_remainder = _spin(data.chuck_remainder_mm, 0.0, 100000.0, " мм")
        self.stock_percent = _spin(data.stock_allowance_percent, 0.0, 1000.0, " %")
        self.end_trim = _spin(data.end_trim_allowance_mm, 0.0, 10000.0, " мм")
        self.useful_remainder = _spin(data.useful_remainder_min_mm, 0.0, 100000.0, " мм")
        self.include_gap = QCheckBox()
        self.include_gap.setChecked(data.include_part_gap)
        self.gap = _spin(data.part_gap_mm, 0.0, 1000.0, " мм")
        self.round_stock = QCheckBox()
        self.round_stock.setChecked(data.round_to_whole_stock)
        self.show_commercial = QCheckBox()
        self.show_commercial.setChecked(data.show_in_commercial_offer)
        self.show_technical = QCheckBox()
        self.show_technical.setChecked(data.show_in_technical_report)
        self.show_cost = QCheckBox()
        self.show_cost.setChecked(data.show_purchase_cost)

        form = QFormLayout()
        form.addRow("Стандартная длина хлыста", self.stock_length)
        form.addRow("Остаток в патроне станка", self.chuck_remainder)
        form.addRow("Запас на резку", self.stock_percent)
        form.addRow("Запас на торцовку/ошибки", self.end_trim)
        form.addRow("Минимальный полезный остаток", self.useful_remainder)
        form.addRow("Учитывать припуск между деталями", self.include_gap)
        form.addRow("Припуск между деталями", self.gap)
        form.addRow("Округлять до целого хлыста", self.round_stock)
        form.addRow("Показывать в КП", self.show_commercial)
        form.addRow("Показывать в техотчете", self.show_technical)
        form.addRow("Показывать стоимость закупки", self.show_cost)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        data = TubePurchaseSettings(
            standard_stock_length_mm=self.stock_length.value(),
            chuck_remainder_mm=self.chuck_remainder.value(),
            stock_allowance_percent=self.stock_percent.value(),
            end_trim_allowance_mm=self.end_trim.value(),
            useful_remainder_min_mm=self.useful_remainder.value(),
            include_part_gap=self.include_gap.isChecked(),
            part_gap_mm=self.gap.value(),
            round_to_whole_stock=self.round_stock.isChecked(),
            show_in_commercial_offer=self.show_commercial.isChecked(),
            show_in_technical_report=self.show_technical.isChecked(),
            show_purchase_cost=self.show_cost.isChecked(),
        )
        self.settings_manager.set("purchase", value=data.to_dict())
        self.settings_manager.save()
        self.accept()


def _spin(value: float, minimum: float, maximum: float, suffix: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(2)
    spin.setSingleStep(1.0)
    spin.setSuffix(suffix)
    spin.setValue(value)
    return spin
