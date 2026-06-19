from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PricingInput:
    cut_length_mm: float = 0.0
    pierce_count: int = 0
    price_per_meter: float = 120.0
    price_per_pierce: float = 15.0
    setup_price: float = 0.0
    minimum_price: float = 0.0
    complexity_factor: float = 1.0
    markup_percent: float = 0.0


def calculate_price(data: PricingInput) -> float:
    base = (
        data.cut_length_mm / 1000.0 * data.price_per_meter
        + data.pierce_count * data.price_per_pierce
        + data.setup_price
    )
    total = base * data.complexity_factor * (1 + data.markup_percent / 100)
    return max(total, data.minimum_price)
