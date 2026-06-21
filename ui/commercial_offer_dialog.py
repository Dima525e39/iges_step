from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
)

from settings.contractors_manager import default_contractor
from settings.settings_manager import SettingsManager


class CommercialOfferDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Коммерческое предложение")
        self.resize(560, 520)
        data = settings_manager.get("commercial_offer", default={}) or {}
        contractor = default_contractor(settings_manager.as_dict())

        self.number = QLineEdit(str(data.get("number", "")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDate(QDate.currentDate())
        self.contractor = QLineEdit(contractor.name)
        self.seller = QLineEdit(str(data.get("seller", "")))
        self.contact_person = QLineEdit(str(data.get("contact_person", "")))
        self.phone = QLineEdit(str(data.get("phone", "")))
        self.email = QLineEdit(str(data.get("email", "")))
        self.valid_days = QSpinBox()
        self.valid_days.setRange(1, 365)
        self.valid_days.setValue(int(data.get("valid_days", 14) or 14))
        self.payment_terms = QLineEdit(str(data.get("payment_terms", "Оплата по счету.")))
        self.production_terms = QLineEdit(
            str(data.get("production_terms", "Срок изготовления уточняется."))
        )
        self.comment = QPlainTextEdit(str(data.get("comment", "")))
        self.note = QPlainTextEdit(str(data.get("note", "")))

        form = QFormLayout()
        form.addRow("Номер КП", self.number)
        form.addRow("Дата", self.date)
        form.addRow("Контрагент", self.contractor)
        form.addRow("Организация-исполнитель", self.seller)
        form.addRow("Контактное лицо", self.contact_person)
        form.addRow("Телефон", self.phone)
        form.addRow("Email", self.email)
        form.addRow("Срок действия, дней", self.valid_days)
        form.addRow("Условия оплаты", self.payment_terms)
        form.addRow("Срок изготовления", self.production_terms)
        form.addRow("Комментарий", self.comment)
        form.addRow("Примечание", self.note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.settings_manager.set(
            "commercial_offer",
            value={
                "number": self.number.text().strip(),
                "date": self.date.date().toString("yyyy-MM-dd") or date.today().isoformat(),
                "contractor": self.contractor.text().strip(),
                "seller": self.seller.text().strip(),
                "contact_person": self.contact_person.text().strip(),
                "phone": self.phone.text().strip(),
                "email": self.email.text().strip(),
                "valid_days": self.valid_days.value(),
                "payment_terms": self.payment_terms.text().strip(),
                "production_terms": self.production_terms.text().strip(),
                "comment": self.comment.toPlainText().strip(),
                "note": self.note.toPlainText().strip(),
            },
        )
        self.settings_manager.save()
        self.accept()
