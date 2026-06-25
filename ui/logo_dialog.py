from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from settings.logo_manager import logo_path_from_settings
from settings.settings_manager import SettingsManager


class LogoDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Логотип")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        self.preview.setStyleSheet("border: 1px solid #cbd5e1; background: #ffffff;")
        layout.addWidget(self.preview, stretch=1)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        actions = QHBoxLayout()
        self.load_button = QPushButton("Загрузить")
        self.delete_button = QPushButton("Удалить")
        self.close_button = QPushButton("Закрыть")
        actions.addWidget(self.load_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.load_button.clicked.connect(self._load_logo)
        self.delete_button.clicked.connect(self._delete_logo)
        self.close_button.clicked.connect(self.accept)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not hasattr(self, "delete_button"):
            return
        path = logo_path_from_settings(self.settings_manager.as_dict())
        self.delete_button.setEnabled(bool(path))
        if not path:
            self.preview.setText("Логотип не установлен")
            self.preview.setPixmap(QPixmap())
            self.path_label.setText("—")
            return

        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.preview.setText("Не удалось открыть логотип")
            self.preview.setPixmap(QPixmap())
            self.path_label.setText(path)
            return

        self.preview.setText("")
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.path_label.setText(path)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._refresh_preview()

    def _load_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбрать логотип",
            "",
            "Изображения (*.png *.jpg *.jpeg)",
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "Логотип", "Не удалось открыть выбранное изображение.")
            return
        self.settings_manager.set("logo", value={"path": path})
        self.settings_manager.save()
        self._refresh_preview()

    def _delete_logo(self) -> None:
        self.settings_manager.set("logo", value={"path": ""})
        self.settings_manager.save()
        self._refresh_preview()
