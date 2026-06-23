from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PLACEHOLDER = "—"
STATUS_PENDING = "Ожидает"
STATUS_DONE = "Обработан"
STATUS_IMPORTED = "Импортирован"
STATUS_IMPORTING = "Импорт..."
STATUS_ERROR = "Ошибка импорта"


@dataclass(slots=True)
class FileJob:
    path: Path
    status: str = STATUS_PENDING
    tube_type: str = PLACEHOLDER
    tube_size: str = PLACEHOLDER
    tube_length_mm: str = PLACEHOLDER
    wall_thickness_mm: str = PLACEHOLDER
    wall_thickness_method: str = PLACEHOLDER
    wall_thickness_confidence: str = PLACEHOLDER
    cut_length_mm: str = PLACEHOLDER
    cut_end_length_mm: str = PLACEHOLDER
    cut_feature_length_mm: str = PLACEHOLDER
    diagnostic_edge_length_mm: str = PLACEHOLDER
    pierce_count: str = PLACEHOLDER
    ignored_longitudinal_edges: str = PLACEHOLDER
    ignored_plane_radius_edges: str = PLACEHOLDER
    auxiliary_unfold_edges: str = PLACEHOLDER
    debug_edges_path: str = ""
    debug_faces_path: str = ""
    material: str = "Сталь"
    contractor: str = "По умолчанию"
    quantity: int = 1
    currency: str = "руб."
    price: str = PLACEHOLDER
    price_warning: str = ""
    error_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def normalized_path(self) -> str:
        return str(self.path)

    def to_table_row(self) -> list[str]:
        return [
            self.name,
            self.tube_size,
            self.tube_length_mm,
            self.cut_length_mm,
            self.pierce_count,
            str(self.quantity),
            self.formatted_price,
            self.material,
            self.contractor,
            self.status,
            self.error_text,
            "; ".join(self.warnings),
        ]

    def to_diagnostic_row(self) -> list[str]:
        return [
            self.name,
            self.normalized_path,
            self.status,
            self.tube_type,
            self.tube_size,
            self.tube_length_mm,
            self.wall_thickness_mm,
            self.wall_thickness_method,
            self.wall_thickness_confidence,
            self.cut_length_mm,
            self.cut_end_length_mm,
            self.cut_feature_length_mm,
            self.diagnostic_edge_length_mm,
            self.pierce_count,
            self.ignored_longitudinal_edges,
            self.ignored_plane_radius_edges,
            self.auxiliary_unfold_edges,
            str(self.quantity),
            self.formatted_price,
            self.debug_edges_path,
            self.debug_faces_path,
            self.error_text,
        ]

    @property
    def formatted_price(self) -> str:
        if self.price == PLACEHOLDER:
            return PLACEHOLDER
        return f"{self.price} {self.currency}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.normalized_path,
            "status": self.status,
            "tube_type": self.tube_type,
            "tube_size": self.tube_size,
            "tube_length_mm": self.tube_length_mm,
            "wall_thickness_mm": self.wall_thickness_mm,
            "wall_thickness_method": self.wall_thickness_method,
            "wall_thickness_confidence": self.wall_thickness_confidence,
            "cut_length_mm": self.cut_length_mm,
            "cut_end_length_mm": self.cut_end_length_mm,
            "cut_feature_length_mm": self.cut_feature_length_mm,
            "diagnostic_edge_length_mm": self.diagnostic_edge_length_mm,
            "pierce_count": self.pierce_count,
            "ignored_longitudinal_edges": self.ignored_longitudinal_edges,
            "ignored_plane_radius_edges": self.ignored_plane_radius_edges,
            "auxiliary_unfold_edges": self.auxiliary_unfold_edges,
            "debug_edges_path": self.debug_edges_path,
            "debug_faces_path": self.debug_faces_path,
            "material": self.material,
            "contractor": self.contractor,
            "quantity": self.quantity,
            "currency": self.currency,
            "price": self.price,
            "price_warning": self.price_warning,
            "error_text": self.error_text,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileJob":
        return cls(
            path=Path(str(data["path"])),
            status=str(data.get("status", STATUS_PENDING)),
            tube_type=str(data.get("tube_type", PLACEHOLDER)),
            tube_size=str(data.get("tube_size", PLACEHOLDER)),
            tube_length_mm=str(data.get("tube_length_mm", PLACEHOLDER)),
            wall_thickness_mm=str(data.get("wall_thickness_mm", PLACEHOLDER)),
            wall_thickness_method=str(data.get("wall_thickness_method", PLACEHOLDER)),
            wall_thickness_confidence=str(
                data.get("wall_thickness_confidence", PLACEHOLDER)
            ),
            cut_length_mm=str(data.get("cut_length_mm", PLACEHOLDER)),
            cut_end_length_mm=str(data.get("cut_end_length_mm", PLACEHOLDER)),
            cut_feature_length_mm=str(data.get("cut_feature_length_mm", PLACEHOLDER)),
            diagnostic_edge_length_mm=str(
                data.get("diagnostic_edge_length_mm", PLACEHOLDER)
            ),
            pierce_count=str(data.get("pierce_count", PLACEHOLDER)),
            ignored_longitudinal_edges=str(
                data.get("ignored_longitudinal_edges", PLACEHOLDER)
            ),
            ignored_plane_radius_edges=str(
                data.get("ignored_plane_radius_edges", PLACEHOLDER)
            ),
            auxiliary_unfold_edges=str(data.get("auxiliary_unfold_edges", PLACEHOLDER)),
            debug_edges_path=str(data.get("debug_edges_path", "")),
            debug_faces_path=str(data.get("debug_faces_path", "")),
            material=str(data.get("material", "Сталь")),
            contractor=str(data.get("contractor", "По умолчанию")),
            quantity=max(1, int(data.get("quantity", 1) or 1)),
            currency=str(data.get("currency", "руб.")),
            price=str(data.get("price", PLACEHOLDER)),
            price_warning=str(data.get("price_warning", "")),
            error_text=str(data.get("error_text", "")),
            warnings=[str(item) for item in data.get("warnings", [])],
        )
