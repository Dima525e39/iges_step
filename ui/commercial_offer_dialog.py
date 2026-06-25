from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QDoubleSpinBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from settings.contractors_manager import default_contractor
from settings.settings_manager import SettingsManager


class CommercialOfferDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Шаблон счета")
        self.resize(720, 680)
        data = settings_manager.get("commercial_offer", default={}) or {}
        contractor = default_contractor(settings_manager.as_dict())

        self.number = QLineEdit(str(data.get("number", "")))
        self.document_title = QLineEdit(str(data.get("document_title", "Счет на оплату")))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        saved_date = QDate.fromString(str(data.get("date", "")), "yyyy-MM-dd")
        self.date.setDate(saved_date if saved_date.isValid() else QDate.currentDate())
        self.contractor = QLineEdit(contractor.name)
        self.supplier_name = QLineEdit(str(data.get("supplier_name", "")))
        self.supplier_inn = QLineEdit(str(data.get("supplier_inn", "")))
        self.supplier_kpp = QLineEdit(str(data.get("supplier_kpp", "")))
        self.supplier_address = QLineEdit(str(data.get("supplier_address", "")))
        self.supplier_bank = QLineEdit(str(data.get("supplier_bank", "")))
        self.supplier_bik = QLineEdit(str(data.get("supplier_bik", "")))
        self.supplier_account = QLineEdit(str(data.get("supplier_account", "")))
        self.supplier_corr_account = QLineEdit(str(data.get("supplier_corr_account", "")))
        self.supplier_recipient = QLineEdit(str(data.get("supplier_recipient", "")))
        self.basis = QLineEdit(str(data.get("basis", "Договор поставки")))
        self.unit = QLineEdit(str(data.get("unit", "шт")))
        self.vat_mode = QComboBox()
        self.vat_mode.addItems(["Без НДС", "НДС включен"])
        self.vat_mode.setCurrentIndex(1 if str(data.get("vat_mode", "none")) == "included" else 0)
        self.vat_rate = QDoubleSpinBox()
        self.vat_rate.setRange(0.0, 100.0)
        self.vat_rate.setDecimals(2)
        self.vat_rate.setValue(float(data.get("vat_rate", 20.0) or 20.0))
        self.validity_text = QLineEdit(
            str(data.get("validity_text", "Счет действителен в течение 3 (трех) банковских дней."))
        )
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
        form.addRow("Название документа", self.document_title)
        form.addRow("Номер счета", self.number)
        form.addRow("Дата", self.date)
        form.addRow("Контрагент", self.contractor)
        form.addRow("Поставщик", self.supplier_name)
        form.addRow("ИНН поставщика", self.supplier_inn)
        form.addRow("КПП поставщика", self.supplier_kpp)
        form.addRow("Адрес поставщика", self.supplier_address)
        form.addRow("Банк поставщика", self.supplier_bank)
        form.addRow("БИК", self.supplier_bik)
        form.addRow("Расчетный счет", self.supplier_account)
        form.addRow("Корр. счет", self.supplier_corr_account)
        form.addRow("Получатель", self.supplier_recipient)
        form.addRow("Основание", self.basis)
        form.addRow("Ед. измерения", self.unit)
        form.addRow("НДС", self.vat_mode)
        form.addRow("Ставка НДС, %", self.vat_rate)
        form.addRow("Срок действия счета", self.validity_text)
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

        content = QWidget()
        content.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.settings_manager.set(
            "commercial_offer",
            value={
                "number": self.number.text().strip(),
                "document_title": self.document_title.text().strip() or "Счет на оплату",
                "date": self.date.date().toString("yyyy-MM-dd") or date.today().isoformat(),
                "contractor": self.contractor.text().strip(),
                "supplier_name": self.supplier_name.text().strip(),
                "supplier_inn": self.supplier_inn.text().strip(),
                "supplier_kpp": self.supplier_kpp.text().strip(),
                "supplier_address": self.supplier_address.text().strip(),
                "supplier_bank": self.supplier_bank.text().strip(),
                "supplier_bik": self.supplier_bik.text().strip(),
                "supplier_account": self.supplier_account.text().strip(),
                "supplier_corr_account": self.supplier_corr_account.text().strip(),
                "supplier_recipient": self.supplier_recipient.text().strip(),
                "basis": self.basis.text().strip(),
                "unit": self.unit.text().strip() or "шт",
                "vat_mode": "included" if self.vat_mode.currentIndex() == 1 else "none",
                "vat_rate": self.vat_rate.value(),
                "validity_text": self.validity_text.text().strip(),
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
