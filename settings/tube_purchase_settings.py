from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TubePurchaseSettings:
    standard_stock_length_mm: float = 6000.0
    chuck_remainder_mm: float = 300.0
    stock_allowance_percent: float = 3.0
    end_trim_allowance_mm: float = 0.0
    useful_remainder_min_mm: float = 300.0
    include_part_gap: bool = True
    part_gap_mm: float = 5.0
    round_to_whole_stock: bool = True
    show_in_commercial_offer: bool = True
    show_in_technical_report: bool = True
    show_purchase_cost: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "TubePurchaseSettings":
        data = settings.get("purchase", {})
        if not isinstance(data, dict):
            data = {}
        return cls(
            standard_stock_length_mm=float(
                data.get("standard_stock_length_mm", 6000.0) or 6000.0
            ),
            chuck_remainder_mm=float(data.get("chuck_remainder_mm", 300.0) or 0.0),
            stock_allowance_percent=float(data.get("stock_allowance_percent", 3.0) or 0.0),
            end_trim_allowance_mm=float(data.get("end_trim_allowance_mm", 0.0) or 0.0),
            useful_remainder_min_mm=float(
                data.get("useful_remainder_min_mm", 300.0) or 0.0
            ),
            include_part_gap=bool(data.get("include_part_gap", True)),
            part_gap_mm=float(data.get("part_gap_mm", 5.0) or 0.0),
            round_to_whole_stock=bool(data.get("round_to_whole_stock", True)),
            show_in_commercial_offer=bool(data.get("show_in_commercial_offer", True)),
            show_in_technical_report=bool(data.get("show_in_technical_report", True)),
            show_purchase_cost=bool(data.get("show_purchase_cost", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard_stock_length_mm": self.standard_stock_length_mm,
            "chuck_remainder_mm": self.chuck_remainder_mm,
            "stock_allowance_percent": self.stock_allowance_percent,
            "end_trim_allowance_mm": self.end_trim_allowance_mm,
            "useful_remainder_min_mm": self.useful_remainder_min_mm,
            "include_part_gap": self.include_part_gap,
            "part_gap_mm": self.part_gap_mm,
            "round_to_whole_stock": self.round_to_whole_stock,
            "show_in_commercial_offer": self.show_in_commercial_offer,
            "show_in_technical_report": self.show_in_technical_report,
            "show_purchase_cost": self.show_purchase_cost,
        }
