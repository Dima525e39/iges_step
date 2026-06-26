from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TubePriceRule:
    material: str = "Сталь"
    tube_size: str = ""
    wall_thickness_mm: float = 0.0
    standard_stock_length_mm: float = 6000.0
    tube_price_per_meter: float = 0.0
    tube_price_per_stock: float = 0.0
    active: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TubePriceRule":
        return cls(
            material=str(data.get("material", "Сталь")),
            tube_size=str(data.get("tube_size", "")),
            wall_thickness_mm=float(data.get("wall_thickness_mm", 0.0) or 0.0),
            standard_stock_length_mm=float(
                data.get("standard_stock_length_mm", 6000.0) or 0.0
            ),
            tube_price_per_meter=float(data.get("tube_price_per_meter", 0.0) or 0.0),
            tube_price_per_stock=float(data.get("tube_price_per_stock", 0.0) or 0.0),
            active=bool(data.get("active", True)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "material": self.material,
            "tube_size": self.tube_size,
            "wall_thickness_mm": self.wall_thickness_mm,
            "standard_stock_length_mm": self.standard_stock_length_mm,
            "tube_price_per_meter": self.tube_price_per_meter,
            "tube_price_per_stock": self.tube_price_per_stock,
            "active": self.active,
        }


def tube_price_rules_from_settings(settings: dict[str, Any]) -> list[TubePriceRule]:
    rows = settings.get("tube_prices", [])
    return [TubePriceRule.from_dict(row) for row in rows if isinstance(row, dict)]


def select_tube_price_rule(
    settings: dict[str, Any],
    *,
    material: str,
    tube_size: str,
    wall_thickness_mm: float,
) -> TubePriceRule | None:
    rules = [
        rule
        for rule in tube_price_rules_from_settings(settings)
        if rule.active
        and rule.material == material
        and _sizes_match(rule.tube_size, tube_size, wall_thickness_mm)
    ]
    if not rules:
        return None

    exact = [
        rule for rule in rules if abs(rule.wall_thickness_mm - wall_thickness_mm) <= 1e-6
    ]
    if exact:
        return exact[0]

    tolerance = float(settings.get("pricing", {}).get("thickness_tolerance_mm", 0.25) or 0.25)
    nearby = [
        rule for rule in rules if abs(rule.wall_thickness_mm - wall_thickness_mm) <= tolerance
    ]
    if nearby:
        return min(nearby, key=lambda rule: abs(rule.wall_thickness_mm - wall_thickness_mm))
    return None


def _normalize_size(value: str) -> str:
    normalized = (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("x", "×")
        .replace("*", "×")
        .replace("ø", "Ø")
    )
    return re.sub(r"-?\d+(?:[.,]\d+)?", _normalize_number, normalized)


def _sizes_match(rule_size: str, tube_size: str, wall_thickness_mm: float) -> bool:
    rule_normalized = _normalize_size(rule_size)
    tube_normalized = _normalize_size(tube_size)
    if rule_normalized == tube_normalized:
        return True
    return _normalize_size(_without_trailing_thickness(rule_size, wall_thickness_mm)) == (
        _normalize_size(_without_trailing_thickness(tube_size, wall_thickness_mm))
    )


def _without_trailing_thickness(value: str, wall_thickness_mm: float) -> str:
    if wall_thickness_mm <= 0.0:
        return value
    parts = str(value).replace("x", "×").replace("*", "×").split("×")
    if len(parts) < 3:
        return value
    last_number = _last_number(parts[-1])
    if last_number is None:
        return value
    if abs(last_number - wall_thickness_mm) > 1e-6:
        return value
    return "×".join(parts[:-1])


def _last_number(value: str) -> float | None:
    matches = re.findall(r"-?\d+(?:[.,]\d+)?", value)
    if not matches:
        return None
    return float(matches[-1].replace(",", "."))


def _normalize_number(match: re.Match[str]) -> str:
    number = float(match.group(0).replace(",", "."))
    return f"{number:.6f}".rstrip("0").rstrip(".")
