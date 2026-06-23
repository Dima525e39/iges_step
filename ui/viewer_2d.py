from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QGraphicsScene,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from cad.shape_summary import summarize_shape
from cad.sheet_analyzer import SheetAnalysisResult
from cad.unfolder import UnfoldingPreview, build_unfolding_preview
from core.file_job import FileJob
from ui.zoom_graphics_view import ZoomGraphicsView


class Viewer2D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.header = QLabel("Развертка не построена")
        self.header.setWordWrap(True)
        self.header.setObjectName("Viewer2DHeader")

        self.scene = QGraphicsScene(self)
        self.view = ZoomGraphicsView(self.scene)
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
        sheet_analysis = getattr(analysis, "sheet_analysis", None)
        if job is not None and isinstance(sheet_analysis, SheetAnalysisResult):
            self._render_sheet_analysis(job, sheet_analysis)
            return

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

    def _render_sheet_analysis(
        self,
        job: FileJob,
        analysis: SheetAnalysisResult,
    ) -> None:
        self.scene.clear()
        self.header.setText(
            f"{job.name}: листовая деталь | "
            f"рез {analysis.cut_length_mm:.1f} мм | "
            f"врезок {analysis.pierce_count}"
        )

        margin = 24.0
        width = max(analysis.width_mm, 1.0)
        height = max(analysis.height_mm, 1.0)
        self.scene.setSceneRect(
            QRectF(0.0, 0.0, width + margin * 2.0, height + margin * 2.0)
        )
        self.scene.addRect(
            QRectF(margin, margin, width, height),
            QPen(QColor("#94a3b8"), 1.0),
            QBrush(QColor("#ffffff")),
        )

        for segment in analysis.segments:
            self.scene.addLine(
                margin + segment.start.x_mm,
                margin + segment.start.y_mm,
                margin + segment.end.x_mm,
                margin + segment.end.y_mm,
                QPen(QColor("#dc2626"), 2.0),
            )

        for contour in analysis.contours:
            if not contour.points:
                continue
            point = contour.points[0]
            text = self.scene.addText(str(contour.component_id))
            text.setDefaultTextColor(QColor("#dc2626"))
            text.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            text.setPos(margin + point.x_mm + 3.0, margin + point.y_mm + 3.0)

        if not analysis.segments:
            text = self.scene.addText("Нет контуров реза")
            text.setDefaultTextColor(QColor("#64748b"))
            text.setPos(margin + 8.0, margin + 8.0)

        self._fit_scene()

    def _render_preview(self, job: FileJob, preview: UnfoldingPreview) -> None:
        self.scene.clear()
        self.header.setText(
            f"{job.name}: развертка расчета | "
            f"рез {preview.cut_length_mm:.1f} мм | "
            f"диагн. {preview.diagnostic_edge_length_mm:.1f} мм | "
            f"врезок {preview.pierce_count}"
        )

        margin = 24.0
        length = max(preview.length_mm, 1.0)
        perimeter = max(preview.perimeter_mm, 1.0)
        scene_rect = QRectF(0.0, 0.0, length + margin * 2.0, perimeter + margin * 2.0)
        self.scene.setSceneRect(scene_rect)

        self.scene.addRect(
            QRectF(margin, margin, length, perimeter),
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor("#ffffff")),
        )

        grid_pen = QPen(QColor("#e2e8f0"), 1.0)
        grid_pen.setCosmetic(True)
        for ratio in (0.25, 0.5, 0.75):
            x = margin + length * ratio
            self.scene.addLine(x, margin, x, margin + perimeter, grid_pen)
            y = margin + perimeter * ratio
            self.scene.addLine(margin, y, margin + length, y, grid_pen)

        for segment in preview.auxiliary_unfold_segments:
            self._draw_segment(segment, margin=margin, color=QColor("#94a3b8"), width=1.0)

        for segment in preview.ignored_profile_segments:
            self._draw_segment(segment, margin=margin, color=QColor("#cbd5e1"), width=1.0)

        for segment in preview.ignored_longitudinal_segments:
            self._draw_segment(
                segment,
                margin=margin,
                color=QColor("#94a3b8"),
                width=1.0,
                dashed=True,
            )

        for segment in preview.ignored_plane_radius_segments:
            self._draw_segment(
                segment,
                margin=margin,
                color=QColor("#64748b"),
                width=1.0,
                dashed=True,
            )

        for segment in preview.uncertain_segments:
            self._draw_segment(
                segment,
                margin=margin,
                color=QColor("#f59e0b"),
                width=1.5,
                dashed=True,
            )

        for segment in preview.calculated_cut_segments:
            color = _segment_color(segment.edge_type)
            self._draw_segment(segment, margin=margin, color=color, width=3.0)
            if segment.component_id >= 0:
                text = self.scene.addText(str(segment.component_id + 1))
                text.setDefaultTextColor(color)
                text.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                text.setPos(
                    margin + (segment.start.x_mm + segment.end.x_mm) / 2.0 + 3.0,
                    margin + (segment.start.y_mm + segment.end.y_mm) / 2.0 + 3.0,
                )

        if not preview.calculated_cut_segments:
            text = self.scene.addText("Нет отмеченных контуров")
            text.setDefaultTextColor(QColor("#64748b"))
            text.setPos(margin + 8.0, margin + 8.0)

        self._fit_scene()

    def _draw_segment(
        self,
        segment: object,
        *,
        margin: float,
        color: QColor,
        width: float,
        dashed: bool = False,
    ) -> None:
        pen = QPen(color, width)
        pen.setCosmetic(True)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.scene.addLine(
            margin + segment.start.x_mm,
            margin + segment.start.y_mm,
            margin + segment.end.x_mm,
            margin + segment.end.y_mm,
            pen,
        )

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
        self.view.fit_scene()


def _longest_axis(summary: object) -> str:
    sizes = {
        "X": float(getattr(summary, "size_x_mm", 0.0) or 0.0),
        "Y": float(getattr(summary, "size_y_mm", 0.0) or 0.0),
        "Z": float(getattr(summary, "size_z_mm", 0.0) or 0.0),
    }
    return max(sizes.items(), key=lambda item: item[1])[0]


def _segment_color(edge_type: str) -> QColor:
    if edge_type == "CUT_END":
        return QColor("#dc2626")
    if edge_type == "CUT_FEATURE":
        return QColor("#dc2626")
    return QColor("#f97316")
