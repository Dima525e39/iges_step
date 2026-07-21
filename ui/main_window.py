from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
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
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_NAME, APP_VERSION, build_label
from cad.analyzer import GeometryAnalysisResult, analyze_shape
from cad.shape_summary import ShapeSummary
from core.dev_reloader import reload_calculation_core
from core.file_job import (
    PLACEHOLDER,
    FileJob,
    STATUS_ERROR,
    STATUS_IMPORTED,
    STATUS_IMPORTING,
    STATUS_PENDING,
    has_explicit_quantity_in_filename,
)
from core.file_queue import AddFilesResult, FileQueue
from core.specification_importer import load_quantity_specification, quantity_for_file
from export.csv_exporter import export_jobs_to_csv
from export.excel_exporter import export_excel_workbook
from export.json_project import load_project, save_project
from export.pdf_commercial_offer import export_commercial_offer_pdf
from export.pdf_technical_report import export_technical_report_pdf
from export.print_manager import print_html
from export.report_html import calculation_table_html, commercial_offer_html, technical_report_html
from export.vector_exporter import export_sheet_dxf, export_sheet_svg
from pricing.price_selector import calculate_job_price
from pricing.material_cost import calculate_tube_material_cost
from purchase.tube_grouping import number_from_text
from purchase.tube_purchase_calculator import TubePurchaseRow, calculate_tube_purchase
from settings.contractors_manager import contractors_from_settings, default_contractor
from settings.materials_manager import default_material, materials_from_settings
from settings.settings_manager import SettingsManager
from settings.tube_purchase_settings import TubePurchaseSettings
from ui.commercial_offer_dialog import CommercialOfferDialog
from ui.contractors_dialog import ContractorsDialog
from ui.drop_helpers import local_paths_from_mime_data
from ui.excel_preview_dialog import ExcelPreviewDialog
from ui.file_drop_area import FileDropArea
from ui.file_list_widget import FileListWidget
from ui.geometry_debug_dialog import GeometryDebugDialog
from ui.import_worker import CadImportWorker
from ui.invoice_export_dialog import InvoiceExportDialog
from ui.logo_dialog import LogoDialog
from ui.material_selection_dialog import MaterialSelectionDialog
from ui.materials_dialog import MaterialsDialog
from ui.nesting_dialog import NestingDialog
from ui.pricing_dialog import PricingDialog
from ui.settings_dialog import GeneralSettingsDialog
from ui.stock_purchase_widget import StockPurchaseWidget
from ui.theme_manager import apply_theme
from ui.top_menu import install_top_menu
from ui.tube_purchase_settings_dialog import TubePurchaseSettingsDialog
from ui.tube_price_dialog import TubePriceDialog
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
        self.purchase_rows: list[TubePurchaseRow] = []
        self.import_thread: QThread | None = None
        self.import_worker: CadImportWorker | None = None
        self.geometry_debug_dialog: GeometryDebugDialog | None = None
        self._shown_3d_path: str | None = None
        self._shown_2d_path: str | None = None
        self._initial_screen_fit_done = False

        self.setAcceptDrops(True)
        self.setWindowTitle(f"{APP_NAME} {build_label()}")

        self.drop_root = QFrame()
        self.drop_root.setObjectName("DropRoot")
        self.setCentralWidget(self.drop_root)

        install_top_menu(self)
        self._build_ui()
        self._apply_current_theme()
        self._fit_to_screen()
        self._connect_signals()
        self._refresh_jobs()

        self.statusBar().showMessage(f"{APP_NAME} {build_label()}")

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        if self._initial_screen_fit_done:
            return
        self._initial_screen_fit_done = True
        QTimer.singleShot(0, self._fit_to_screen)
        QTimer.singleShot(150, self._fit_to_screen)

    def _fit_to_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1200, 720)
            return

        available = screen.availableGeometry()
        safe_width = max(320, available.width() - 24)
        safe_height = max(320, available.height() - 48)
        width = min(1360, safe_width, max(760, int(available.width() * 0.92)))
        height = min(820, safe_height, max(520, int(available.height() * 0.88)))
        self.resize(width, height)

        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        if frame.left() < available.left():
            frame.moveLeft(available.left())
        if frame.top() < available.top():
            frame.moveTop(available.top())
        if frame.right() > available.right():
            frame.moveRight(available.right())
        if frame.bottom() > available.bottom():
            frame.moveBottom(available.bottom())
        self.move(frame.topLeft())

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self.drop_root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        header = QLabel(f"{APP_NAME} {build_label()}")
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
        bottom_panel.setMinimumHeight(72)

        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.addWidget(content_splitter)
        self.vertical_splitter.addWidget(bottom_panel)
        self.vertical_splitter.setStretchFactor(0, 3)
        self.vertical_splitter.setStretchFactor(1, 1)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.setSizes([520, 84])
        root_layout.addWidget(self.vertical_splitter, stretch=1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(280)
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
        self.file_table = FileListWidget()
        self.diagnostic_table = FileListWidget(diagnostic=True)
        self.stock_purchase_widget = StockPurchaseWidget()

        self.tabs.addTab(self.viewer_3d, "3D-модель")
        self.tabs.addTab(self.viewer_2d, "2D-развертка")
        self.tabs.addTab(self.file_table, "Таблица расчета")
        self.tabs.addTab(self.stock_purchase_widget, "Закупка трубы")
        self.tabs.addTab(self.diagnostic_table, "Диагностика")
        layout.addWidget(self.tabs)
        return panel

    def _build_right_panel(self) -> QWidget:
        outer_panel = QWidget()
        outer_panel.setMinimumWidth(280)
        outer_panel.setMaximumWidth(460)
        outer_layout = QVBoxLayout(outer_panel)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # Wrap long values within the panel instead of forcing a horizontal
        # scrollbar that hides the text.
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        outer_layout.addWidget(scroll_area)

        panel = QWidget()
        layout = QVBoxLayout(panel)

        params_group = QGroupBox("Параметры")
        params_layout = QFormLayout(params_group)
        # Wrap long rows under their label and let fields grow, so values stay
        # fully readable inside the fixed-width side panel.
        params_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        params_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        params_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.param_name = self._value_label()
        self.param_status = self._value_label()
        self.param_profile = self._value_label()
        self.param_length = self._value_label()
        self.param_thickness = self._value_label()
        self.param_thickness_method = self._value_label()
        self.param_thickness_confidence = self._value_label()
        self.param_cut = self._value_label()
        self.param_cut_end = self._value_label()
        self.param_cut_feature = self._value_label()
        self.param_diagnostic_cut = self._value_label()
        self.param_pierces = self._value_label()
        self.param_ignored_longitudinal = self._value_label()
        self.param_ignored_plane_radius = self._value_label()
        self.param_auxiliary_unfold = self._value_label()
        self.param_debug_edges = self._value_label()
        self.param_material = self._value_label()
        self.param_customer_tube = self._value_label()
        self.param_contractor = self._value_label()
        self.param_price_rule = self._value_label()
        self.param_price = self._value_label()
        params_layout.addRow("Файл", self.param_name)
        params_layout.addRow("Статус", self.param_status)
        params_layout.addRow("Тип трубы", self.param_profile)
        params_layout.addRow("Длина", self.param_length)
        params_layout.addRow("Толщина", self.param_thickness)
        params_layout.addRow("Метод толщины", self.param_thickness_method)
        params_layout.addRow("Confidence толщины", self.param_thickness_confidence)
        params_layout.addRow("Реальный рез", self.param_cut)
        params_layout.addRow("Торцевые резы", self.param_cut_end)
        params_layout.addRow("Вырезы/пазы", self.param_cut_feature)
        params_layout.addRow("Диагн. сумма ребер", self.param_diagnostic_cut)
        params_layout.addRow("Врезки", self.param_pierces)
        params_layout.addRow("Игнор. продольные", self.param_ignored_longitudinal)
        params_layout.addRow("Игнор. плоскость/радиус", self.param_ignored_plane_radius)
        params_layout.addRow("Вспом. линии", self.param_auxiliary_unfold)
        params_layout.addRow("debug_edges.csv", self.param_debug_edges)
        params_layout.addRow("Материал", self.param_material)
        params_layout.addRow("Труба заказчика", self.param_customer_tube)
        params_layout.addRow("Контрагент", self.param_contractor)
        params_layout.addRow("Правило цены", self.param_price_rule)
        params_layout.addRow("Стоимость", self.param_price)
        layout.addWidget(params_group)

        geometry_group = QGroupBox("Анализ")
        geometry_layout = QFormLayout(geometry_group)
        self.manual_thickness_checkbox = QCheckBox("Ручная толщина")
        self.manual_thickness_input = QDoubleSpinBox()
        self.manual_thickness_input.setRange(0.0, 1000.0)
        self.manual_thickness_input.setDecimals(3)
        self.manual_thickness_input.setSingleStep(0.5)
        self.manual_thickness_input.setSuffix(" мм")
        self.manual_thickness_input.setEnabled(False)
        self.debug_edges_checkbox = QCheckBox("debug_edges.csv")
        self.rebuild_iges_solid_button = QPushButton("Точный IGES: собрать solid")
        self.rebuild_iges_solid_button.setEnabled(False)
        self.inventor_iges_button = QPushButton("IGES через Inventor")
        self.inventor_iges_button.setEnabled(False)
        geometry_layout.addRow(self.manual_thickness_checkbox, self.manual_thickness_input)
        geometry_layout.addRow(self.debug_edges_checkbox)
        geometry_layout.addRow(self.rebuild_iges_solid_button)
        geometry_layout.addRow(self.inventor_iges_button)
        layout.addWidget(geometry_group)

        pricing_group = QGroupBox("Стоимость")
        pricing_layout = QFormLayout(pricing_group)
        self.pricing_hint_label = QLabel("Цены редактируются в меню Настройки / Цены.")
        self.pricing_hint_label.setWordWrap(True)
        pricing_layout.addRow(self.pricing_hint_label)
        layout.addWidget(pricing_group)

        warnings_group = QGroupBox("Предупреждения")
        warnings_layout = QVBoxLayout(warnings_group)
        self.warning_label = self._value_label()
        warnings_layout.addWidget(self.warning_label)
        layout.addWidget(warnings_group, stretch=1)

        self.geometry_debug_button = QPushButton("DEV: скрипт анализа")
        self.geometry_debug_button.setEnabled(False)
        layout.addWidget(self.geometry_debug_button)
        scroll_area.setWidget(panel)
        return outer_panel

    def _value_label(self, text: str = "—") -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        return label

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
        self.process_selected_button = QPushButton("Обработать выбранный")
        self.process_all_button = QPushButton("Обработать все")
        self.process_all_button.setObjectName("PrimaryButton")
        self.export_csv_button = QPushButton("Экспорт CSV")
        self.export_excel_button = QPushButton("Экспорт Excel")
        self.export_pdf_button = QPushButton("PDF счет")
        self.export_dxf_button = QPushButton("DXF")
        self.export_svg_button = QPushButton("SVG")
        self.nesting_button = QPushButton("Nesting")
        self.save_project_button = QPushButton("Сохранить проект")

        actions.addWidget(self.process_selected_button)
        actions.addWidget(self.process_all_button)
        actions.addStretch(1)
        self.nesting_button.setVisible(False)
        self.export_dxf_button.setVisible(False)
        self.export_svg_button.setVisible(False)
        self.export_csv_button.setVisible(False)
        actions.addWidget(self.export_excel_button)
        actions.addWidget(self.export_pdf_button)
        actions.addWidget(self.save_project_button)
        layout.addLayout(actions)

        self.summary_label = QLabel("Файлов: 0 | Успешно: 0 | Ошибок: 0 | Итого: 0.00 руб.")
        self.summary_label.setObjectName("SummaryLabel")
        layout.addWidget(self.summary_label)
        return panel

    def _connect_signals(self) -> None:
        self.add_file_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.clear_button.clicked.connect(self._clear_jobs)
        self.remove_button.clicked.connect(self._remove_selected_jobs)
        self.process_selected_button.clicked.connect(self._process_selected)
        self.process_all_button.clicked.connect(self._process_all)
        self.save_project_button.clicked.connect(self._save_project)
        self.export_csv_button.clicked.connect(self._export_csv)
        self.export_excel_button.clicked.connect(self._export_excel)
        self.export_pdf_button.clicked.connect(self._export_commercial_pdf)
        self.export_dxf_button.clicked.connect(self._export_current_sheet_dxf)
        self.export_svg_button.clicked.connect(self._export_current_sheet_svg)
        self.nesting_button.clicked.connect(self._open_nesting)
        self.drop_area.pathsDropped.connect(self._add_paths)
        self.file_table.pathsDropped.connect(self._add_paths)
        self.file_table.quantityChanged.connect(self._on_job_quantity_changed)
        self.file_table.thicknessChanged.connect(self._on_job_thickness_changed)
        self.file_table.materialChanged.connect(self._on_job_material_changed)
        self.diagnostic_table.quantityChanged.connect(self._on_job_quantity_changed)
        self.file_table.itemSelectionChanged.connect(self._sync_from_table_selection)
        self.diagnostic_table.itemSelectionChanged.connect(self._sync_from_diagnostic_selection)
        self.compact_list.currentRowChanged.connect(self._sync_from_compact_selection)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.geometry_debug_button.clicked.connect(self._open_geometry_debugger)
        self.rebuild_iges_solid_button.clicked.connect(self._rebuild_selected_iges_solid)
        self.inventor_iges_button.clicked.connect(self._process_selected_iges_with_inventor)
        self.manual_thickness_checkbox.toggled.connect(self.manual_thickness_input.setEnabled)

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить CAD-файлы",
            "",
            "CAD-файлы (*.step *.stp *.iges *.igs *.dxf);;Все файлы (*.*)",
        )
        if paths:
            self._add_paths(paths)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Добавить папку")
        if folder:
            self._add_paths([folder])

    def _add_paths(self, paths: list[str]) -> None:
        result = self.queue.add_paths(paths)
        self._apply_default_settings_to_jobs(result.added, force=True)
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

    def _apply_default_settings_to_jobs(self, jobs: list[FileJob], *, force: bool = False) -> None:
        settings = self.settings_manager.as_dict()
        contractor = default_contractor(settings)
        material = default_material(settings)
        material_names = {item.name for item in materials_from_settings(settings) if item.active}
        if material.name:
            material_names.add(material.name)
        for job in jobs:
            if force or not job.contractor:
                job.contractor = contractor.name
            job.currency = contractor.currency
            if force or not job.material or job.material not in material_names:
                job.material = material.name

    def _clear_jobs(self) -> None:
        if len(self.queue) == 0:
            return
        self.queue.clear()
        self.imported_shapes.clear()
        self.shape_summaries.clear()
        self.shape_analyses.clear()
        self.purchase_rows.clear()
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

    def _rebuild_selected_iges_solid(self) -> None:
        job = self._current_job()
        if job is None:
            QMessageBox.information(self, "Точный IGES", "Выберите IGES-файл в списке.")
            return
        if job.path.suffix.casefold() not in {".iges", ".igs"}:
            QMessageBox.information(
                self,
                "Точный IGES",
                "Точный режим восстановления solid доступен только для IGES / IGS.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Точный IGES",
            "Программа попробует сшить поверхности IGES и собрать твердое тело.\n"
            "На тяжелых файлах это может занять заметное время.\n\n"
            f"Запустить для файла {job.name}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._start_import([job.normalized_path], force_iges_solid_healing=True)

    def _process_selected_iges_with_inventor(self) -> None:
        job = self._current_job()
        if job is None:
            QMessageBox.information(self, "IGES через Inventor", "Выберите IGES-файл в списке.")
            return
        if not self._job_is_iges(job):
            QMessageBox.information(
                self,
                "IGES через Inventor",
                "Конвертация через Inventor доступна только для IGES / IGS.",
            )
            return

        answer = QMessageBox.question(
            self,
            "IGES через Inventor",
            "Программа попробует открыть IGES в Autodesk Inventor, "
            "сохранить временный STEP и рассчитать уже STEP-модель.\n\n"
            "Inventor должен быть установлен на этом Windows-компьютере.\n\n"
            f"Запустить для файла {job.name}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._start_import([job.normalized_path], use_inventor_iges_conversion=True)

    def _process_all(self) -> None:
        if len(self.queue) == 0:
            QMessageBox.information(self, "Импорт", "Список файлов пуст.")
            return
        jobs = self.queue.jobs()
        material, contractor, customer_tube = self._choose_material_for_bulk_processing(jobs)
        if not material:
            return
        self._set_bulk_parameters_for_jobs(
            jobs,
            material=material,
            contractor=contractor,
            customer_tube=customer_tube,
        )
        self._start_import([job.normalized_path for job in jobs])

    def _save_project(self) -> None:
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить проект",
            "TubeCutCalculator-project.json",
            "JSON (*.json)",
        )
        if not target_path:
            return
        save_project(
            self.queue.jobs(),
            target_path,
            settings=self.settings_manager.as_dict(),
            purchase_rows=[asdict(row) for row in self.purchase_rows],
        )
        self.statusBar().showMessage(f"Проект сохранен: {Path(target_path).name}", 5000)

    def _open_project(self) -> None:
        source_path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть проект",
            "",
            "JSON (*.json)",
        )
        if not source_path:
            return
        try:
            jobs, settings = load_project(source_path)
        except Exception as exc:
            QMessageBox.critical(self, "Открыть проект", f"Не удалось открыть проект:\n{exc}")
            return
        if settings:
            for key, value in settings.items():
                self.settings_manager.set(str(key), value=value)
            self.settings_manager.save()
            self._apply_current_theme()
        self.queue.replace_jobs(jobs)
        self.imported_shapes.clear()
        self.shape_summaries.clear()
        self.shape_analyses.clear()
        self._refresh_jobs()
        self.statusBar().showMessage(f"Проект открыт: {Path(source_path).name}", 5000)

    def _reload_calculation_core(self) -> None:
        source_root = QFileDialog.getExistingDirectory(
            self,
            "DEV: выбрать папку исходников",
            str(Path.cwd()),
        )
        if not source_root:
            return
        try:
            result = reload_calculation_core(source_root)
            self._rebind_reloaded_calculation_modules()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "DEV: перезагрузка ядра",
                f"Не удалось перезагрузить расчетное ядро:\n{exc}",
            )
            return

        self.shape_analyses.clear()
        self._shown_3d_path = None
        self._shown_2d_path = None
        for job in self.queue.jobs():
            if job.status == STATUS_IMPORTED:
                job.status = STATUS_PENDING
                job.warnings.append(
                    "Расчетное ядро перезагружено; обработайте файл повторно для пересчета."
                )
        self._refresh_jobs()

        skipped = f"\nПропущено: {len(result.skipped)}" if result.skipped else ""
        QMessageBox.information(
            self,
            "DEV: перезагрузка ядра",
            f"Папка: {result.source_root}\n"
            f"Перезагружено модулей: {len(result.modules)}"
            f"{skipped}\n\n"
            "Для применения новой логики обработайте нужные файлы повторно.",
        )
        self.statusBar().showMessage(
            f"Расчетное ядро перезагружено: {len(result.modules)} модулей",
            7000,
        )

    def _rebind_reloaded_calculation_modules(self) -> None:
        import cad.analyzer as analyzer_module
        import cad.edge_classifier as edge_classifier_module
        import cad.pierce_counter as pierce_counter_module
        import ui.geometry_debug_dialog as debug_dialog_module
        import ui.import_worker as import_worker_module

        globals()["analyze_shape"] = analyzer_module.analyze_shape
        import_worker_module.analyze_shape = analyzer_module.analyze_shape
        debug_dialog_module.analyze_shape = analyzer_module.analyze_shape
        debug_dialog_module.classify_cut_edges = edge_classifier_module.classify_cut_edges
        debug_dialog_module.count_edge_components = pierce_counter_module.count_edge_components
        if self.geometry_debug_dialog is not None:
            job = self._current_job()
            path = job.normalized_path if job is not None else ""
            self.geometry_debug_dialog.set_context(
                job=job,
                shape=self.imported_shapes.get(path),
                summary=self.shape_summaries.get(path),
                analysis=None,
            )

    def _import_quantity_specification(self) -> None:
        if len(self.queue) == 0:
            QMessageBox.information(
                self,
                "Импорт количества",
                "Сначала добавьте CAD-файлы в список.",
            )
            return
        source_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт количества из Excel",
            "",
            "Excel (*.xlsx *.xlsm)",
        )
        if not source_path:
            return
        try:
            specification = load_quantity_specification(source_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Импорт количества",
                f"Не удалось прочитать спецификацию:\n{exc}",
            )
            return
        if not specification:
            QMessageBox.warning(
                self,
                "Импорт количества",
                "В спецификации не найдены колонки с названием детали и количеством.",
            )
            return

        updated = 0
        skipped_explicit = 0
        unmatched: list[str] = []
        for job in self.queue.jobs():
            if has_explicit_quantity_in_filename(job.path):
                skipped_explicit += 1
                continue
            item = quantity_for_file(job.path, specification)
            if item is None:
                unmatched.append(job.name)
                continue
            job.quantity = item.quantity
            analysis = self.shape_analyses.get(job.normalized_path)
            if analysis is not None:
                self._update_job_price(job, analysis)
            updated += 1

        self._refresh_jobs()
        message = (
            f"Обновлено количеств: {updated}\n"
            f"Пропущено файлов с количеством в имени: {skipped_explicit}\n"
            f"Не найдено в спецификации: {len(unmatched)}"
        )
        if unmatched:
            preview = "\n".join(unmatched[:8])
            if len(unmatched) > 8:
                preview += f"\n... еще {len(unmatched) - 8}"
            message += f"\n\nНе найдено:\n{preview}"
        QMessageBox.information(self, "Импорт количества", message)
        self.statusBar().showMessage(
            f"Количество обновлено из спецификации: {Path(source_path).name}",
            6000,
        )

    def _start_import(
        self,
        paths: list[str],
        *,
        force_iges_solid_healing: bool = False,
        use_inventor_iges_conversion: bool = False,
    ) -> None:
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
            job.tube_size = PLACEHOLDER
            job.tube_length_mm = PLACEHOLDER
            job.wall_thickness_mm = PLACEHOLDER
            job.wall_thickness_method = PLACEHOLDER
            job.wall_thickness_confidence = PLACEHOLDER
            job.cut_length_mm = PLACEHOLDER
            job.cut_end_length_mm = PLACEHOLDER
            job.cut_feature_length_mm = PLACEHOLDER
            job.diagnostic_edge_length_mm = PLACEHOLDER
            job.pierce_count = PLACEHOLDER
            job.ignored_longitudinal_edges = PLACEHOLDER
            job.ignored_plane_radius_edges = PLACEHOLDER
            job.auxiliary_unfold_edges = PLACEHOLDER
            job.debug_edges_path = ""
            job.debug_faces_path = ""
            job.price = PLACEHOLDER
            job.price_warning = ""
            job.error_text = ""
            job.warnings.clear()
            self.imported_shapes.pop(job.normalized_path, None)
            self.shape_summaries.pop(job.normalized_path, None)
            self.shape_analyses.pop(job.normalized_path, None)

        self._set_import_controls_enabled(False)
        self.statusBar().showMessage(f"Импорт файлов: {len(import_jobs)}")
        self._refresh_jobs()

        self.import_thread = QThread(self)
        manual_thickness = (
            self.manual_thickness_input.value()
            if self.manual_thickness_checkbox.isChecked()
            else None
        )
        self.import_worker = CadImportWorker(
            [Path(job.normalized_path) for job in import_jobs],
            manual_wall_thickness_mm=manual_thickness,
            debug_edges_enabled=self.debug_edges_checkbox.isChecked(),
            force_iges_solid_healing=force_iges_solid_healing,
            use_inventor_iges_conversion=use_inventor_iges_conversion,
        )
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
        self._invalidate_preview_cache(job.normalized_path)

        job.status = STATUS_IMPORTED
        self._apply_analysis_to_job(job, geometry_analysis, fallback_profile=str(file_format))
        job.error_text = ""

        self._refresh_jobs()

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
        self._invalidate_preview_cache(job.normalized_path)
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
        self.export_dxf_button.setEnabled(enabled)
        self.export_svg_button.setEnabled(enabled)
        self.nesting_button.setEnabled(enabled)
        self.rebuild_iges_solid_button.setEnabled(enabled and self._current_job_is_iges())
        self.inventor_iges_button.setEnabled(enabled and self._current_job_is_iges())

    def _apply_analysis_to_job(
        self,
        job: FileJob,
        analysis: GeometryAnalysisResult,
        *,
        fallback_profile: str = "CAD",
    ) -> None:
        job.tube_type = getattr(analysis, "profile_hint", fallback_profile)
        job.tube_size = self._format_tube_size(analysis)
        job.tube_length_mm = self._format_analysis_length(analysis)
        job.wall_thickness_mm = self._format_wall_thickness(analysis)
        job.wall_thickness_method = str(
            getattr(analysis, "wall_thickness_method", PLACEHOLDER) or PLACEHOLDER
        )
        job.wall_thickness_confidence = str(
            getattr(analysis, "wall_thickness_confidence", PLACEHOLDER) or PLACEHOLDER
        )
        job.cut_length_mm = self._format_cut_length(analysis)
        job.cut_end_length_mm = self._format_length_field(analysis, "cut_end_length_mm")
        job.cut_feature_length_mm = self._format_length_field(analysis, "cut_feature_length_mm")
        job.diagnostic_edge_length_mm = self._format_diagnostic_edge_length(analysis)
        job.pierce_count = self._format_pierce_count(analysis)
        job.ignored_longitudinal_edges = self._format_count(
            analysis,
            "ignored_longitudinal_edge_count",
        )
        job.ignored_plane_radius_edges = self._format_count(
            analysis,
            "ignored_plane_radius_edge_count",
        )
        job.auxiliary_unfold_edges = self._format_count(
            analysis,
            "auxiliary_unfold_edge_count",
        )
        job.debug_edges_path = str(getattr(analysis, "debug_edges_path", "") or "")
        job.debug_faces_path = str(getattr(analysis, "debug_faces_path", "") or "")
        self._update_job_price(job, analysis)
        job.warnings = [self._format_analysis_summary(analysis)]
        if job.price_warning:
            job.warnings.append(job.price_warning)
        job.warnings.extend(str(warning) for warning in getattr(analysis, "warnings", ()))

    def _on_job_thickness_changed(self, path: str, thickness: float) -> None:
        job = self.queue.get(path)
        if job is None or thickness <= 0.0:
            return

        summary = self.shape_summaries.get(job.normalized_path)
        current_analysis = self.shape_analyses.get(job.normalized_path)
        shape = self.imported_shapes.get(job.normalized_path)
        try:
            if shape is not None:
                analysis = analyze_shape(
                    shape,
                    summary=summary,
                    file_format=(
                        current_analysis.file_format
                        if current_analysis is not None
                        else "CAD"
                    ),
                    manual_wall_thickness_mm=thickness,
                    source_path=job.normalized_path,
                )
            elif current_analysis is not None and current_analysis.sheet_analysis is not None:
                sheet_analysis = current_analysis.sheet_analysis
                sheet_analysis.thickness_mm = thickness
                analysis = analyze_shape(
                    None,
                    summary=summary,
                    file_format="DXF",
                    manual_wall_thickness_mm=thickness,
                    source_path=job.normalized_path,
                    sheet_analysis=sheet_analysis,
                )
            else:
                job.wall_thickness_mm = f"{thickness:.1f} мм"
                self._refresh_jobs()
                self.statusBar().showMessage(
                    f"Толщина обновлена для файла: {job.name}. Для пересчета стоимости нужна обработанная модель.",
                    6000,
                )
                return
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Толщина",
                f"Не удалось пересчитать файл с ручной толщиной:\n{exc}",
            )
            return

        self.shape_analyses[job.normalized_path] = analysis
        self._apply_analysis_to_job(job, analysis, fallback_profile=job.tube_type)
        job.status = STATUS_IMPORTED
        job.error_text = ""
        self._refresh_jobs()
        self.statusBar().showMessage(
            f"Толщина и стоимость пересчитаны для файла: {job.name}",
            4000,
        )

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

    def _format_tube_size(self, analysis: object) -> str:
        width = float(getattr(analysis, "width_mm", 0.0) or 0.0)
        height = float(getattr(analysis, "height_mm", 0.0) or 0.0)
        round_diameter = float(getattr(analysis, "round_outer_diameter_mm", 0.0) or 0.0)
        profile = str(getattr(analysis, "profile_hint", "") or "").lower()
        if width <= 0.0 or height <= 0.0:
            return PLACEHOLDER
        if round_diameter > 0.0:
            base = f"Ø{round_diameter:.1f}"
        elif "круг" in profile and "квадрат" not in profile:
            base = f"Ø{max(width, height):.1f}"
        else:
            base = f"{self._format_tube_dimension(width)}×{self._format_tube_dimension(height)}"
        return base

    def _format_tube_dimension(self, value: float) -> str:
        rounded = round(value)
        if abs(value - rounded) <= 0.25:
            return f"{rounded:.0f}"
        return f"{value:.1f}"

    def _update_job_price(self, job: FileJob, analysis: object) -> None:
        cut_length = float(getattr(analysis, "cut_length_mm", 0.0) or 0.0)
        pierce_count = int(getattr(analysis, "pierce_count", 0) or 0)
        thickness = float(getattr(analysis, "wall_thickness_mm", 0.0) or 0.0)
        quantity = max(1, int(getattr(job, "quantity", 1) or 1))
        if cut_length <= 0.0 and pierce_count <= 0:
            job.price = PLACEHOLDER
            job.price_warning = ""
            return
        result = calculate_job_price(
            self.settings_manager.as_dict(),
            contractor=job.contractor,
            material=job.material,
            thickness_mm=thickness,
            cut_length_mm=cut_length,
            pierce_count=pierce_count,
        )
        material_result = calculate_tube_material_cost(
            self.settings_manager.as_dict(),
            material=job.material,
            tube_size=job.tube_size,
            wall_thickness_mm=thickness,
            tube_length_mm=number_from_text(job.tube_length_mm)
            or float(getattr(analysis, "length_mm", 0.0) or 0.0),
            quantity=quantity,
            customer_tube=job.customer_tube,
        )
        job.price = f"{result.total * quantity + material_result.total:.2f}"
        job.currency = result.currency
        job.price_warning = _join_warnings(
            result.selection.warning,
            material_result.warning,
        )

    def _on_job_material_changed(self, path: str, material: str) -> None:
        job = self.queue.get(path)
        if job is None or job.material == material:
            return
        job.material = material
        self._recalculate_job_price(job)
        self._refresh_jobs()
        self.statusBar().showMessage(
            f"Стоимость пересчитана для файла: {job.name}",
            4000,
        )

    def _choose_material_for_bulk_processing(self, jobs: list[FileJob]) -> tuple[str, str, bool]:
        current_material = ""
        current_contractor = ""
        if jobs:
            current_material = jobs[0].material
            current_contractor = jobs[0].contractor
        dialog = MaterialSelectionDialog(
            self._material_choices(),
            self._contractor_choices(),
            current_material=current_material,
            current_contractor=current_contractor,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return "", "", True
        return (
            dialog.selected_material(),
            dialog.selected_contractor(),
            dialog.is_customer_tube(),
        )

    def _set_bulk_parameters_for_jobs(
        self,
        jobs: list[FileJob],
        *,
        material: str,
        contractor: str,
        customer_tube: bool,
    ) -> None:
        if not material:
            return
        for job in jobs:
            changed = (
                job.material != material
                or job.contractor != contractor
                or job.customer_tube != customer_tube
            )
            if not changed:
                continue
            job.material = material
            if contractor:
                job.contractor = contractor
            job.customer_tube = customer_tube
            self._recalculate_job_price(job)

    def _set_material_for_jobs(
        self,
        jobs: list[FileJob],
        material: str,
        *,
        customer_tube: bool | None = None,
    ) -> None:
        if not material:
            return
        for job in jobs:
            material_changed = job.material != material
            customer_tube_changed = (
                customer_tube is not None and job.customer_tube != customer_tube
            )
            if not material_changed and not customer_tube_changed:
                continue
            job.material = material
            if customer_tube is not None:
                job.customer_tube = customer_tube
            self._recalculate_job_price(job)

    def _recalculate_job_price(self, job: FileJob) -> None:
        analysis = self.shape_analyses.get(job.normalized_path)
        if analysis is None:
            return
        old_warning = job.price_warning
        if old_warning:
            job.warnings = [warning for warning in job.warnings if warning != old_warning]
        self._update_job_price(job, analysis)
        if job.price_warning and job.price_warning not in job.warnings:
            job.warnings.append(job.price_warning)

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
            f"ребер: {getattr(analysis, 'edge_count', 0)}; "
            f"толщина: {getattr(analysis, 'wall_thickness_mm', 0.0):.1f} мм, "
            f"метод толщины: {getattr(analysis, 'wall_thickness_method', '—')}, "
            f"confidence: {getattr(analysis, 'wall_thickness_confidence', '—')}, "
            f"ребер реза: {getattr(analysis, 'cut_edge_count', 0)}, "
            f"реальный рез: {getattr(analysis, 'cut_length_mm', 0.0):.1f} мм, "
            f"торцы: {getattr(analysis, 'cut_end_length_mm', 0.0):.1f} мм, "
            f"вырезы/пазы: {getattr(analysis, 'cut_feature_length_mm', 0.0):.1f} мм, "
            f"диагн. сумма ребер: {getattr(analysis, 'diagnostic_edge_length_mm', 0.0):.1f} мм, "
            f"врезок: {getattr(analysis, 'pierce_count', 0)}, "
            f"игнор. продольных: {getattr(analysis, 'ignored_longitudinal_edge_count', 0)}, "
            f"игнор. плоскость/радиус: {getattr(analysis, 'ignored_plane_radius_edge_count', 0)}, "
            f"вспом. линий: {getattr(analysis, 'auxiliary_unfold_edge_count', 0)}."
        )

    def _format_wall_thickness(self, analysis: object) -> str:
        thickness = float(getattr(analysis, "wall_thickness_mm", 0.0))
        if thickness <= 0.0:
            return PLACEHOLDER
        return f"{thickness:.1f} мм"

    def _format_cut_length(self, analysis: object) -> str:
        cut_length = float(getattr(analysis, "cut_length_mm", 0.0))
        if cut_length <= 0.0:
            return PLACEHOLDER
        return f"{cut_length:.1f} мм"

    def _format_length_field(self, analysis: object, field_name: str) -> str:
        length = float(getattr(analysis, field_name, 0.0))
        if length <= 0.0:
            return PLACEHOLDER
        return f"{length:.1f} мм"

    def _format_diagnostic_edge_length(self, analysis: object) -> str:
        length = float(getattr(analysis, "diagnostic_edge_length_mm", 0.0))
        if length <= 0.0:
            return PLACEHOLDER
        return f"{length:.1f} мм"

    def _format_count(self, analysis: object, field_name: str) -> str:
        count = int(getattr(analysis, field_name, 0) or 0)
        return str(count)

    def _format_pierce_count(self, analysis: object) -> str:
        pierce_count = int(getattr(analysis, "pierce_count", 0))
        if pierce_count <= 0:
            return PLACEHOLDER
        return str(pierce_count)

    def _format_price(self, analysis: object) -> str:
        cut_length = float(getattr(analysis, "cut_length_mm", 0.0))
        pierce_count = int(getattr(analysis, "pierce_count", 0))
        if cut_length <= 0.0 and pierce_count <= 0:
            return PLACEHOLDER
        settings = self.settings_manager.as_dict()
        contractor = default_contractor(settings)
        material = default_material(settings)
        result = calculate_job_price(
            settings,
            contractor=contractor.name,
            material=material.name,
            thickness_mm=float(getattr(analysis, "wall_thickness_mm", 0.0) or 0.0),
            cut_length_mm=cut_length,
            pierce_count=pierce_count,
        )
        return f"{result.total:.2f} {result.currency}"

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
        self.file_table.set_materials(self._material_choices())
        self.file_table.set_jobs(jobs)
        self.diagnostic_table.set_jobs(jobs)
        self._refresh_compact_list(jobs)
        self._refresh_purchase()
        self._refresh_summary()
        self._show_selected_job(self._current_job())

    def _material_choices(self) -> list[str]:
        settings = self.settings_manager.as_dict()
        materials = materials_from_settings(settings)
        choices = [material.name for material in materials if material.active]
        default = default_material(settings).name
        if default and default not in choices:
            choices.insert(0, default)
        return choices

    def _contractor_choices(self) -> list[str]:
        settings = self.settings_manager.as_dict()
        contractors = contractors_from_settings(settings)
        choices = [contractor.name for contractor in contractors]
        default = default_contractor(settings).name
        if default and default not in choices:
            choices.insert(0, default)
        return choices

    def _refresh_purchase(self) -> None:
        self.purchase_rows = calculate_tube_purchase(
            self.queue.jobs(),
            self.settings_manager.as_dict(),
        )
        self.stock_purchase_widget.set_rows(
            self.purchase_rows,
            purchase_settings=TubePurchaseSettings.from_settings(
                self.settings_manager.as_dict()
            ),
        )

    def _refresh_summary(self) -> None:
        jobs = self.queue.jobs()
        imported = sum(1 for job in jobs if job.status == STATUS_IMPORTED)
        failed = sum(1 for job in jobs if job.status == STATUS_ERROR)
        quantity_total = sum(max(1, int(getattr(job, "quantity", 1) or 1)) for job in jobs)
        cut_total = sum(
            number_from_text(job.cut_length_mm) * max(1, int(getattr(job, "quantity", 1) or 1))
            for job in jobs
        )
        pierce_total = sum(
            int(round(number_from_text(job.pierce_count)))
            * max(1, int(getattr(job, "quantity", 1) or 1))
            for job in jobs
        )
        total = sum(number_from_text(job.price) for job in jobs)
        currency = next((job.currency for job in jobs if job.currency), "руб.")
        self.summary_label.setText(
            f"Файлов: {len(jobs)} | Успешно: {imported} | Ошибок: {failed} | "
            f"Деталей: {quantity_total} | Рез: {cut_total:.1f} мм | "
            f"Врезки: {pierce_total} | Сумма: {total:.2f} {currency}"
        )

    def _on_job_quantity_changed(self, path: str, quantity: int) -> None:
        job = self.queue.get(path)
        if job is None:
            return
        job.quantity = max(1, int(quantity))
        analysis = self.shape_analyses.get(job.normalized_path)
        if analysis is not None:
            old_warning = job.price_warning
            if old_warning:
                job.warnings = [warning for warning in job.warnings if warning != old_warning]
            self._update_job_price(job, analysis)
            if job.price_warning and job.price_warning not in job.warnings:
                job.warnings.append(job.price_warning)
        self._refresh_jobs()

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
            self.diagnostic_table.blockSignals(True)
            self.diagnostic_table.select_path(selected[0])
            self.diagnostic_table.blockSignals(False)
        self._show_selected_job(self._current_job())

    def _sync_from_diagnostic_selection(self) -> None:
        selected = self.diagnostic_table.selected_paths()
        if selected:
            self.compact_list.blockSignals(True)
            self._select_compact_path(selected[0])
            self.compact_list.blockSignals(False)
            self.file_table.blockSignals(True)
            self.file_table.select_path(selected[0])
            self.file_table.blockSignals(False)
        self._show_selected_job(self._current_job())

    def _sync_from_compact_selection(self, row: int) -> None:
        item = self.compact_list.item(row)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self.file_table.blockSignals(True)
        self.file_table.select_path(path)
        self.file_table.blockSignals(False)
        self.diagnostic_table.blockSignals(True)
        self.diagnostic_table.select_path(path)
        self.diagnostic_table.blockSignals(False)
        self._show_selected_job(self.queue.get(path))

    def _on_tab_changed(self, _index: int) -> None:
        self._show_selected_preview(self._current_job(), force=False)

    def _invalidate_preview_cache(self, path: str) -> None:
        if self._shown_3d_path == path:
            self._shown_3d_path = None
        if self._shown_2d_path == path:
            self._shown_2d_path = None

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
        self._show_selected_preview(job, force=False)
        self.geometry_debug_button.setEnabled(shape is not None)
        self.rebuild_iges_solid_button.setEnabled(
            self.import_thread is None and self._job_is_iges(job)
        )
        self.inventor_iges_button.setEnabled(
            self.import_thread is None and self._job_is_iges(job)
        )
        if self.geometry_debug_dialog is not None:
            self.geometry_debug_dialog.set_context(
                job=job,
                shape=shape,
                summary=summary,
                analysis=analysis,
            )

        if job is None:
            values = ["—"] * 21
            warnings = "—"
        else:
            values = [
                job.name,
                job.status,
                job.tube_type,
                job.tube_length_mm,
                job.wall_thickness_mm,
                job.wall_thickness_method,
                job.wall_thickness_confidence,
                job.cut_length_mm,
                job.cut_end_length_mm,
                job.cut_feature_length_mm,
                job.diagnostic_edge_length_mm,
                job.pierce_count,
                job.ignored_longitudinal_edges,
                job.ignored_plane_radius_edges,
                job.auxiliary_unfold_edges,
                job.debug_edges_path or "—",
                job.material,
                "да" if job.customer_tube else "нет",
                job.contractor,
                job.price_warning or "точное/дефолтное правило",
                job.formatted_price,
            ]
            warnings = "\n".join(job.warnings) if job.warnings else "—"

        labels = [
            self.param_name,
            self.param_status,
            self.param_profile,
            self.param_length,
            self.param_thickness,
            self.param_thickness_method,
            self.param_thickness_confidence,
            self.param_cut,
            self.param_cut_end,
            self.param_cut_feature,
            self.param_diagnostic_cut,
            self.param_pierces,
            self.param_ignored_longitudinal,
            self.param_ignored_plane_radius,
            self.param_auxiliary_unfold,
            self.param_debug_edges,
            self.param_material,
            self.param_customer_tube,
            self.param_contractor,
            self.param_price_rule,
            self.param_price,
        ]
        for label, value in zip(labels, values, strict=True):
            label.setText(value)
        self.warning_label.setText(warnings)

    def _show_selected_preview(self, job: FileJob | None, *, force: bool = False) -> None:
        current_widget = self.tabs.currentWidget()
        if current_widget not in (self.viewer_3d, self.viewer_2d):
            return

        path = job.normalized_path if job is not None else ""
        shape = self.imported_shapes.get(path) if job is not None else None
        summary = self.shape_summaries.get(path) if job is not None else None
        analysis = self.shape_analyses.get(path) if job is not None else None
        has_sheet = getattr(analysis, "sheet_analysis", None) is not None

        if current_widget is self.viewer_3d:
            if not force and self._shown_3d_path == path:
                return
            if shape is None and not has_sheet:
                self.viewer_3d.show_job(job)
            elif shape is None:
                self.viewer_3d.show_message(f"{job.name}\nDXF-лист открыт в 2D.")
            else:
                self.viewer_3d.show_shape(shape, job.name, analysis=analysis)
            self._shown_3d_path = path
            return

        if current_widget is self.viewer_2d:
            if not force and self._shown_2d_path == path:
                return
            if shape is None and not has_sheet:
                self.viewer_2d.show_job(job)
            else:
                self.viewer_2d.show_unfolding(
                    job,
                    shape=shape,
                    summary=summary,
                    analysis=analysis,
                )
            self._shown_2d_path = path

    def _current_job_is_iges(self) -> bool:
        return self._job_is_iges(self._current_job())

    @staticmethod
    def _job_is_iges(job: FileJob | None) -> bool:
        return job is not None and job.path.suffix.casefold() in {".iges", ".igs"}

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
            manual_thickness = (
                self.manual_thickness_input.value()
                if self.manual_thickness_checkbox.isChecked()
                else None
            )
            analysis = analyze_shape(
                shape,
                summary=summary,
                manual_wall_thickness_mm=manual_thickness,
            )
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

    def _open_contractors_settings(self) -> None:
        if ContractorsDialog(self.settings_manager, self).exec():
            self._settings_changed()

    def _open_materials_settings(self) -> None:
        if MaterialsDialog(self.settings_manager, self).exec():
            self._settings_changed()

    def _open_tube_price_settings(self) -> None:
        if TubePriceDialog(self.settings_manager, self).exec():
            self._settings_changed()

    def _open_pricing_settings(self) -> None:
        if PricingDialog(self.settings_manager, self).exec():
            self._settings_changed()

    def _open_purchase_settings(self) -> None:
        if TubePurchaseSettingsDialog(self.settings_manager, self).exec():
            self._settings_changed()

    def _open_general_settings(self) -> None:
        if GeneralSettingsDialog(self.settings_manager, self).exec():
            self._settings_changed()

    def _open_offer_settings(self) -> None:
        CommercialOfferDialog(self.settings_manager, self).exec()

    def _choose_logo(self) -> None:
        LogoDialog(self.settings_manager, self).exec()

    def _settings_changed(self) -> None:
        self._apply_current_theme()
        self._apply_default_settings_to_jobs(self.queue.jobs())
        for job in self.queue.jobs():
            analysis = self.shape_analyses.get(job.normalized_path)
            if analysis is not None:
                old_warning = job.price_warning
                if old_warning:
                    job.warnings = [warning for warning in job.warnings if warning != old_warning]
                self._update_job_price(job, analysis)
                if job.price_warning and job.price_warning not in job.warnings:
                    job.warnings.append(job.price_warning)
        self._refresh_jobs()

    def _export_csv(self) -> None:
        if not self._ensure_has_jobs():
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт CSV",
            "TubeCutCalculator-calculation.csv",
            "CSV (*.csv)",
        )
        if not target_path:
            return
        export_jobs_to_csv(self.queue.jobs(), target_path)
        self.statusBar().showMessage(f"CSV сохранен: {Path(target_path).name}", 5000)

    def _export_excel(self) -> None:
        if not self._ensure_has_jobs():
            return
        jobs = self.queue.jobs()
        if ExcelPreviewDialog(jobs, self).exec() != QDialog.DialogCode.Accepted:
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт Excel",
            "TubeCutCalculator-calculation.xlsx",
            "Excel (*.xlsx)",
        )
        if not target_path:
            return
        self._refresh_purchase()
        export_excel_workbook(
            jobs,
            self.purchase_rows,
            self.settings_manager.as_dict(),
            target_path,
        )
        self.statusBar().showMessage(f"Excel сохранен: {Path(target_path).name}", 5000)

    def _export_commercial_pdf(self) -> None:
        if not self._ensure_has_jobs():
            return
        dialog = InvoiceExportDialog(self.settings_manager, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.apply_to_settings()
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF — счет на оплату",
            "TubeCutCalculator-invoice.pdf",
            "PDF (*.pdf)",
        )
        if not target_path:
            return
        self._refresh_purchase()
        export_commercial_offer_pdf(
            self.queue.jobs(),
            self.purchase_rows,
            self.settings_manager.as_dict(),
            target_path,
        )
        self.statusBar().showMessage(f"PDF счет сохранен: {Path(target_path).name}", 5000)

    def _export_technical_pdf(self) -> None:
        if not self._ensure_has_jobs():
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF — технический отчет",
            "TubeCutCalculator-technical-report.pdf",
            "PDF (*.pdf)",
        )
        if not target_path:
            return
        self._refresh_purchase()
        export_technical_report_pdf(
            self.queue.jobs(),
            self.purchase_rows,
            self.settings_manager.as_dict(),
            target_path,
        )
        self.statusBar().showMessage(f"PDF техотчет сохранен: {Path(target_path).name}", 5000)

    def _export_current_sheet_dxf(self) -> None:
        sheet_analysis = self._current_sheet_analysis()
        if sheet_analysis is None:
            QMessageBox.information(
                self,
                "Экспорт DXF",
                "Выберите импортированную DXF/листовую деталь.",
            )
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт DXF",
            "TubeCutCalculator-sheet.dxf",
            "DXF (*.dxf)",
        )
        if not target_path:
            return
        export_sheet_dxf(sheet_analysis, target_path)
        self.statusBar().showMessage(f"DXF сохранен: {Path(target_path).name}", 5000)

    def _export_current_sheet_svg(self) -> None:
        sheet_analysis = self._current_sheet_analysis()
        if sheet_analysis is None:
            QMessageBox.information(
                self,
                "Экспорт SVG",
                "Выберите импортированную DXF/листовую деталь.",
            )
            return
        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт SVG",
            "TubeCutCalculator-sheet.svg",
            "SVG (*.svg)",
        )
        if not target_path:
            return
        export_sheet_svg(sheet_analysis, target_path)
        self.statusBar().showMessage(f"SVG сохранен: {Path(target_path).name}", 5000)

    def _open_nesting(self) -> None:
        jobs: list[tuple[FileJob, object]] = []
        for job in self.queue.jobs():
            analysis = self.shape_analyses.get(job.normalized_path)
            if getattr(analysis, "sheet_analysis", None) is not None:
                jobs.append((job, analysis))
        if not jobs:
            QMessageBox.information(
                self,
                "Nesting",
                "Сначала импортируйте DXF или листовые STEP/IGES детали.",
            )
            return
        NestingDialog(self, jobs=jobs).exec()

    def _current_sheet_analysis(self) -> object | None:
        job = self._current_job()
        if job is None:
            return None
        analysis = self.shape_analyses.get(job.normalized_path)
        return getattr(analysis, "sheet_analysis", None)

    def _print_current_table(self) -> None:
        if self._ensure_has_jobs():
            print_html(self, calculation_table_html(self.queue.jobs()))

    def _print_commercial_offer(self) -> None:
        if self._ensure_has_jobs():
            self._refresh_purchase()
            print_html(
                self,
                commercial_offer_html(
                    self.queue.jobs(),
                    self.purchase_rows,
                    self.settings_manager.as_dict(),
                ),
            )

    def _print_technical_report(self) -> None:
        if self._ensure_has_jobs():
            self._refresh_purchase()
            print_html(
                self,
                technical_report_html(
                    self.queue.jobs(),
                    self.purchase_rows,
                    self.settings_manager.as_dict(),
                ),
            )

    def _preview_print(self) -> None:
        if self._ensure_has_jobs():
            print_html(self, calculation_table_html(self.queue.jobs()), preview=True)

    def _ensure_has_jobs(self) -> bool:
        if len(self.queue) == 0:
            QMessageBox.information(self, "Экспорт", "Список файлов пуст.")
            return False
        return True

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

    def _apply_current_theme(self) -> None:
        theme = str(self.settings_manager.get("ui", "theme", default="light") or "light")
        apply_theme(self, theme)


def _join_warnings(*warnings: str) -> str:
    return "\n".join(warning for warning in warnings if warning)
