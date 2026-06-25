from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from settings.materials_manager import material_by_name
from settings.tube_purchase_settings import TubePurchaseSettings


@dataclass(slots=True)
class MaterialCostResult:
    total: float = 0.0
    unit: float = 0.0
    chargeable_length_mm: float = 0.0
    warning: str = ""


def calculate_tube_material_cost(
    settings: dict[str, Any],
    *,
    material: str,
    tube_length_mm: float,
    quantity: int,
    customer_tube: bool,
) -> MaterialCostResult:
    if customer_tube:
        return MaterialCostResult()

    length = max(0.0, tube_length_mm)
    count = max(1, int(quantity or 1))
    if length <= 0.0:
        return MaterialCostResult(
            warning="Стоимость материала не добавлена: не определена длина трубы."
        )

    purchase = TubePurchaseSettings.from_settings(settings)
    material_data = material_by_name(settings, material)
    stock_length = (
        material_data.standard_stock_length_mm
        if material_data.standard_stock_length_mm > 0.0
        else purchase.standard_stock_length_mm
    )
    useful_length = max(1.0, stock_length - max(0.0, purchase.chuck_remainder_mm))
    chuck_factor = stock_length / useful_length if purchase.round_to_whole_stock else 1.0

    chargeable_length = length * (1 + purchase.stock_allowance_percent / 100.0)
    if purchase.include_part_gap:
        chargeable_length += purchase.part_gap_mm
    if purchase.end_trim_allowance_mm > 0.0:
        chargeable_length += purchase.end_trim_allowance_mm / count
    chargeable_length *= chuck_factor

    if material_data.tube_price_per_meter > 0.0:
        unit = chargeable_length / 1000.0 * material_data.tube_price_per_meter
    elif material_data.tube_price_per_stock > 0.0 and stock_length > 0.0:
        unit = chargeable_length / stock_length * material_data.tube_price_per_stock
    else:
        return MaterialCostResult(
            warning=f"Стоимость материала не добавлена: для материала {material_data.name} не задана цена трубы."
        )

    return MaterialCostResult(
        total=unit * count,
        unit=unit,
        chargeable_length_mm=chargeable_length,
    )
