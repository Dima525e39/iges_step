from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class StockLengthInput:
    detail_lengths_mm: list[float]
    standard_stock_length_mm: float = 6000.0
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
    stock_count: int
    purchase_length_mm: float
    remainder_mm: float
    warning: str = ""


def calculate_stock_lengths(data: StockLengthInput) -> StockLengthResult:
    detail_lengths = [max(0.0, value) for value in data.detail_lengths_mm if value > 0.0]
    detail_count = len(detail_lengths)
    detail_length = sum(detail_lengths)
    part_gaps = max(0, detail_count - 1) * data.part_gap_mm if data.include_part_gap else 0.0
    allowances = part_gaps + max(0.0, data.end_trim_allowance_mm)
    length_with_allowance = (detail_length + allowances) * (
        1 + data.stock_allowance_percent / 100
    )
    stock_length = max(1.0, data.standard_stock_length_mm)
    if data.round_to_whole_stock:
        stock_count = max(1, math.ceil(length_with_allowance / stock_length)) if detail_count else 0
        purchase_length = stock_count * stock_length
    else:
        stock_count = math.ceil(length_with_allowance / stock_length) if detail_count else 0
        purchase_length = length_with_allowance
    remainder = max(0.0, purchase_length - detail_length)
    warning = "Расчет закупки приблизительный; оптимизация раскроя по хлыстам пока не выполняется."
    if detail_count == 0:
        warning = "Нет деталей с определенной длиной."
    return StockLengthResult(
        detail_count=detail_count,
        detail_length_mm=detail_length,
        allowances_mm=allowances,
        stock_allowance_percent=data.stock_allowance_percent,
        length_with_allowance_mm=length_with_allowance,
        standard_stock_length_mm=stock_length,
        stock_count=stock_count,
        purchase_length_mm=purchase_length,
        remainder_mm=remainder,
        warning=warning,
    )
