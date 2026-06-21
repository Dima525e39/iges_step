from __future__ import annotations

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import QWidget


def print_html(parent: QWidget, html: str, *, preview: bool = False) -> None:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    document = QTextDocument()
    document.setHtml(html)

    if preview:
        dialog = QPrintPreviewDialog(printer, parent)
        dialog.paintRequested.connect(document.print_)
        dialog.exec()
        return

    dialog = QPrintDialog(printer, parent)
    if dialog.exec() == QPrintDialog.DialogCode.Accepted:
        document.print_(printer)
