from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.file_job import FileJob
from export.excel_exporter import calculation_detail_rows


class ExcelPreviewDialog(QDialog):
    HEADERS = [
        "Файл",
        "Материал",
        "Размер",
        "Толщина",
        "Длина",
        "Длина реза",
        "Врезки",
        "Количество",
        "Цена",
    ]

    def __init__(self, jobs: list[FileJob], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр Excel")
        self.resize(980, 520)

        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        rows = calculation_detail_rows(jobs, include_totals=True)[1:]
        self.table.setRowCount(len(rows))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)

        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()
        self.export_button = QPushButton("Экспорт")
        self.cancel_button = QPushButton("Отмена")
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

        self.export_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
