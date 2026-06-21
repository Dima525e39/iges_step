from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PriceRule:
    contractor: str = "По умолчанию"
    material: str = "Сталь"
    thickness_mm: float = 1.5
    price_per_meter: float = 120.0
    price_per_pierce: float = 15.0
    minimum_price: float = 0.0
    setup_price: float = 0.0
    complexity_factor: float = 1.0
    active: bool = True
    is_default: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PriceRule":
        return cls(
            contractor=str(data.get("contractor", "По умолчанию")),
            material=str(data.get("material", "Сталь")),
            thickness_mm=float(data.get("thickness_mm", 1.5) or 0.0),
            price_per_meter=float(data.get("price_per_meter", 120.0) or 0.0),
            price_per_pierce=float(data.get("price_per_pierce", 15.0) or 0.0),
            minimum_price=float(data.get("minimum_price", 0.0) or 0.0),
            setup_price=float(data.get("setup_price", 0.0) or 0.0),
            complexity_factor=float(data.get("complexity_factor", 1.0) or 1.0),
            active=bool(data.get("active", True)),
            is_default=bool(data.get("is_default", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractor": self.contractor,
            "material": self.material,
            "thickness_mm": self.thickness_mm,
            "price_per_meter": self.price_per_meter,
            "price_per_pierce": self.price_per_pierce,
            "minimum_price": self.minimum_price,
            "setup_price": self.setup_price,
            "complexity_factor": self.complexity_factor,
            "active": self.active,
            "is_default": self.is_default,
        }


def pricing_rules_from_settings(settings: dict[str, Any]) -> list[PriceRule]:
    pricing = settings.get("pricing", {})
    rows = pricing.get("rules", []) if isinstance(pricing, dict) else []
    rules = [PriceRule.from_dict(row) for row in rows if isinstance(row, dict)]
    if rules:
        return rules

    return [
        PriceRule(
            contractor="По умолчанию",
            material="Сталь",
            thickness_mm=1.5,
            price_per_meter=float(pricing.get("price_per_meter", 120.0) or 120.0)
            if isinstance(pricing, dict)
            else 120.0,
            price_per_pierce=float(pricing.get("price_per_pierce", 15.0) or 15.0)
            if isinstance(pricing, dict)
            else 15.0,
            minimum_price=float(pricing.get("minimum_price", 0.0) or 0.0)
            if isinstance(pricing, dict)
            else 0.0,
            setup_price=float(pricing.get("setup_price", 0.0) or 0.0)
            if isinstance(pricing, dict)
            else 0.0,
            complexity_factor=float(pricing.get("complexity_factor", 1.0) or 1.0)
            if isinstance(pricing, dict)
            else 1.0,
            is_default=True,
        )
    ]
