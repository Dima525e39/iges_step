from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from cad.shape_summary import summarize_shape
from cad.unfolder import UnfoldingPreview, build_unfolding_preview
from core.file_job import FileJob


class Viewer2D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.header = QLabel("Развертка не построена")
        self.header.setWordWrap(True)
        self.header.setObjectName("Viewer2DHeader")

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setBackgroundBrush(QBrush(QColor("#f8fafc")))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.header)
        layout.addWidget(self.view, stretch=1)
        self._clear_scene()

    def show_job(self, job: FileJob | None) -> None:
        if job is None:
            self.header.setText("Развертка не построена")
            self._clear_scene()
            return
        self.header.setText(f"{job.name}: модель еще не импортирована")
        self._clear_scene()

    def show_unfolding(
        self,
        job: FileJob | None,
        *,
        shape: object | None,
        summary: object | None,
        analysis: object | None,
    ) -> None:
        if job is None or shape is None:
            self.show_job(job)
            return

        try:
            if summary is None:
                summary = summarize_shape(shape)
            length_axis = str(getattr(analysis, "length_axis", "") or _longest_axis(summary))
            preview = build_unfolding_preview(
                shape,
                summary=summary,  # type: ignore[arg-type]
                length_axis=length_axis,
            )
        except Exception as exc:
            self.header.setText(f"{job.name}: развертка не построена ({exc})")
            self._clear_scene()
            return

        self._render_preview(job, preview)

    def _render_preview(self, job: FileJob, preview: UnfoldingPreview) -> None:
        self.scene.clear()
        self.header.setText(
            f"{job.name}: развертка расчета | "
            f"рез {preview.cut_length_mm:.1f} мм | "
            f"врезок {preview.pierce_count}"
        )

        margin = 24.0
        length = max(preview.length_mm, 1.0)
        perimeter = max(preview.perimeter_mm, 1.0)
        scene_rect = QRectF(0.0, 0.0, length + margin * 2.0, perimeter + margin * 2.0)
        self.scene.setSceneRect(scene_rect)

        frame_pen = QPen(QColor("#94a3b8"), 1.0)
        frame_pen.setCosmetic(True)
        self.scene.addRect(
            QRectF(margin, margin, length, perimeter),
            frame_pen,
            QBrush(QColor("#ffffff")),
        )

        grid_pen = QPen(QColor("#e2e8f0"), 1.0)
        grid_pen.setCosmetic(True)
        for ratio in (0.25, 0.5, 0.75):
            x = margin + length * ratio
            self.scene.addLine(x, margin, x, margin + perimeter, grid_pen)
            y = margin + perimeter * ratio
            self.scene.addLine(margin, y, margin + length, y, grid_pen)

        for segment in preview.segments:
            color = _segment_color(segment.reason)
            pen = QPen(color, 3.0)
            pen.setCosmetic(True)
            self.scene.addLine(
                margin + segment.start.x_mm,
                margin + segment.start.y_mm,
                margin + segment.end.x_mm,
                margin + segment.end.y_mm,
                pen,
            )

            text = self.scene.addText(str(segment.component_id + 1))
            text.setDefaultTextColor(color)
            text.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            text.setPos(
                margin + (segment.start.x_mm + segment.end.x_mm) / 2.0 + 3.0,
                margin + (segment.start.y_mm + segment.end.y_mm) / 2.0 + 3.0,
            )

        if not preview.segments:
            text = self.scene.addText("Нет отмеченных контуров")
            text.setDefaultTextColor(QColor("#64748b"))
            text.setPos(margin + 8.0, margin + 8.0)

        self._fit_scene()

    def _clear_scene(self) -> None:
        self.scene.clear()
        self.scene.setSceneRect(QRectF(0.0, 0.0, 420.0, 260.0))
        text = self.scene.addText("Развертка появится после импорта CAD-модели")
        text.setDefaultTextColor(QColor("#64748b"))
        text.setPos(24.0, 24.0)
        self._fit_scene()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._fit_scene()

    def _fit_scene(self) -> None:
        self.view.fitInView(
            self.scene.sceneRect().adjusted(-8.0, -8.0, 8.0, 8.0),
            Qt.AspectRatioMode.KeepAspectRatio,
        )


def _longest_axis(summary: object) -> str:
    sizes = {
        "X": float(getattr(summary, "size_x_mm", 0.0) or 0.0),
        "Y": float(getattr(summary, "size_y_mm", 0.0) or 0.0),
        "Z": float(getattr(summary, "size_z_mm", 0.0) or 0.0),
    }
    return max(sizes.items(), key=lambda item: item[1])[0]


def _segment_color(reason: str) -> QColor:
    if reason == "unfolded tube end":
        return QColor("#2563eb")
    if "inner" in reason:
        return QColor("#dc2626")
    return QColor("#f97316")
