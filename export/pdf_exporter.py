from __future__ import annotations

from pathlib import Path


def export_pdf_report(target_path: str | Path) -> None:
    raise NotImplementedError(
        f"PDF-экспорт ({Path(target_path).name}) будет реализован в v0.6.0."
    )
