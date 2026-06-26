from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow


def install_top_menu(window: QMainWindow) -> None:
    menu_bar = window.menuBar()
    menu_bar.clear()

    file_menu = menu_bar.addMenu("Файл")
    _add_action(file_menu, "Добавить файл", window._choose_files)
    _add_action(file_menu, "Добавить папку", window._choose_folder)
    file_menu.addSeparator()
    _add_action(file_menu, "Сохранить проект", window._save_project)
    _add_action(file_menu, "Открыть проект", window._open_project)
    file_menu.addSeparator()
    _add_action(file_menu, "Очистить список", window._clear_jobs)
    _add_action(file_menu, "Выход", window.close)

    settings_menu = menu_bar.addMenu("Настройки")
    _add_action(settings_menu, "Контрагенты", window._open_contractors_settings)
    _add_action(settings_menu, "Материалы", window._open_materials_settings)
    _add_action(settings_menu, "Прайс труб", window._open_tube_price_settings)
    _add_action(settings_menu, "Цены", window._open_pricing_settings)
    _add_action(settings_menu, "Закупка трубы", window._open_purchase_settings)
    _add_action(settings_menu, "Логотип", window._choose_logo)
    _add_action(settings_menu, "Шаблон счета", window._open_offer_settings)
    settings_menu.addSeparator()
    _add_action(settings_menu, "Общие параметры расчета", window._open_general_settings)

    export_menu = menu_bar.addMenu("Печать / экспорт")
    _add_action(export_menu, "Печать текущего расчета на принтер", window._print_current_table)
    _add_action(export_menu, "Печать счета", window._print_commercial_offer)
    _add_action(export_menu, "Печать технического отчета", window._print_technical_report)
    export_menu.addSeparator()
    _add_action(export_menu, "Экспорт в Excel", window._export_excel)
    _add_action(export_menu, "Экспорт в PDF — счет на оплату", window._export_commercial_pdf)
    _add_action(export_menu, "Экспорт в PDF — технический отчет", window._export_technical_pdf)
    export_menu.addSeparator()
    _add_action(export_menu, "Nesting листовых деталей", window._open_nesting)
    _add_action(export_menu, "Экспорт текущей листовой детали в DXF", window._export_current_sheet_dxf)
    _add_action(export_menu, "Экспорт текущей листовой детали в SVG", window._export_current_sheet_svg)
    export_menu.addSeparator()
    _add_action(export_menu, "Предпросмотр перед печатью", window._preview_print)


def _add_action(menu: object, title: str, callback: object) -> QAction:
    action = QAction(title, menu)
    action.triggered.connect(callback)  # type: ignore[attr-defined]
    menu.addAction(action)  # type: ignore[attr-defined]
    return action
