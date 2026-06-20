from __future__ import annotations


class PerimeterCalculator:
    """Calculates a bounding-box profile perimeter estimate."""

    def calculate(self, profile: object) -> float:
        width = float(getattr(profile, "width_mm", 0.0))
        height = float(getattr(profile, "height_mm", 0.0))
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return 2.0 * (width + height)
