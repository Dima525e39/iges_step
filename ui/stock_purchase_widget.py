from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from purchase.tube_purchase_calculator import TubePurchaseRow
from settings.tube_purchase_settings import TubePurchaseSettings


class StockPurchaseWidget(QWidget):
    HEADERS = [
        "Материал",
        "Тип трубы",
        "Размер",
        "Толщина, мм",
        "Деталей",
        "Длина деталей, мм",
        "Припуски, мм",
        "Запас, %",
        "Длина с запасом, мм",
        "Хлыст, мм",
        "Хлыстов",
        "Закупка, мм",
        "Остаток, мм",
        "Стоимость закупки",
        "Предупреждения",
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def set_rows(
        self,
        rows: list[TubePurchaseRow],
        *,
        purchase_settings: TubePurchaseSettings,
    ) -> None:
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = row.to_table_row(show_purchase_cost=True)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row_index, column, item)
