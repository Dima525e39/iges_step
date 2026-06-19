from __future__ import annotations

from pathlib import Path


class CadImporter:
    """STEP/IGES import placeholder for v0.2.0."""

    def import_file(self, path: str | Path) -> None:
        raise NotImplementedError(
            f"CAD-импорт для {Path(path).name} будет реализован в v0.2.0."
        )
