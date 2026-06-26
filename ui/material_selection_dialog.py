from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class MaterialSelectionDialog(QDialog):
    def __init__(
        self,
        materials: list[str],
        contractors: list[str],
        *,
        current_material: str = "",
        current_contractor: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Материал для обработки")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите параметры, которые будут назначены всем файлам."))

        self.material_combo = QComboBox()
        values = [material for material in materials if material]
        if current_material and current_material not in values:
            values.insert(0, current_material)
        self.material_combo.addItems(values or ["Сталь"])
        if current_material:
            self.material_combo.setCurrentText(current_material)

        self.contractor_combo = QComboBox()
        contractor_values = [contractor for contractor in contractors if contractor]
        if current_contractor and current_contractor not in contractor_values:
            contractor_values.insert(0, current_contractor)
        self.contractor_combo.addItems(contractor_values or ["По умолчанию"])
        if current_contractor:
            self.contractor_combo.setCurrentText(current_contractor)

        form = QFormLayout()
        form.addRow("Материал:", self.material_combo)
        form.addRow("Контрагент:", self.contractor_combo)
        self.customer_tube_checkbox = QCheckBox("Труба заказчика")
        self.customer_tube_checkbox.setChecked(True)
        form.addRow("", self.customer_tube_checkbox)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_material(self) -> str:
        return self.material_combo.currentText().strip()

    def selected_contractor(self) -> str:
        return self.contractor_combo.currentText().strip()

    def is_customer_tube(self) -> bool:
        return self.customer_tube_checkbox.isChecked()
