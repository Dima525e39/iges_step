from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget


LIGHT_THEME = """
QMainWindow, QWidget {
    background: #f6f7f9;
    color: #111827;
}
#DropRoot {
    background: #f6f7f9;
    border: 2px solid transparent;
}
#DropRoot[dropActive="true"] {
    border: 2px solid #2563eb;
    background: #eff6ff;
}
#HeaderLabel {
    font-size: 18px;
    font-weight: 700;
    color: #111827;
}
#SectionLabel {
    font-weight: 600;
    color: #374151;
}
#SummaryLabel {
    font-size: 15px;
    font-weight: 600;
    color: #111827;
}
#FileDropArea {
    border: 2px dashed #9ca3af;
    border-radius: 6px;
    background: #ffffff;
    color: #4b5563;
}
#FileDropArea[dropActive="true"],
#FileListWidget[dropActive="true"] {
    border: 2px solid #2563eb;
    background: #eff6ff;
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
QPushButton#PrimaryButton {
    background: #2563eb;
    border: 1px solid #1d4ed8;
    border-radius: 5px;
    color: #ffffff;
    font-weight: 600;
}
QTableWidget, QListWidget, QTabWidget::pane, QGraphicsView, QTextEdit, QLineEdit,
QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #d1d5db;
}
QHeaderView::section {
    background: #e5e7eb;
    color: #111827;
    padding: 4px;
    border: 1px solid #d1d5db;
}
"""


DARK_THEME = """
QMainWindow, QWidget {
    background: #181a1f;
    color: #e5e7eb;
}
#DropRoot {
    background: #181a1f;
    border: 2px solid transparent;
}
#DropRoot[dropActive="true"] {
    border: 2px solid #60a5fa;
    background: #1f2937;
}
#HeaderLabel {
    font-size: 18px;
    font-weight: 700;
    color: #f9fafb;
}
#SectionLabel, #SummaryLabel {
    font-weight: 600;
    color: #f3f4f6;
}
#FileDropArea {
    border: 2px dashed #6b7280;
    border-radius: 6px;
    background: #22262d;
    color: #d1d5db;
}
#FileDropArea[dropActive="true"],
#FileListWidget[dropActive="true"] {
    border: 2px solid #60a5fa;
    background: #243449;
}
QGroupBox {
    border: 1px solid #3f4652;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    background: #22262d;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #f3f4f6;
    font-weight: 600;
}
QPushButton {
    min-height: 30px;
    padding: 4px 10px;
    background: #2f3540;
    border: 1px solid #4b5563;
    color: #f9fafb;
}
QPushButton#PrimaryButton {
    background: #2563eb;
    border: 1px solid #60a5fa;
    border-radius: 5px;
    color: #ffffff;
    font-weight: 600;
}
QTableWidget, QListWidget, QTabWidget::pane, QGraphicsView, QTextEdit, QLineEdit,
QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {
    background: #22262d;
    border: 1px solid #3f4652;
    color: #e5e7eb;
}
QHeaderView::section {
    background: #2f3540;
    color: #f9fafb;
    padding: 4px;
    border: 1px solid #3f4652;
}
"""


def apply_theme(widget: QWidget, theme: str) -> None:
    stylesheet = DARK_THEME if theme == "dark" else LIGHT_THEME
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(stylesheet)
    else:
        widget.setStyleSheet(stylesheet)
