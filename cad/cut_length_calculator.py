from __future__ import annotations

from dataclasses import dataclass

from cad.edge_classifier import EdgeClassificationResult, classify_cut_edges
from cad.shape_summary import ShapeSummary


@dataclass(slots=True)
class CutLengthEstimate:
    cut_length_mm: float
    diagnostic_edge_length_mm: float
    cut_edge_count: int
    outer_face_count: int
    wall_thickness_mm: float = 0.0
    thickness_face_count: int = 0
    ignored_longitudinal_edge_count: int = 0
    ignored_profile_edge_count: int = 0
    auxiliary_unfold_edge_count: int = 0
    uncertain_edge_count: int = 0
    warnings: tuple[str, ...] = ()


class CutLengthCalculator:
    """Estimates laser cut length from likely outer-surface cut edges."""

    def calculate(self, contours: object) -> float:
        if isinstance(contours, EdgeClassificationResult):
            return contours.cut_length_mm
        raise TypeError("Ожидался EdgeClassificationResult.")

    def estimate(
        self,
        shape: object | None,
        *,
        summary: ShapeSummary,
        length_axis: str,
    ) -> CutLengthEstimate:
        classification = classify_cut_edges(
            shape,
            summary=summary,
            length_axis=length_axis,
        )
        return CutLengthEstimate(
            cut_length_mm=classification.cut_length_mm,
            diagnostic_edge_length_mm=classification.diagnostic_edge_length_mm,
            cut_edge_count=classification.cut_edge_count,
            outer_face_count=classification.outer_face_count,
            wall_thickness_mm=classification.wall_thickness_mm,
            thickness_face_count=classification.thickness_face_count,
            ignored_longitudinal_edge_count=classification.ignored_longitudinal_edge_count,
            ignored_profile_edge_count=classification.ignored_profile_edge_count,
            auxiliary_unfold_edge_count=classification.auxiliary_unfold_edge_count,
            uncertain_edge_count=classification.uncertain_edge_count,
            warnings=classification.warnings,
        )
