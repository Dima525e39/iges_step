from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument

from core.file_job import FileJob
from export.report_html import technical_report_html
from purchase.tube_purchase_calculator import TubePurchaseRow


def export_technical_report_pdf(
    jobs: list[FileJob],
    purchase_rows: list[TubePurchaseRow],
    settings: dict[str, Any],
    target_path: str | Path,
) -> None:
    writer = QPdfWriter(str(target_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setResolution(96)
    document = QTextDocument()
    document.setHtml(technical_report_html(jobs, purchase_rows, settings))
    document.print_(writer)
