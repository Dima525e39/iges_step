from __future__ import annotations

from pathlib import Path

from core.file_job import FileJob
from export.pdf_technical_report import export_technical_report_pdf
from purchase.tube_purchase_calculator import TubePurchaseRow


def export_pdf_report(
    target_path: str | Path,
    *,
    jobs: list[FileJob] | None = None,
    purchase_rows: list[TubePurchaseRow] | None = None,
    settings: dict[str, object] | None = None,
) -> None:
    export_technical_report_pdf(
        jobs or [],
        purchase_rows or [],
        settings or {},
        target_path,
    )
