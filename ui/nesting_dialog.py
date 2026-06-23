from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.file_job import FileJob
from export.vector_exporter import export_nesting_dxf, export_nesting_svg
from nesting.core import MaxRectsNestingEngine, NestingLayout, NestingPart, transformed_contours
from ui.zoom_graphics_view import ZoomGraphicsView


class NestingDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        jobs: list[tuple[FileJob, object]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nesting листовых деталей")
        self.resize(1100, 720)
        self.parts = [
            NestingPart.from_sheet_analysis(
                name=job.name,
                analysis=getattr(analysis, "sheet_analysis"),
                quantity=max(1, int(getattr(job, "quantity", 1) or 1)),
            )
            for job, analysis in jobs
            if getattr(analysis, "sheet_analysis", None) is not None
        ]
        self.layout_result: NestingLayout | None = None

        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_preview())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._refresh_part_list()
        self._run_nesting()

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)

        form = QFormLayout()
        self.sheet_width_input = QDoubleSpinBox()
        self.sheet_width_input.setRange(10.0, 10000.0)
        self.sheet_width_input.setValue(3000.0)
        self.sheet_width_input.setSuffix(" мм")
        self.sheet_width_input.setSingleStep(100.0)
        self.sheet_height_input = QDoubleSpinBox()
        self.sheet_height_input.setRange(10.0, 10000.0)
        self.sheet_height_input.setValue(1500.0)
        self.sheet_height_input.setSuffix(" мм")
        self.sheet_height_input.setSingleStep(100.0)
        self.spacing_input = QDoubleSpinBox()
        self.spacing_input.setRange(0.0, 100.0)
        self.spacing_input.setValue(3.0)
        self.spacing_input.setSuffix(" мм")
        self.spacing_input.setSingleStep(0.5)
        self.rotate_checkbox = QCheckBox("Разрешить поворот")
        self.rotate_checkbox.setChecked(True)
        self.rotation_step_input = QDoubleSpinBox()
        self.rotation_step_input.setRange(1.0, 90.0)
        self.rotation_step_input.setValue(5.0)
        self.rotation_step_input.setSuffix("°")
        self.rotation_step_input.setSingleStep(1.0)
        form.addRow("Ширина листа", self.sheet_width_input)
        form.addRow("Высота листа", self.sheet_height_input)
        form.addRow("Зазор", self.spacing_input)
        form.addRow(self.rotate_checkbox)
        form.addRow("Шаг угла", self.rotation_step_input)
        layout.addLayout(form)

        self.parts_list = QListWidget()
        layout.addWidget(QLabel("Детали"))
        layout.addWidget(self.parts_list, stretch=1)

        actions = QHBoxLayout()
        self.calculate_button = QPushButton("Рассчитать")
        self.export_dxf_button = QPushButton("DXF")
        self.export_svg_button = QPushButton("SVG")
        actions.addWidget(self.calculate_button)
        actions.addWidget(self.export_dxf_button)
        actions.addWidget(self.export_svg_button)
        layout.addLayout(actions)

        self.summary_label = QLabel("—")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.calculate_button.clicked.connect(self._run_nesting)
        self.export_dxf_button.clicked.connect(self._export_dxf)
        self.export_svg_button.clicked.connect(self._export_svg)
        self.rotate_checkbox.toggled.connect(self.rotation_step_input.setEnabled)
        return panel

    def _build_preview(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        toolbar = QHBoxLayout()
        self.fit_view_button = QPushButton("Вписать")
        toolbar.addStretch(1)
        toolbar.addWidget(self.fit_view_button)
        layout.addLayout(toolbar)
        self.scene = QGraphicsScene(self)
        self.view = ZoomGraphicsView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor("#f8fafc")))
        layout.addWidget(self.view)
        self.fit_view_button.clicked.connect(self.view.fit_scene)
        return panel

    def _refresh_part_list(self) -> None:
        self.parts_list.clear()
        for part in self.parts:
            self.parts_list.addItem(
                f"{part.name} | {part.width_mm:.1f} x {part.height_mm:.1f} мм | x{part.quantity}"
            )

    def _run_nesting(self) -> None:
        if not self.parts:
            self.summary_label.setText("Нет импортированных DXF/листовых деталей.")
            self.scene.clear()
            return
        self.layout_result = MaxRectsNestingEngine().nest(
            self.parts,
            sheet_width_mm=self.sheet_width_input.value(),
            sheet_height_mm=self.sheet_height_input.value(),
            spacing_mm=self.spacing_input.value(),
            allow_rotation=self.rotate_checkbox.isChecked(),
            rotation_step_degrees=self.rotation_step_input.value(),
        )
        self._render_layout(self.layout_result)

    def _render_layout(self, layout: NestingLayout) -> None:
        self.scene.clear()
        margin = 24.0
        sheet_gap = max(25.0, layout.spacing_mm * 4.0)
        total_height = (
            layout.sheet_count * layout.sheet_height_mm
            + max(0, layout.sheet_count - 1) * sheet_gap
        )
        self.scene.setSceneRect(
            QRectF(
                0.0,
                0.0,
                layout.sheet_width_mm + margin * 2.0,
                max(total_height, 1.0) + margin * 2.0,
            )
        )
        sheet_pen = QPen(QColor("#94a3b8"), 1.2)
        sheet_pen.setCosmetic(True)
        cut_pen = QPen(QColor("#dc2626"), 1.8)
        cut_pen.setCosmetic(True)
        bbox_pen = QPen(QColor("#cbd5e1"), 1.0)
        bbox_pen.setCosmetic(True)
        bbox_pen.setStyle(Qt.PenStyle.DashLine)

        for sheet in layout.sheets:
            offset_y = sheet.index * (layout.sheet_height_mm + sheet_gap)
            self.scene.addRect(
                QRectF(margin, margin + offset_y, sheet.width_mm, sheet.height_mm),
                sheet_pen,
                QBrush(QColor("#ffffff")),
            )
            label = self.scene.addText(
                f"Лист {sheet.index + 1} | заполнение {sheet.efficiency * 100:.1f}%"
            )
            label.setDefaultTextColor(QColor("#334155"))
            label.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            label.setPos(margin + 4.0, margin + offset_y + 4.0)

            for placement in sheet.placements:
                self.scene.addRect(
                    QRectF(
                        margin + placement.x_mm,
                        margin + offset_y + placement.y_mm,
                        placement.width_mm,
                        placement.height_mm,
                    ),
                    bbox_pen,
                )
                for contour in transformed_contours(placement):
                    points = contour.points
                    for start, end in zip(points, points[1:], strict=False):
                        self.scene.addLine(
                            margin + start.x_mm,
                            margin + offset_y + start.y_mm,
                            margin + end.x_mm,
                            margin + offset_y + end.y_mm,
                            cut_pen,
                        )
                part_label = self.scene.addText(placement.part.name)
                part_label.setDefaultTextColor(QColor("#475569"))
                part_label.setFont(QFont("Arial", 7))
                part_label.setPos(
                    margin + placement.x_mm + 2.0,
                    margin + offset_y + placement.y_mm + 2.0,
                )

        warnings = "\n".join(layout.warnings)
        self.summary_label.setText(
            f"Листов: {layout.sheet_count}; деталей: {len(layout.placements)}"
            + (f"\n{warnings}" if warnings else "")
        )
        self.view.fit_scene()

    def _export_dxf(self) -> None:
        layout = self._ensure_layout()
        if layout is None:
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт nesting DXF",
            "TubeCutCalculator-nesting.dxf",
            "DXF (*.dxf)",
        )
        if not target_path:
            return
        export_nesting_dxf(layout, target_path)
        QMessageBox.information(self, "Nesting", f"DXF сохранен: {Path(target_path).name}")

    def _export_svg(self) -> None:
        layout = self._ensure_layout()
        if layout is None:
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт nesting SVG",
            "TubeCutCalculator-nesting.svg",
            "SVG (*.svg)",
        )
        if not target_path:
            return
        export_nesting_svg(layout, target_path)
        QMessageBox.information(self, "Nesting", f"SVG сохранен: {Path(target_path).name}")

    def _ensure_layout(self) -> NestingLayout | None:
        if self.layout_result is None:
            self._run_nesting()
        return self.layout_result
