from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.file_job import FileJob


class Viewer3D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._canvas = None
        self._display = None

        self.label = QLabel("Модель не загружена")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.label)

    def show_job(self, job: FileJob | None) -> None:
        if job is None:
            self.show_message("Модель не загружена")
            return
        self.show_message(f"{job.name}\nИмпортируйте файл, чтобы открыть 3D-просмотр.")

    def show_shape(self, shape: object, title: str = "") -> None:
        if not self._ensure_occ_canvas():
            return

        try:
            self._display.EraseAll()
            self._display.DisplayShape(shape, update=True)
            self._display.FitAll()
            self.label.hide()
            self._canvas.show()
        except Exception as exc:
            name = f"{title}\n" if title else ""
            self.show_message(f"{name}Не удалось показать 3D-модель:\n{exc}")

    def show_message(self, message: str) -> None:
        if self._canvas is not None:
            self._canvas.hide()
        self.label.setText(message)
        self.label.show()

    def _ensure_occ_canvas(self) -> bool:
        if self._canvas is not None and self._display is not None:
            return True

        try:
            from OCC.Display.backend import load_backend

            load_backend("pyside6")
            from OCC.Display.qtDisplay import qtViewer3d

            self._canvas = qtViewer3d(self)
            self._canvas.InitDriver()
            self._display = self._canvas._display
            self._layout.addWidget(self._canvas, stretch=1)
            return True
        except Exception as exc:
            self.show_message(
                "3D-просмотрщик недоступен.\n"
                "Установите окружение из environment.yml и pythonocc-core.\n"
                f"{exc}"
            )
            return False
