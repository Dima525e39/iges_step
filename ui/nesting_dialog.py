from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QThread, Qt, Signal, Slot
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
from nesting.core import (
    MaxRectsNestingEngine,
    NestingCancelled,
    NestingLayout,
    NestingPart,
    TrueShapeNestingEngine,
    transformed_contours,
)
from ui.zoom_graphics_view import ZoomGraphicsView


class _NestingWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        *,
        parts: tuple[NestingPart, ...],
        use_true_shape: bool,
        sheet_width_mm: float,
        sheet_height_mm: float,
        spacing_mm: float,
        allow_rotation: bool,
        rotation_step_degrees: float,
    ) -> None:
        super().__init__()
        self.parts = parts
        self.use_true_shape = use_true_shape
        self.sheet_width_mm = sheet_width_mm
        self.sheet_height_mm = sheet_height_mm
        self.spacing_mm = spacing_mm
        self.allow_rotation = allow_rotation
        self.rotation_step_degrees = rotation_step_degrees

    @Slot()
    def run(self) -> None:
        try:
            engine = TrueShapeNestingEngine() if self.use_true_shape else MaxRectsNestingEngine()
            layout = engine.nest(
                self.parts,
                sheet_width_mm=self.sheet_width_mm,
                sheet_height_mm=self.sheet_height_mm,
                spacing_mm=self.spacing_mm,
                allow_rotation=self.allow_rotation,
                rotation_step_degrees=self.rotation_step_degrees,
                progress_callback=self.progress.emit,
                should_cancel=lambda: QThread.currentThread().isInterruptionRequested(),
            )
            self.finished.emit(layout)
        except NestingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{exc.__class__.__name__}: {exc}")


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
        self._thread: QThread | None = None
        self._worker: _NestingWorker | None = None

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
        self.true_shape_checkbox = QCheckBox("True-shape / NFP")
        self.true_shape_checkbox.setChecked(True)
        self.rotation_step_input = QDoubleSpinBox()
        self.rotation_step_input.setRange(1.0, 90.0)
        self.rotation_step_input.setValue(5.0)
        self.rotation_step_input.setSuffix("°")
        self.rotation_step_input.setSingleStep(1.0)
        form.addRow("Ширина листа", self.sheet_width_input)
        form.addRow("Высота листа", self.sheet_height_input)
        form.addRow("Зазор", self.spacing_input)
        form.addRow(self.true_shape_checkbox)
        form.addRow(self.rotate_checkbox)
        form.addRow("Шаг угла", self.rotation_step_input)
        layout.addLayout(form)

        self.parts_list = QListWidget()
        layout.addWidget(QLabel("Детали"))
        layout.addWidget(self.parts_list, stretch=1)

        actions = QHBoxLayout()
        self.calculate_button = QPushButton("Рассчитать")
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setEnabled(False)
        self.export_dxf_button = QPushButton("DXF")
        self.export_svg_button = QPushButton("SVG")
        actions.addWidget(self.calculate_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.export_dxf_button)
        actions.addWidget(self.export_svg_button)
        layout.addLayout(actions)

        self.summary_label = QLabel("—")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.calculate_button.clicked.connect(self._run_nesting)
        self.cancel_button.clicked.connect(self._cancel_nesting)
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
        if self._thread is not None and self._thread.isRunning():
            return
        self.calculate_button.setEnabled(False)
        self.summary_label.setText("Расчет nesting...")
        self._set_busy(True)

        thread = QThread(self)
        worker = _NestingWorker(
            parts=tuple(self.parts),
            use_true_shape=self.true_shape_checkbox.isChecked(),
            sheet_width_mm=self.sheet_width_input.value(),
            sheet_height_mm=self.sheet_height_input.value(),
            spacing_mm=self.spacing_input.value(),
            allow_rotation=self.rotate_checkbox.isChecked(),
            rotation_step_degrees=self.rotation_step_input.value(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.summary_label.setText)
        worker.finished.connect(self._nesting_finished)
        worker.failed.connect(self._nesting_failed)
        worker.cancelled.connect(self._nesting_cancelled)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._nesting_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _cancel_nesting(self) -> None:
        if self._thread is None or not self._thread.isRunning():
            return
        self.summary_label.setText("Остановка расчета nesting...")
        self._thread.requestInterruption()

    @Slot(object)
    def _nesting_finished(self, layout: object) -> None:
        if isinstance(layout, NestingLayout):
            self.layout_result = layout
            self._render_layout(layout)

    @Slot(str)
    def _nesting_failed(self, message: str) -> None:
        self.summary_label.setText("Nesting не выполнен.")
        QMessageBox.warning(self, "Nesting", f"Расчет nesting не выполнен:\n{message}")

    @Slot()
    def _nesting_cancelled(self) -> None:
        self.summary_label.setText("Расчет nesting отменен.")

    @Slot()
    def _nesting_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.calculate_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.export_dxf_button.setEnabled(not busy and self.layout_result is not None)
        self.export_svg_button.setEnabled(not busy and self.layout_result is not None)
        self.sheet_width_input.setEnabled(not busy)
        self.sheet_height_input.setEnabled(not busy)
        self.spacing_input.setEnabled(not busy)
        self.true_shape_checkbox.setEnabled(not busy)
        self.rotate_checkbox.setEnabled(not busy)
        self.rotation_step_input.setEnabled(not busy and self.rotate_checkbox.isChecked())

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

    def closeEvent(self, event: object) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)
