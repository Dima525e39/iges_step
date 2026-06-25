from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from settings.contractors_manager import contractors_from_settings, default_contractor
from settings.settings_manager import SettingsManager


class InvoiceExportDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Экспорт счета")
        self.resize(420, 180)

        offer = settings_manager.get("commercial_offer", default={}) or {}
        settings = settings_manager.as_dict()
        contractors = contractors_from_settings(settings)
        default = default_contractor(settings)

        self.number = QLineEdit(str(offer.get("number", "")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        saved_date = QDate.fromString(str(offer.get("date", "")), "yyyy-MM-dd")
        self.date.setDate(saved_date if saved_date.isValid() else QDate.currentDate())
        self.contractor = QComboBox()
        for contractor in contractors:
            self.contractor.addItem(contractor.name)
        selected = str(offer.get("contractor", "")) or default.name
        index = self.contractor.findText(selected)
        self.contractor.setCurrentIndex(index if index >= 0 else 0)

        form = QFormLayout()
        form.addRow("Номер счета", self.number)
        form.addRow("Дата", self.date)
        form.addRow("Контрагент", self.contractor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply_to_settings(self) -> None:
        self.settings_manager.set("commercial_offer", "number", value=self.number.text().strip())
        self.settings_manager.set(
            "commercial_offer",
            "date",
            value=self.date.date().toString("yyyy-MM-dd") or date.today().isoformat(),
        )
        self.settings_manager.set(
            "commercial_offer",
            "contractor",
            value=self.contractor.currentText().strip(),
        )
        self.settings_manager.save()
