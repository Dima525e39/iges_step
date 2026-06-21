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
    tube_length_mm: str = PLACEHOLDER
    wall_thickness_mm: str = PLACEHOLDER
    cut_length_mm: str = PLACEHOLDER
    diagnostic_edge_length_mm: str = PLACEHOLDER
    pierce_count: str = PLACEHOLDER
    ignored_longitudinal_edges: str = PLACEHOLDER
    auxiliary_unfold_edges: str = PLACEHOLDER
    price: str = PLACEHOLDER
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
            self.normalized_path,
            self.status,
            self.tube_type,
            self.tube_length_mm,
            self.wall_thickness_mm,
            self.cut_length_mm,
            self.diagnostic_edge_length_mm,
            self.pierce_count,
            self.ignored_longitudinal_edges,
            self.auxiliary_unfold_edges,
            self.price,
            self.error_text,
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.normalized_path,
            "status": self.status,
            "tube_type": self.tube_type,
            "tube_length_mm": self.tube_length_mm,
            "wall_thickness_mm": self.wall_thickness_mm,
            "cut_length_mm": self.cut_length_mm,
            "diagnostic_edge_length_mm": self.diagnostic_edge_length_mm,
            "pierce_count": self.pierce_count,
            "ignored_longitudinal_edges": self.ignored_longitudinal_edges,
            "auxiliary_unfold_edges": self.auxiliary_unfold_edges,
            "price": self.price,
            "error_text": self.error_text,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileJob":
        return cls(
            path=Path(str(data["path"])),
            status=str(data.get("status", STATUS_PENDING)),
            tube_type=str(data.get("tube_type", PLACEHOLDER)),
            tube_length_mm=str(data.get("tube_length_mm", PLACEHOLDER)),
            wall_thickness_mm=str(data.get("wall_thickness_mm", PLACEHOLDER)),
            cut_length_mm=str(data.get("cut_length_mm", PLACEHOLDER)),
            diagnostic_edge_length_mm=str(
                data.get("diagnostic_edge_length_mm", PLACEHOLDER)
            ),
            pierce_count=str(data.get("pierce_count", PLACEHOLDER)),
            ignored_longitudinal_edges=str(
                data.get("ignored_longitudinal_edges", PLACEHOLDER)
            ),
            auxiliary_unfold_edges=str(data.get("auxiliary_unfold_edges", PLACEHOLDER)),
            price=str(data.get("price", PLACEHOLDER)),
            error_text=str(data.get("error_text", "")),
            warnings=[str(item) for item in data.get("warnings", [])],
        )
