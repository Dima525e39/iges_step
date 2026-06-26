from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from settings.materials_manager import material_by_name
from settings.tube_purchase_settings import TubePurchaseSettings
from settings.tube_price_manager import select_tube_price_rule


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
    tube_size: str = "",
    wall_thickness_mm: float = 0.0,
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
    tube_price = select_tube_price_rule(
        settings,
        material=material,
        tube_size=tube_size,
        wall_thickness_mm=wall_thickness_mm,
    )
    stock_length = (
        tube_price.standard_stock_length_mm
        if tube_price is not None and tube_price.standard_stock_length_mm > 0.0
        else material_data.standard_stock_length_mm
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

    price_per_meter = (
        tube_price.tube_price_per_meter
        if tube_price is not None and tube_price.tube_price_per_meter > 0.0
        else material_data.tube_price_per_meter
    )
    price_per_stock = (
        tube_price.tube_price_per_stock
        if tube_price is not None and tube_price.tube_price_per_stock > 0.0
        else material_data.tube_price_per_stock
    )
    if price_per_meter > 0.0:
        unit = chargeable_length / 1000.0 * price_per_meter
    elif price_per_stock > 0.0 and stock_length > 0.0:
        unit = chargeable_length / stock_length * price_per_stock
    else:
        return MaterialCostResult(
            warning=(
                f"Стоимость материала не добавлена: для трубы {tube_size or material_data.name} "
                "не задана цена в прайсе труб или материале."
            )
        )

    return MaterialCostResult(
        total=unit * count,
        unit=unit,
        chargeable_length_mm=chargeable_length,
    )
