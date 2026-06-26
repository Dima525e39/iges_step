from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.file_job import FileJob
from purchase.stock_length_calculator import StockLengthInput, calculate_stock_lengths
from purchase.tube_grouping import group_jobs_by_tube, number_from_text
from settings.materials_manager import material_by_name
from settings.tube_purchase_settings import TubePurchaseSettings
from settings.tube_price_manager import select_tube_price_rule


@dataclass(slots=True)
class TubePurchaseRow:
    material: str
    tube_type: str
    tube_size: str
    wall_thickness_mm: float
    detail_count: int
    detail_length_mm: float
    allowances_mm: float
    stock_allowance_percent: float
    length_with_allowance_mm: float
    stock_length_mm: float
    stock_count: int
    purchase_length_mm: float
    remainder_mm: float
    purchase_cost: float
    warnings: str = ""

    def to_table_row(self, *, show_purchase_cost: bool = True) -> list[str]:
        row = [
            self.material,
            self.tube_type,
            self.tube_size,
            _format_thickness(self.wall_thickness_mm),
            str(self.detail_count),
            f"{self.detail_length_mm:.1f}",
            f"{self.allowances_mm:.1f}",
            f"{self.stock_allowance_percent:.1f}",
            f"{self.length_with_allowance_mm:.1f}",
            f"{self.stock_length_mm:.1f}",
            str(self.stock_count),
            f"{self.purchase_length_mm:.1f}",
            f"{self.remainder_mm:.1f}",
        ]
        if show_purchase_cost:
            row.append(f"{self.purchase_cost:.2f}" if self.purchase_cost > 0.0 else "—")
        row.append(self.warnings)
        return row


def calculate_tube_purchase(
    jobs: list[FileJob],
    settings: dict[str, Any],
) -> list[TubePurchaseRow]:
    purchase_settings = TubePurchaseSettings.from_settings(settings)
    rows: list[TubePurchaseRow] = []
    for group in group_jobs_by_tube(jobs):
        material = material_by_name(settings, group.material)
        tube_price = select_tube_price_rule(
            settings,
            material=group.material,
            tube_size=group.tube_size,
            wall_thickness_mm=group.wall_thickness_mm,
        )
        stock_length = (
            tube_price.standard_stock_length_mm
            if tube_price is not None and tube_price.standard_stock_length_mm > 0.0
            else material.standard_stock_length_mm
            if material.standard_stock_length_mm > 0.0
            else purchase_settings.standard_stock_length_mm
        )
        lengths = [
            number_from_text(job.tube_length_mm)
            for job in group.jobs
            for _ in range(max(1, int(getattr(job, "quantity", 1) or 1)))
        ]
        result = calculate_stock_lengths(
            StockLengthInput(
                detail_lengths_mm=lengths,
                standard_stock_length_mm=stock_length,
                chuck_remainder_mm=purchase_settings.chuck_remainder_mm,
                stock_allowance_percent=purchase_settings.stock_allowance_percent,
                end_trim_allowance_mm=purchase_settings.end_trim_allowance_mm,
                include_part_gap=purchase_settings.include_part_gap,
                part_gap_mm=purchase_settings.part_gap_mm,
                round_to_whole_stock=purchase_settings.round_to_whole_stock,
            )
        )
        cost = 0.0
        price_per_stock = (
            tube_price.tube_price_per_stock
            if tube_price is not None and tube_price.tube_price_per_stock > 0.0
            else material.tube_price_per_stock
        )
        price_per_meter = (
            tube_price.tube_price_per_meter
            if tube_price is not None and tube_price.tube_price_per_meter > 0.0
            else material.tube_price_per_meter
        )
        if price_per_stock > 0.0:
            cost = result.stock_count * price_per_stock
        elif price_per_meter > 0.0:
            cost = result.purchase_length_mm / 1000.0 * price_per_meter
        rows.append(
            TubePurchaseRow(
                material=group.material,
                tube_type=group.tube_type,
                tube_size=group.tube_size,
                wall_thickness_mm=group.wall_thickness_mm,
                detail_count=result.detail_count,
                detail_length_mm=result.detail_length_mm,
                allowances_mm=result.allowances_mm,
                stock_allowance_percent=result.stock_allowance_percent,
                length_with_allowance_mm=result.length_with_allowance_mm,
                stock_length_mm=result.standard_stock_length_mm,
                stock_count=result.stock_count,
                purchase_length_mm=result.purchase_length_mm,
                remainder_mm=result.remainder_mm,
                purchase_cost=cost,
                warnings=result.warning,
            )
        )
    return rows


def _format_thickness(value: float) -> str:
    return f"{value:.1f}" if value > 0.0 else "—"
