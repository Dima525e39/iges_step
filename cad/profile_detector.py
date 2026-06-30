from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProfileEstimate:
    profile_type: str
    width_mm: float
    height_mm: float
    confidence: str


class ProfileDetector:
    """Detects a first-pass profile type from bounding-box proportions."""

    def detect(self, shape: object) -> ProfileEstimate:
        width = float(getattr(shape, "width_mm", 0.0))
        height = float(getattr(shape, "height_mm", 0.0))
        length = float(getattr(shape, "length_mm", 0.0))
        return detect_profile_from_dimensions(length, width, height)


def detect_profile_from_dimensions(
    length_mm: float,
    width_mm: float,
    height_mm: float,
) -> ProfileEstimate:
    max_cross = max(width_mm, height_mm)
    min_cross = min(width_mm, height_mm)
    if length_mm <= 0.0 or max_cross <= 0.0:
        return ProfileEstimate("Не определено", width_mm, height_mm, "низкая")

    slender_ratio = length_mm / max_cross
    cross_ratio = abs(width_mm - height_mm) / max_cross
    if slender_ratio < 2.0:
        return ProfileEstimate("Объемная деталь", width_mm, height_mm, "низкая")
    if cross_ratio <= 0.05:
        return ProfileEstimate("Квадратная профильная труба", width_mm, height_mm, "средняя")
    return ProfileEstimate("Прямоугольная профильная труба", width_mm, height_mm, "средняя")
