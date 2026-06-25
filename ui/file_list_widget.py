from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from core.file_job import STATUS_ERROR, STATUS_IMPORTED, STATUS_IMPORTING, STATUS_PENDING, FileJob
from ui.drop_helpers import local_paths_from_mime_data


class FileListWidget(QTableWidget):
    pathsDropped = Signal(list)
    quantityChanged = Signal(str, int)
    thicknessChanged = Signal(str, float)

    HEADERS = [
        "Файл",
        "Размер",
        "Толщина",
        "Длина",
        "Длина реза",
        "Врезки",
        "Количество",
        "Цена",
    ]

    DIAGNOSTIC_HEADERS = [
        "Файл",
        "Путь",
        "Статус",
        "Тип трубы",
        "Размер / толщина",
        "Длина",
        "Толщина",
        "Метод толщины",
        "Confidence толщины",
        "Реальный рез",
        "Торцевые резы",
        "Вырезы/пазы",
        "Диагн. сумма ребер",
        "Врезки",
        "Игнор. продольные",
        "Игнор. плоскость/радиус",
        "Вспом. линии",
        "Количество",
        "Цена",
        "debug_edges.csv",
        "debug_faces.csv",
        "Ошибка",
    ]

    def __init__(self, parent=None, *, diagnostic: bool = False) -> None:
        super().__init__(parent)
        self.diagnostic = diagnostic
        self.setAcceptDrops(True)
        self.setObjectName("FileListWidget")
        headers = self.DIAGNOSTIC_HEADERS if diagnostic else self.HEADERS
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)
        self.itemChanged.connect(self._on_item_changed)

    def set_jobs(self, jobs: list[FileJob]) -> None:
        selected_paths = set(self.selected_paths())
        self.blockSignals(True)
        self.setRowCount(len(jobs))

        for row, job in enumerate(jobs):
            values = job.to_diagnostic_row() if self.diagnostic else job.to_table_row()
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job.normalized_path)
                if self._is_quantity_column(column) or self._is_thickness_column(column):
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column >= 2:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                color = _row_color(job)
                if color is not None:
                    item.setBackground(color)
                    item.setForeground(QColor("#111827"))
                self.setItem(row, column, item)

            if job.normalized_path in selected_paths:
                self.selectRow(row)
        self.blockSignals(False)

    def selected_paths(self) -> list[str]:
        rows = sorted({index.row() for index in self.selectedIndexes()})
        paths: list[str] = []
        for row in rows:
            item = self.item(row, 0)
            if item is not None:
                paths.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return paths

    def select_path(self, path: str) -> None:
        self.clearSelection()
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == path:
                self.selectRow(row)
                self.scrollToItem(item)
                return

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if local_paths_from_mime_data(event.mimeData()):
            event.acceptProposedAction()
            self._set_drop_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if local_paths_from_mime_data(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drop_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = local_paths_from_mime_data(event.mimeData())
        self._set_drop_active(False)
        if paths:
            self.pathsDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _set_drop_active(self, active: bool) -> None:
        self.setProperty("dropActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def _is_quantity_column(self, column: int) -> bool:
        headers = self.DIAGNOSTIC_HEADERS if self.diagnostic else self.HEADERS
        return 0 <= column < len(headers) and headers[column] == "Количество"

    def _is_thickness_column(self, column: int) -> bool:
        if self.diagnostic:
            return False
        headers = self.HEADERS
        return 0 <= column < len(headers) and headers[column] == "Толщина"

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        path = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if self._is_quantity_column(item.column()):
            try:
                quantity = max(1, int(item.text().strip()))
            except ValueError:
                quantity = 1
            if item.text() != str(quantity):
                self.blockSignals(True)
                item.setText(str(quantity))
                self.blockSignals(False)
            if path:
                self.quantityChanged.emit(path, quantity)
            return

        if self._is_thickness_column(item.column()):
            thickness = _number_from_text(item.text())
            if thickness <= 0.0:
                text = "—"
            else:
                text = f"{thickness:.1f} мм"
            if item.text() != text:
                self.blockSignals(True)
                item.setText(text)
                self.blockSignals(False)
            if path and thickness > 0.0:
                self.thicknessChanged.emit(path, thickness)


def _number_from_text(text: str) -> float:
    cleaned = (
        text.strip()
        .lower()
        .replace("мм", "")
        .replace(",", ".")
        .replace(" ", "")
    )
    try:
        return max(0.0, float(cleaned))
    except ValueError:
        return 0.0


def _row_color(job: FileJob) -> QColor | None:
    if job.status == STATUS_PENDING:
        return QColor("#f1f5f9")
    if job.status == STATUS_IMPORTING:
        return QColor("#dbeafe")
    if job.status == STATUS_ERROR:
        return QColor("#fee2e2")
    if job.status == STATUS_IMPORTED and job.warnings:
        return QColor("#fef3c7")
    if job.status == STATUS_IMPORTED:
        return QColor("#ecfdf5")
    return None
