from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from core.file_job import FileJob
from ui.drop_helpers import local_paths_from_mime_data


class FileListWidget(QTableWidget):
    pathsDropped = Signal(list)

    HEADERS = [
        "Имя файла",
        "Путь",
        "Статус",
        "Тип трубы",
        "Длина",
        "Толщина",
        "Реальный рез",
        "Диагн. сумма ребер",
        "Врезки",
        "Игнор. продольные",
        "Вспом. линии",
        "Стоимость",
        "Ошибка",
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("FileListWidget")
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setStretchLastSection(True)

    def set_jobs(self, jobs: list[FileJob]) -> None:
        selected_paths = set(self.selected_paths())
        self.setRowCount(len(jobs))

        for row, job in enumerate(jobs):
            for column, value in enumerate(job.to_table_row()):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job.normalized_path)
                if column >= 4:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                    )
                self.setItem(row, column, item)

            if job.normalized_path in selected_paths:
                self.selectRow(row)

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
