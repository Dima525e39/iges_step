from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pricing.calculator import PricingInput, calculate_price
from settings.contractors_manager import contractor_by_name
from settings.pricing_manager import PriceRule, pricing_rules_from_settings


@dataclass(slots=True)
class PricingSelection:
    rule: PriceRule
    warning: str = ""
    source: str = "точное правило"


@dataclass(slots=True)
class PricingResult:
    total: float
    base_without_markup: float
    selection: PricingSelection
    currency: str = "руб."
    contractor_markup_percent: float = 0.0
    global_markup_percent: float = 0.0


def select_price_rule(
    settings: dict[str, Any],
    *,
    contractor: str,
    material: str,
    thickness_mm: float,
) -> PricingSelection:
    rules = [rule for rule in pricing_rules_from_settings(settings) if rule.active]
    tolerance = float(settings.get("pricing", {}).get("thickness_tolerance_mm", 0.25) or 0.25)

    exact = [
        rule
        for rule in rules
        if rule.contractor == contractor
        and rule.material == material
        and abs(rule.thickness_mm - thickness_mm) <= 1e-6
    ]
    if exact:
        return PricingSelection(rule=exact[0])

    nearby = [
        rule
        for rule in rules
        if rule.contractor == contractor
        and rule.material == material
        and abs(rule.thickness_mm - thickness_mm) <= tolerance
    ]
    if nearby:
        rule = min(nearby, key=lambda item: abs(item.thickness_mm - thickness_mm))
        return PricingSelection(
            rule=rule,
            source="ближайшая толщина",
            warning=(
                f"Для толщины {thickness_mm:.2f} мм использована ближайшая цена "
                f"{rule.thickness_mm:.2f} мм."
            ),
        )

    default_rules = [rule for rule in rules if rule.is_default]
    if not default_rules and rules:
        default_rules = [rules[0]]
    if default_rules:
        rule = default_rules[0]
    else:
        pricing = settings.get("pricing", {})
        rule = PriceRule(
            contractor="По умолчанию",
            material="Сталь",
            thickness_mm=thickness_mm,
            price_per_meter=float(pricing.get("price_per_meter", 120.0) or 120.0),
            price_per_pierce=float(pricing.get("price_per_pierce", 15.0) or 15.0),
            minimum_price=float(pricing.get("minimum_price", 0.0) or 0.0),
            setup_price=float(pricing.get("setup_price", 0.0) or 0.0),
            complexity_factor=float(pricing.get("complexity_factor", 1.0) or 1.0),
            is_default=True,
        )

    return PricingSelection(
        rule=rule,
        source="цена по умолчанию",
        warning=(
            "Для выбранного контрагента не найдена цена для материала/толщины. "
            "Использована цена по умолчанию."
        ),
    )


def calculate_job_price(
    settings: dict[str, Any],
    *,
    contractor: str,
    material: str,
    thickness_mm: float,
    cut_length_mm: float,
    pierce_count: int,
) -> PricingResult:
    selection = select_price_rule(
        settings,
        contractor=contractor,
        material=material,
        thickness_mm=thickness_mm,
    )
    contractor_data = contractor_by_name(settings, contractor)
    global_markup = float(settings.get("pricing", {}).get("markup_percent", 0.0) or 0.0)
    rule = selection.rule
    base = (
        cut_length_mm / 1000.0 * rule.price_per_meter
        + pierce_count * rule.price_per_pierce
        + rule.setup_price
    )
    total = calculate_price(
        PricingInput(
            cut_length_mm=cut_length_mm,
            pierce_count=pierce_count,
            price_per_meter=rule.price_per_meter,
            price_per_pierce=rule.price_per_pierce,
            setup_price=rule.setup_price,
            minimum_price=rule.minimum_price,
            complexity_factor=rule.complexity_factor,
            markup_percent=global_markup,
            contractor_markup_percent=contractor_data.markup_percent,
        )
    )
    return PricingResult(
        total=total,
        base_without_markup=base,
        selection=selection,
        currency=contractor_data.currency,
        contractor_markup_percent=contractor_data.markup_percent,
        global_markup_percent=global_markup,
    )
