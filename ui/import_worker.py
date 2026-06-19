from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from cad.importer import CadImporter
from cad.shape_summary import summarize_shape


class CadImportWorker(QObject):
    progress = Signal(str, object, object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, paths: list[str | Path]) -> None:
        super().__init__()
        self.paths = [str(path) for path in paths]

    @Slot()
    def run(self) -> None:
        importer = CadImporter()
        for path in self.paths:
            try:
                result = importer.import_file(path)
                summary = summarize_shape(result.shape)
            except Exception as exc:
                message = str(exc).strip() or exc.__class__.__name__
                self.failed.emit(path, message)
                continue
            self.progress.emit(path, result, summary)
        self.finished.emit()
