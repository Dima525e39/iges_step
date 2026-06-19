from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.file_job import FileJob


class Viewer3D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.label = QLabel("Модель не загружена")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

    def show_job(self, job: FileJob | None) -> None:
        if job is None:
            self.label.setText("Модель не загружена")
            return
        self.label.setText(f"{job.name}\n3D-просмотр будет подключен в v0.2.0")
