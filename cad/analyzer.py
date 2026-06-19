from __future__ import annotations

from pathlib import Path


class TubeAnalyzer:
    """Geometry analysis placeholder for v0.3.0+."""

    def analyze(self, path: str | Path) -> None:
        raise NotImplementedError(
            f"Анализ геометрии для {Path(path).name} пока не реализован."
        )
