from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.file_job import FileJob


class Viewer2D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.label = QLabel("Развертка не построена")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

    def show_job(self, job: FileJob | None) -> None:
        if job is None:
            self.label.setText("Развертка не построена")
            return
        self.label.setText(f"{job.name}\n2D-развертка будет подключена в v0.5.0")
