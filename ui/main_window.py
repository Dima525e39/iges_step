from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_DESCRIPTION, APP_NAME, APP_VERSION
from cad.analyzer import GeometryAnalysisResult, analyze_shape
from cad.shape_summary import ShapeSummary
from core.file_job import (
    PLACEHOLDER,
    FileJob,
    STATUS_ERROR,
    STATUS_IMPORTED,
    STATUS_IMPORTING,
    STATUS_PENDING,
)
from core.file_queue import AddFilesResult, FileQueue
from export.json_project import save_project
from settings.settings_manager import SettingsManager
from ui.drop_helpers import local_paths_from_mime_data
from ui.file_drop_area import FileDropArea
from ui.file_list_widget import FileListWidget
from ui.geometry_debug_dialog import GeometryDebugDialog
from ui.import_worker import CadImportWorker
from ui.viewer_2d import Viewer2D
from ui.viewer_3d import Viewer3D


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.queue = FileQueue()
        self.settings_manager = SettingsManager()
        self.imported_shapes: dict[str, object] = {}
        self.shape_summaries: dict[str, ShapeSummary] = {}
        self.shape_analyses: dict[str, GeometryAnalysisResult] = {}
        self.import_thread: QThread | None = None
        self.import_worker: CadImportWorker | None = None
        self.geometry_debug_dialog: GeometryDebugDialog | None = None

        self.setAcceptDrops(True)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1360, 820)

        self.drop_root = QFrame()
        self.drop_root.setObjectName("DropRoot")
        self.setCentralWidget(self.drop_root)

        self._build_ui()
        self._apply_styles()
        self._connect_signals()
        self._refresh_jobs()

        self.statusBar().showMessage(f"{APP_NAME} {APP_VERSION}")

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self.drop_root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        header = QLabel(f"{APP_NAME} {APP_VERSION}")
        header.setObjectName("HeaderLabel")
        root_layout.addWidget(header)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.addWidget(self._build_left_panel())
        content_splitter.addWidget(self._build_center_panel())
        content_splitter.addWidget(self._build_right_panel())
        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setStretchFactor(2, 0)
        content_splitter.setChildrenCollapsible(False)

        bottom_panel = self._build_bottom_panel()
        bottom_panel.setMinimumHeight(160)

        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.addWidget(content_splitter)
        self.vertical_splitter.addWidget(bottom_panel)
        self.vertical_splitter.setStretchFactor(0, 3)
        self.vertical_splitter.setStretchFactor(1, 1)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.setSizes([560, 220])
        root_layout.addWidget(self.vertical_splitter, stretch=1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(420)
        layout = QVBoxLayout(panel)

        buttons = QGridLayout()
        self.add_file_button = QPushButton("Добавить файл")
        self.add_folder_button = QPushButton("Добавить папку")
        self.clear_button = QPushButton("Очистить список")
        self.remove_button = QPushButton("Удалить выбранный")
        buttons.addWidget(self.add_file_button, 0, 0)
        buttons.addWidget(self.add_folder_button, 0, 1)
        buttons.addWidget(self.clear_button, 1, 0)
        buttons.addWidget(self.remove_button, 1, 1)
        layout.addLayout(buttons)

        self.drop_area = FileDropArea()
        layout.addWidget(self.drop_area)

        list_title = QLabel("Файлы")
        list_title.setObjectName("SectionLabel")
        layout.addWidget(list_title)

        self.compact_list = QListWidget()
        self.compact_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.compact_list, stretch=1)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.tabs = QTabWidget()
        self.viewer_3d = Viewer3D()
        self.viewer_2d = Viewer2D()
        self.calculation_placeholder = QLabel("Расчет не выполнен")
        self.calculation_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.calculation_placeholder.setWordWrap(True)

        self.tabs.addTab(self.viewer_3d, "3D-модель")
        self.tabs.addTab(self.viewer_2d, "2D-развертка")
        self.tabs.addTab(self.calculation_placeholder, "Таблица расчета")
        layout.addWidget(self.tabs)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(380)
        layout = QVBoxLayout(panel)

        params_group = QGroupBox("Параметры")
        params_layout = QFormLayout(params_group)
        self.param_name = QLabel("—")
        self.param_status = QLabel("—")
        self.param_profile = QLabel("—")
        self.param_length = QLabel("—")
        self.param_thickness = QLabel("—")
        self.param_cut = QLabel("—")
        self.param_pierces = QLabel("—")
        self.param_price = QLabel("—")
        params_layout.addRow("Файл", self.param_name)
        params_layout.addRow("Статус", self.param_status)
        params_layout.addRow("Тип трубы", self.param_profile)
        params_layout.addRow("Длина", self.param_length)
        params_layout.addRow("Толщина", self.param_thickness)
        params_layout.addRow("Длина реза", self.param_cut)
        params_layout.addRow("Врезки", self.param_pierces)
        params_layout.addRow("Стоимость", self.param_price)
        layout.addWidget(params_group)

        settings_group = QGroupBox("Настройки цен")
        settings_layout = QFormLayout(settings_group)
        pricing = self.settings_manager.get("pricing", default={})
        self.price_per_meter_input = self._make_money_input(
            float(pricing.get("price_per_meter", 120.0))
        )
        self.price_per_pierce_input = self._make_money_input(
            float(pricing.get("price_per_pierce", 15.0))
        )
        self.minimum_price_input = self._make_money_input(
            float(pricing.get("minimum_price", 0.0))
        )
        self.setup_price_input = self._make_money_input(
            float(pricing.get("setup_price", 0.0))
        )
        self.complexity_factor_input = self._make_factor_input(
            float(pricing.get("complexity_factor", 1.0))
        )
        self.markup_percent_input = self._make_percent_input(
            float(pricing.get("markup_percent", 0.0))
        )
        settings_layout.addRow("Цена за метр", self.price_per_meter_input)
        settings_layout.addRow("Цена за врезку", self.price_per_pierce_input)
        settings_layout.addRow("Минимум", self.minimum_price_input)
        settings_layout.addRow("Подготовка", self.setup_price_input)
        settings_layout.addRow("Сложность", self.complexity_factor_input)
        settings_layout.addRow("Наценка, %", self.markup_percent_input)
        layout.addWidget(settings_group)

        warnings_group = QGroupBox("Предупреждения")
        warnings_layout = QVBoxLayout(warnings_group)
        self.warning_label = QLabel("—")
        self.warning_label.setWordWrap(True)
        warnings_layout.addWidget(self.warning_label)
        layout.addWidget(warnings_group, stretch=1)

        self.geometry_debug_button = QPushButton("DEV: скрипт анализа")
        self.geometry_debug_button.setEnabled(False)
        layout.addWidget(self.geometry_debug_button)
        return panel

    def _make_money_input(self, value: float) -> QDoubleSpinBox:
        spin_box = QDoubleSpinBox()
        spin_box.setRange(0, 1_000_000)
        spin_box.setDecimals(2)
        spin_box.setSingleStep(10)
        spin_box.setValue(value)
        return spin_box

    def _make_factor_input(self, value: float) -> QDoubleSpinBox:
        spin_box = QDoubleSpinBox()
        spin_box.setRange(0.1, 100)
        spin_box.setDecimals(2)
        spin_box.setSingleStep(0.1)
        spin_box.setValue(value)
        return spin_box

    def _make_percent_input(self, value: float) -> QDoubleSpinBox:
        spin_box = QDoubleSpinBox()
        spin_box.setRange(0, 1000)
        spin_box.setDecimals(2)
        spin_box.setSingleStep(1)
        spin_box.setValue(value)
        return spin_box

    def _build_bottom_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        actions = QHBoxLayout()
        self.process_selected_button = QPushButton("Импортировать выбранный")
        self.process_all_button = QPushButton("Импортировать все")
        self.export_csv_button = QPushButton("Экспорт CSV")
        self.export_pdf_button = QPushButton("Экспорт PDF")
        self.save_project_button = QPushButton("Сохранить проект")
        self.export_csv_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)

        actions.addWidget(self.process_selected_button)
        actions.addWidget(self.process_all_button)
        actions.addStretch(1)
        actions.addWidget(self.export_csv_button)
        actions.addWidget(self.export_pdf_button)
        actions.addWidget(self.save_project_button)
        layout.addLayout(actions)

        self.file_table = FileListWidget()
        layout.addWidget(self.file_table, stretch=1)
        return panel

    def _connect_signals(self) -> None:
        self.add_file_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.clear_button.clicked.connect(self._clear_jobs)
        self.remove_button.clicked.connect(self._remove_selected_jobs)
        self.process_selected_button.clicked.connect(self._process_selected)
        self.process_all_button.clicked.connect(self._process_all)
        self.save_project_button.clicked.connect(self._save_project)
        self.drop_area.pathsDropped.connect(self._add_paths)
        self.file_table.pathsDropped.connect(self._add_paths)
        self.file_table.itemSelectionChanged.connect(self._sync_from_table_selection)
        self.compact_list.currentRowChanged.connect(self._sync_from_compact_selection)
        self.geometry_debug_button.clicked.connect(self._open_geometry_debugger)

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить CAD-файлы",
            "",
            "CAD-файлы (*.step *.stp *.iges *.igs);;Все файлы (*.*)",
        )
        if paths:
            self._add_paths(paths)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Добавить папку")
        if folder:
            self._add_paths([folder])

    def _add_paths(self, paths: list[str]) -> None:
        result = self.queue.add_paths(paths)
        self._refresh_jobs()
        self._show_add_result(result)

    def _show_add_result(self, result: AddFilesResult) -> None:
        if result.added:
            self.statusBar().showMessage(f"Добавлено файлов: {len(result.added)}", 5000)

        messages: list[str] = []
        messages.extend(f"Файл не поддерживается: {path.name}" for path in result.unsupported)
        if result.duplicates:
            messages.append(f"Дубликаты пропущены: {len(result.duplicates)}")

        if messages:
            QMessageBox.warning(self, "Добавление файлов", "\n".join(messages[:20]))

    def _clear_jobs(self) -> None:
        if len(self.queue) == 0:
            return
        self.queue.clear()
        self.imported_shapes.clear()
        self.shape_summaries.clear()
        self.shape_analyses.clear()
        self._refresh_jobs()

    def _remove_selected_jobs(self) -> None:
        paths = self.file_table.selected_paths()
        if not paths and self.compact_list.currentItem() is not None:
            paths = [self.compact_list.currentItem().data(Qt.ItemDataRole.UserRole)]
        self.queue.remove_paths(paths)
        for path in paths:
            key = str(path)
            self.imported_shapes.pop(key, None)
            self.shape_summaries.pop(key, None)
            self.shape_analyses.pop(key, None)
        self._refresh_jobs()

    def _process_selected(self) -> None:
        selected_paths = self.file_table.selected_paths()
        if not selected_paths and self.compact_list.currentItem() is not None:
            selected_paths = [self.compact_list.currentItem().data(Qt.ItemDataRole.UserRole)]
        if not selected_paths:
            QMessageBox.information(self, "Импорт", "Выберите файл в списке.")
            return
        self._start_import(selected_paths)

    def _process_all(self) -> None:
        if len(self.queue) == 0:
            QMessageBox.information(self, "Импорт", "Список файлов пуст.")
            return
        self._start_import([job.normalized_path for job in self.queue.jobs()])

    def _save_project(self) -> None:
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить проект",
            "TubeCutCalculator-project.json",
            "JSON (*.json)",
        )
        if not target_path:
            return
        save_project(self.queue.jobs(), target_path)
        self.statusBar().showMessage(f"Проект сохранен: {Path(target_path).name}", 5000)

    def _start_import(self, paths: list[str]) -> None:
        if self.import_thread is not None:
            QMessageBox.information(self, "Импорт", "Импорт уже выполняется.")
            return

        jobs = [self.queue.get(path) for path in paths]
        import_jobs = [job for job in jobs if job is not None]
        if not import_jobs:
            return

        for job in import_jobs:
            job.status = STATUS_IMPORTING
            job.tube_type = PLACEHOLDER
            job.tube_length_mm = PLACEHOLDER
            job.wall_thickness_mm = PLACEHOLDER
            job.cut_length_mm = PLACEHOLDER
            job.pierce_count = PLACEHOLDER
            job.price = PLACEHOLDER
            job.error_text = ""
            job.warnings.clear()
            self.imported_shapes.pop(job.normalized_path, None)
            self.shape_summaries.pop(job.normalized_path, None)
            self.shape_analyses.pop(job.normalized_path, None)

        self._set_import_controls_enabled(False)
        self.statusBar().showMessage(f"Импорт файлов: {len(import_jobs)}")
        self._refresh_jobs()

        self.import_thread = QThread(self)
        self.import_worker = CadImportWorker([Path(job.normalized_path) for job in import_jobs])
        self.import_worker.moveToThread(self.import_thread)
        self.import_thread.started.connect(self.import_worker.run)
        self.import_worker.progress.connect(self._on_import_progress)
        self.import_worker.failed.connect(self._on_import_failed)
        self.import_worker.finished.connect(self.import_thread.quit)
        self.import_worker.finished.connect(self.import_worker.deleteLater)
        self.import_thread.finished.connect(self._finish_import_thread)
        self.import_thread.finished.connect(self.import_thread.deleteLater)
        self.import_thread.start()

    def _on_import_progress(
        self,
        path: str,
        result: object,
        summary: object,
        analysis: object,
    ) -> None:
        job = self.queue.get(path)
        if job is None:
            return

        shape = getattr(result, "shape")
        file_format = getattr(result, "file_format", "CAD")
        shape_summary = summary
        geometry_analysis = analysis
        self.imported_shapes[job.normalized_path] = shape
        self.shape_summaries[job.normalized_path] = shape_summary
        self.shape_analyses[job.normalized_path] = geometry_analysis

        job.status = STATUS_IMPORTED
        job.tube_type = getattr(geometry_analysis, "profile_hint", str(file_format))
        job.tube_length_mm = self._format_analysis_length(geometry_analysis)
        job.wall_thickness_mm = PLACEHOLDER
        job.cut_length_mm = PLACEHOLDER
        job.pierce_count = PLACEHOLDER
        job.price = PLACEHOLDER
        job.error_text = ""
        job.warnings = [
            self._format_analysis_summary(geometry_analysis),
            "Расчет длины реза и количества врезок будет добавлен после этапа анализа геометрии.",
        ]
        analysis_warnings = getattr(geometry_analysis, "warnings", ())
        job.warnings.extend(str(warning) for warning in analysis_warnings)

        self._refresh_jobs()
        current_job = self._current_job()
        if current_job is not None and current_job.normalized_path == job.normalized_path:
            self.viewer_3d.show_shape(shape, job.name)

    def _on_import_failed(self, path: str, error_message: str) -> None:
        job = self.queue.get(path)
        if job is None:
            return

        job.status = STATUS_ERROR
        job.error_text = error_message
        job.warnings = [
            "Импорт не выполнен.",
            f"Причина: {error_message}",
        ]
        self.imported_shapes.pop(job.normalized_path, None)
        self.shape_summaries.pop(job.normalized_path, None)
        self.shape_analyses.pop(job.normalized_path, None)
        self._refresh_jobs()

    def _finish_import_thread(self) -> None:
        self.import_thread = None
        self.import_worker = None
        self._set_import_controls_enabled(True)
        imported = sum(1 for job in self.queue.jobs() if job.status == STATUS_IMPORTED)
        failed = sum(1 for job in self.queue.jobs() if job.status == STATUS_ERROR)
        self.statusBar().showMessage(
            f"Импорт завершен. Успешно: {imported}; ошибок: {failed}",
            7000,
        )

    def _set_import_controls_enabled(self, enabled: bool) -> None:
        self.process_selected_button.setEnabled(enabled)
        self.process_all_button.setEnabled(enabled)
        self.add_file_button.setEnabled(enabled)
        self.add_folder_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)

    def _format_model_length(self, summary: object) -> str:
        sizes = [
            getattr(summary, "size_x_mm", 0.0),
            getattr(summary, "size_y_mm", 0.0),
            getattr(summary, "size_z_mm", 0.0),
        ]
        return f"{max(sizes):.1f} мм"

    def _format_analysis_length(self, analysis: object) -> str:
        return (
            f"{getattr(analysis, 'length_mm', 0.0):.1f} мм "
            f"({getattr(analysis, 'length_axis', '—')})"
        )

    def _format_analysis_summary(self, analysis: object) -> str:
        return (
            "Базовый анализ геометрии выполнен. "
            f"Тип: {getattr(analysis, 'profile_hint', '—')}; "
            f"габариты: {getattr(analysis, 'size_x_mm', 0.0):.1f} x "
            f"{getattr(analysis, 'size_y_mm', 0.0):.1f} x "
            f"{getattr(analysis, 'size_z_mm', 0.0):.1f} мм; "
            f"solid: {getattr(analysis, 'solid_count', 0)}, "
            f"shell: {getattr(analysis, 'shell_count', 0)}, "
            f"граней: {getattr(analysis, 'face_count', 0)}, "
            f"ребер: {getattr(analysis, 'edge_count', 0)}."
        )

    def _format_shape_summary(self, summary: object) -> str:
        return (
            "Импорт выполнен. "
            f"Габариты: {getattr(summary, 'size_x_mm', 0.0):.1f} x "
            f"{getattr(summary, 'size_y_mm', 0.0):.1f} x "
            f"{getattr(summary, 'size_z_mm', 0.0):.1f} мм; "
            f"граней: {getattr(summary, 'face_count', 0)}, "
            f"ребер: {getattr(summary, 'edge_count', 0)}."
        )

    def _refresh_jobs(self) -> None:
        jobs = self.queue.jobs()
        self.file_table.set_jobs(jobs)
        self._refresh_compact_list(jobs)
        self._show_selected_job(self._current_job())

    def _refresh_compact_list(self, jobs: list[FileJob]) -> None:
        current_path = None
        current_item = self.compact_list.currentItem()
        if current_item is not None:
            current_path = current_item.data(Qt.ItemDataRole.UserRole)

        self.compact_list.blockSignals(True)
        self.compact_list.clear()
        for job in jobs:
            item = QListWidgetItem(f"{job.name}  |  {job.status}")
            item.setData(Qt.ItemDataRole.UserRole, job.normalized_path)
            self.compact_list.addItem(item)
            if current_path == job.normalized_path:
                self.compact_list.setCurrentItem(item)
        self.compact_list.blockSignals(False)

    def _sync_from_table_selection(self) -> None:
        selected = self.file_table.selected_paths()
        if selected:
            self.compact_list.blockSignals(True)
            self._select_compact_path(selected[0])
            self.compact_list.blockSignals(False)
        self._show_selected_job(self._current_job())

    def _sync_from_compact_selection(self, row: int) -> None:
        item = self.compact_list.item(row)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self.file_table.blockSignals(True)
        self.file_table.select_path(path)
        self.file_table.blockSignals(False)
        self._show_selected_job(self.queue.get(path))

    def _select_compact_path(self, path: str) -> None:
        for row in range(self.compact_list.count()):
            item = self.compact_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self.compact_list.setCurrentRow(row)
                return

    def _current_job(self) -> FileJob | None:
        selected_paths = self.file_table.selected_paths()
        if selected_paths:
            return self.queue.get(selected_paths[0])

        current_item = self.compact_list.currentItem()
        if current_item is None:
            return None
        return self.queue.get(current_item.data(Qt.ItemDataRole.UserRole))

    def _show_selected_job(self, job: FileJob | None) -> None:
        shape = self.imported_shapes.get(job.normalized_path) if job is not None else None
        summary = self.shape_summaries.get(job.normalized_path) if job is not None else None
        analysis = self.shape_analyses.get(job.normalized_path) if job is not None else None
        if shape is None:
            self.viewer_3d.show_job(job)
        else:
            self.viewer_3d.show_shape(shape, job.name)
        self.viewer_2d.show_job(job)
        self.geometry_debug_button.setEnabled(shape is not None)
        if self.geometry_debug_dialog is not None:
            self.geometry_debug_dialog.set_context(
                job=job,
                shape=shape,
                summary=summary,
                analysis=analysis,
            )

        if job is None:
            values = ["—"] * 8
            warnings = "—"
        else:
            values = [
                job.name,
                job.status,
                job.tube_type,
                job.tube_length_mm,
                job.wall_thickness_mm,
                job.cut_length_mm,
                job.pierce_count,
                job.price,
            ]
            warnings = "\n".join(job.warnings) if job.warnings else "—"

        labels = [
            self.param_name,
            self.param_status,
            self.param_profile,
            self.param_length,
            self.param_thickness,
            self.param_cut,
            self.param_pierces,
            self.param_price,
        ]
        for label, value in zip(labels, values, strict=True):
            label.setText(value)
        self.warning_label.setText(warnings)

    def _open_geometry_debugger(self) -> None:
        job = self._current_job()
        if job is None:
            QMessageBox.information(self, "DEV: анализ", "Выберите импортированный файл.")
            return

        shape = self.imported_shapes.get(job.normalized_path)
        if shape is None:
            QMessageBox.information(
                self,
                "DEV: анализ",
                "Сначала импортируйте выбранный файл.",
            )
            return

        summary = self.shape_summaries.get(job.normalized_path)
        analysis = self.shape_analyses.get(job.normalized_path)
        if analysis is None:
            analysis = analyze_shape(shape, summary=summary)
            self.shape_analyses[job.normalized_path] = analysis

        if self.geometry_debug_dialog is None:
            self.geometry_debug_dialog = GeometryDebugDialog(
                self,
                job=job,
                shape=shape,
                summary=summary,
                analysis=analysis,
            )
            self.geometry_debug_dialog.destroyed.connect(self._on_geometry_debugger_closed)
        else:
            self.geometry_debug_dialog.set_context(
                job=job,
                shape=shape,
                summary=summary,
                analysis=analysis,
            )
        self.geometry_debug_dialog.show()
        self.geometry_debug_dialog.raise_()
        self.geometry_debug_dialog.activateWindow()

    def _on_geometry_debugger_closed(self, *_args: object) -> None:
        self.geometry_debug_dialog = None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if local_paths_from_mime_data(event.mimeData()):
            self._set_drop_active(True)
            event.acceptProposedAction()
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
            self._add_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _set_drop_active(self, active: bool) -> None:
        self.drop_root.setProperty("dropActive", active)
        self.drop_root.style().unpolish(self.drop_root)
        self.drop_root.style().polish(self.drop_root)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f5f7fb;
            }
            #DropRoot {
                background: #f5f7fb;
                border: 2px solid transparent;
            }
            #DropRoot[dropActive="true"] {
                border: 2px solid #2f80ed;
                background: #eef5ff;
            }
            #HeaderLabel {
                font-size: 18px;
                font-weight: 700;
                color: #1f2937;
            }
            #SectionLabel {
                font-weight: 600;
                color: #374151;
            }
            #FileDropArea {
                border: 2px dashed #9ca3af;
                border-radius: 6px;
                background: #ffffff;
                color: #4b5563;
            }
            #FileDropArea[dropActive="true"],
            #FileListWidget[dropActive="true"] {
                border: 2px solid #2f80ed;
                background: #eef5ff;
            }
            QGroupBox {
                border: 1px solid #d1d5db;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #374151;
                font-weight: 600;
            }
            QPushButton {
                min-height: 30px;
                padding: 4px 10px;
            }
            QTableWidget, QListWidget, QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #d1d5db;
            }
            """
        )
