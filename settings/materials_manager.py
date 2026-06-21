from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Material:
    id: str
    name: str
    active: bool = True
    comment: str = ""
    standard_stock_length_mm: float = 6000.0
    tube_price_per_meter: float = 0.0
    tube_price_per_stock: float = 0.0
    is_default: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Material":
        return cls(
            id=str(data.get("id", "")) or _slug(str(data.get("name", "steel"))),
            name=str(data.get("name", "Сталь")),
            active=bool(data.get("active", True)),
            comment=str(data.get("comment", "")),
            standard_stock_length_mm=float(
                data.get("standard_stock_length_mm", 6000.0) or 0.0
            ),
            tube_price_per_meter=float(data.get("tube_price_per_meter", 0.0) or 0.0),
            tube_price_per_stock=float(data.get("tube_price_per_stock", 0.0) or 0.0),
            is_default=bool(data.get("is_default", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "active": self.active,
            "comment": self.comment,
            "standard_stock_length_mm": self.standard_stock_length_mm,
            "tube_price_per_meter": self.tube_price_per_meter,
            "tube_price_per_stock": self.tube_price_per_stock,
            "is_default": self.is_default,
        }


def materials_from_settings(settings: dict[str, Any]) -> list[Material]:
    rows = settings.get("materials", [])
    materials = [Material.from_dict(row) for row in rows if isinstance(row, dict)]
    if not materials:
        materials = [Material(id="steel", name="Сталь", is_default=True)]
    if not any(item.is_default for item in materials):
        materials[0].is_default = True
    return materials


def default_material(settings: dict[str, Any]) -> Material:
    materials = materials_from_settings(settings)
    return next((item for item in materials if item.is_default), materials[0])


def material_by_name(settings: dict[str, Any], name: str) -> Material:
    materials = materials_from_settings(settings)
    return next((item for item in materials if item.name == name), default_material(settings))


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return slug or "material"
