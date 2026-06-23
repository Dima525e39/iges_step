from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


class ZoomGraphicsView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self._zoom_level = 0
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        factor = 1.18 if event.angleDelta().y() > 0 else 1.0 / 1.18
        next_level = self._zoom_level + (1 if factor > 1.0 else -1)
        if not -12 <= next_level <= 24:
            event.accept()
            return
        self._zoom_level = next_level
        self.scale(factor, factor)
        event.accept()

    def fit_scene(self) -> None:
        scene_rect = self.scene().sceneRect()
        if scene_rect.isNull():
            return
        self.resetTransform()
        self._zoom_level = 0
        self.fitInView(
            scene_rect.adjusted(-8.0, -8.0, 8.0, 8.0),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
