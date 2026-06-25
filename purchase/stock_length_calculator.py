from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class StockLengthInput:
    detail_lengths_mm: list[float]
    standard_stock_length_mm: float = 6000.0
    chuck_remainder_mm: float = 300.0
    stock_allowance_percent: float = 3.0
    end_trim_allowance_mm: float = 0.0
    include_part_gap: bool = True
    part_gap_mm: float = 5.0
    round_to_whole_stock: bool = True


@dataclass(slots=True)
class StockLengthResult:
    detail_count: int
    detail_length_mm: float
    allowances_mm: float
    stock_allowance_percent: float
    length_with_allowance_mm: float
    standard_stock_length_mm: float
    useful_stock_length_mm: float
    stock_count: int
    purchase_length_mm: float
    remainder_mm: float
    warning: str = ""


def calculate_stock_lengths(data: StockLengthInput) -> StockLengthResult:
    detail_lengths = [max(0.0, value) for value in data.detail_lengths_mm if value > 0.0]
    detail_count = len(detail_lengths)
    detail_length = sum(detail_lengths)
    stock_length = max(1.0, data.standard_stock_length_mm)
    chuck_remainder = max(0.0, min(data.chuck_remainder_mm, stock_length - 1.0))
    useful_stock_length = max(1.0, stock_length - chuck_remainder)
    per_detail_factor = 1 + data.stock_allowance_percent / 100
    gap = max(0.0, data.part_gap_mm) if data.include_part_gap else 0.0
    end_trim = max(0.0, data.end_trim_allowance_mm)

    packed_lengths = [
        length * per_detail_factor + gap
        for length in detail_lengths
    ]
    if packed_lengths:
        packed_lengths[-1] = max(0.0, packed_lengths[-1] - gap)
    packed_lengths.extend([end_trim] if end_trim > 0.0 else [])

    bins, too_long = _pack_first_fit_decreasing(packed_lengths, useful_stock_length)
    allowances = sum(packed_lengths) - detail_length
    length_with_allowance = sum(packed_lengths)
    if data.round_to_whole_stock:
        stock_count = len(bins)
        purchase_length = stock_count * stock_length
    else:
        stock_count = math.ceil(length_with_allowance / useful_stock_length) if detail_count else 0
        purchase_length = length_with_allowance
    useful_remainder = sum(max(0.0, useful_stock_length - used) for used in bins)
    chuck_total = stock_count * chuck_remainder if data.round_to_whole_stock else 0.0
    remainder = max(0.0, useful_remainder + chuck_total)
    warning = (
        f"Раскладка по деталям: {stock_count} хлыст.; "
        f"полезная длина хлыста {useful_stock_length:.1f} мм."
    )
    if too_long:
        warning += f" Есть детали длиннее полезной длины хлыста: {len(too_long)}."
    if detail_count == 0:
        warning = "Нет деталей с определенной длиной."
    return StockLengthResult(
        detail_count=detail_count,
        detail_length_mm=detail_length,
        allowances_mm=allowances,
        stock_allowance_percent=data.stock_allowance_percent,
        length_with_allowance_mm=length_with_allowance,
        standard_stock_length_mm=stock_length,
        useful_stock_length_mm=useful_stock_length,
        stock_count=stock_count,
        purchase_length_mm=purchase_length,
        remainder_mm=remainder,
        warning=warning,
    )


def _pack_first_fit_decreasing(lengths: list[float], capacity: float) -> tuple[list[float], list[float]]:
    bins: list[float] = []
    too_long: list[float] = []
    for length in sorted((value for value in lengths if value > 0.0), reverse=True):
        if length > capacity:
            too_long.append(length)
            bins.append(length)
            continue
        for index, used in enumerate(bins):
            if used <= capacity and used + length <= capacity:
                bins[index] = used + length
                break
        else:
            bins.append(length)
    return bins, too_long
