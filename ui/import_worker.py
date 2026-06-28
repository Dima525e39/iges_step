from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal, Slot

from cad.analyzer import analyze_shape
from cad.dxf_reader import read_dxf_sheet
from cad.importer import CadImporter
from cad.shape_summary import summarize_shape


class CadImportWorker(QObject):
    progress = Signal(str, object, object, object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        paths: list[str | Path],
        *,
        manual_wall_thickness_mm: float | None = None,
        debug_edges_enabled: bool = False,
    ) -> None:
        super().__init__()
        self.paths = [str(path) for path in paths]
        self.manual_wall_thickness_mm = manual_wall_thickness_mm
        self.debug_edges_enabled = debug_edges_enabled

    @Slot()
    def run(self) -> None:
        importer = CadImporter()
        for path in self.paths:
            try:
                source_path = Path(path)
                if source_path.suffix.casefold() == ".dxf":
                    summary, sheet_analysis = read_dxf_sheet(
                        source_path,
                        manual_thickness_mm=self.manual_wall_thickness_mm,
                    )
                    result = SimpleNamespace(
                        path=source_path,
                        shape=None,
                        file_format="DXF",
                    )
                    analysis = analyze_shape(
                        None,
                        summary=summary,
                        file_format="DXF",
                        manual_wall_thickness_mm=self.manual_wall_thickness_mm,
                        source_path=source_path,
                        sheet_analysis=sheet_analysis,
                    )
                else:
                    result = importer.import_file(path)
                    summary = summarize_shape(result.shape)
                    debug_edges_path = (
                        source_path.with_name("debug_edges.csv")
                        if self.debug_edges_enabled
                        else None
                    )
                    analysis = analyze_shape(
                        result.shape,
                        summary=summary,
                        file_format=result.file_format,
                        manual_wall_thickness_mm=self.manual_wall_thickness_mm,
                        debug_edges_path=debug_edges_path,
                        source_path=source_path,
                        import_warnings=result.warnings,
                    )
            except Exception as exc:
                message = str(exc).strip() or exc.__class__.__name__
                self.failed.emit(path, message)
                continue
            self.progress.emit(path, result, summary, analysis)
        self.finished.emit()
