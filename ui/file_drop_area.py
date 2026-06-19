from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ui.drop_helpers import local_paths_from_mime_data


class FileDropArea(QFrame):
    pathsDropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("FileDropArea")
        self.setMinimumHeight(96)

        label = QLabel("Перетащите STEP / STP / IGES / IGS")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(label)

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
