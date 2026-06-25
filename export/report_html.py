from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from core.file_job import FileJob
from purchase.tube_grouping import number_from_text
from purchase.tube_purchase_calculator import TubePurchaseRow
from settings.logo_manager import logo_path_from_settings


def commercial_offer_html(
    jobs: list[FileJob],
    purchase_rows: list[TubePurchaseRow],
    settings: dict[str, Any],
) -> str:
    offer = settings.get("commercial_offer", {})
    if not isinstance(offer, dict):
        offer = {}
    number = str(offer.get("number", "")) or "без номера"
    offer_date = str(offer.get("date", "")) or date.today().isoformat()
    contractor = str(offer.get("contractor", "")) or _first_contractor(settings)
    total = sum(number_from_text(job.price) for job in jobs)
    logo = _logo_html(settings)
    return f"""
<html><body>
{_style()}
{logo}
<h1>Коммерческое предложение № {escape(number)}</h1>
<p><b>Дата:</b> {escape(offer_date)}<br>
<b>Контрагент:</b> {escape(contractor)}<br>
<b>Исполнитель:</b> {escape(str(offer.get("seller", "")))}<br>
<b>Контакт:</b> {escape(str(offer.get("contact_person", "")))} {escape(str(offer.get("phone", "")))} {escape(str(offer.get("email", "")))}</p>
{_details_table(jobs)}
<h2>Необходимое количество трубы</h2>
{_purchase_table(purchase_rows, commercial=True)}
<h2>Итого</h2>
<p class="total">Общая сумма: {total:.2f} руб.</p>
<p><b>Условия оплаты:</b> {escape(str(offer.get("payment_terms", "")))}</p>
<p><b>Срок изготовления:</b> {escape(str(offer.get("production_terms", "")))}</p>
<p>{escape(str(offer.get("note", "")))}</p>
</body></html>
"""


def technical_report_html(
    jobs: list[FileJob],
    purchase_rows: list[TubePurchaseRow],
    settings: dict[str, Any],
) -> str:
    logo = _logo_html(settings)
    warnings = "<br>".join(
        escape(f"{job.name}: {'; '.join(job.warnings)}")
        for job in jobs
        if job.warnings or job.error_text
    )
    return f"""
<html><body>
{_style()}
{logo}
<h1>Технический отчет TubeCutCalculator</h1>
<p><b>Дата:</b> {date.today().isoformat()}</p>
{_details_table(jobs, technical=True)}
<h2>Закупка трубы</h2>
{_purchase_table(purchase_rows, commercial=False)}
<h2>Диагностика</h2>
<p>{warnings or "Предупреждений и ошибок нет."}</p>
</body></html>
"""


def calculation_table_html(jobs: list[FileJob]) -> str:
    return f"""
<html><body>
{_style()}
<h1>Расчет деталей TubeCutCalculator</h1>
{_details_table(jobs)}
</body></html>
"""


def _details_table(jobs: list[FileJob], *, technical: bool = False) -> str:
    headers = [
        "№",
        "Файл",
        "Размер",
        "Толщина",
        "Длина",
        "Длина реза",
        "Врезки",
        "Количество",
        "Цена",
    ]
    if technical:
        headers.extend(["Метод толщины", "Confidence", "Предупреждения", "Ошибка"])
    rows = []
    for index, job in enumerate(jobs, start=1):
        values = [
            str(index),
            job.name,
            job.tube_size,
            job.wall_thickness_mm,
            job.tube_length_mm,
            job.cut_length_mm,
            job.pierce_count,
            str(job.quantity),
            job.formatted_price,
        ]
        if technical:
            values.extend(
                [
                    job.wall_thickness_method,
                    job.wall_thickness_confidence,
                    "; ".join(job.warnings),
                    job.error_text,
                ]
            )
        rows.append("<tr>" + "".join(f"<td>{escape(value)}</td>" for value in values) + "</tr>")
    return _table(headers, rows)


def _purchase_table(rows: list[TubePurchaseRow], *, commercial: bool) -> str:
    if commercial:
        headers = [
            "Материал",
            "Труба",
            "Деталей",
            "Длина деталей",
            "Хлыст",
            "Нужно купить",
            "Остаток",
        ]
        html_rows = [
            "<tr>"
            + "".join(
                f"<td>{escape(value)}</td>"
                for value in [
                    row.material,
                    row.tube_size,
                    str(row.detail_count),
                    f"{row.detail_length_mm:.1f} мм",
                    f"{row.stock_length_mm:.1f} мм",
                    f"{row.stock_count} хлыст. / {row.purchase_length_mm:.1f} мм",
                    f"{row.remainder_mm:.1f} мм",
                ]
            )
            + "</tr>"
            for row in rows
        ]
    else:
        headers = [
            "Материал",
            "Тип",
            "Размер",
            "Деталей",
            "Длина деталей",
            "Припуски",
            "Запас",
            "С запасом",
            "Хлыст",
            "Хлыстов",
            "Закупка",
            "Остаток",
            "Предупреждения",
        ]
        html_rows = [
            "<tr>"
            + "".join(
                f"<td>{escape(value)}</td>"
                for value in [
                    row.material,
                    row.tube_type,
                    row.tube_size,
                    str(row.detail_count),
                    f"{row.detail_length_mm:.1f}",
                    f"{row.allowances_mm:.1f}",
                    f"{row.stock_allowance_percent:.1f}%",
                    f"{row.length_with_allowance_mm:.1f}",
                    f"{row.stock_length_mm:.1f}",
                    str(row.stock_count),
                    f"{row.purchase_length_mm:.1f}",
                    f"{row.remainder_mm:.1f}",
                    row.warnings,
                ]
            )
            + "</tr>"
            for row in rows
        ]
    return _table(headers, html_rows) if rows else "<p>Нет данных для закупки трубы.</p>"


def _table(headers: list[str], rows: list[str]) -> str:
    header_html = "<tr>" + "".join(f"<th>{escape(header)}</th>" for header in headers) + "</tr>"
    return f"<table>{header_html}{''.join(rows)}</table>"


def _logo_html(settings: dict[str, Any]) -> str:
    logo_path = logo_path_from_settings(settings)
    if not logo_path:
        return ""
    return f'<p><img src="{escape(logo_path)}" height="64"></p>'


def _first_contractor(settings: dict[str, Any]) -> str:
    rows = settings.get("contractors", [])
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return str(rows[0].get("name", ""))
    return ""


def _style() -> str:
    return """
<style>
body { font-family: Arial, sans-serif; font-size: 10pt; color: #111827; }
h1 { font-size: 18pt; margin-bottom: 8px; }
h2 { font-size: 13pt; margin-top: 18px; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
th { background: #e5e7eb; font-weight: bold; }
td, th { border: 1px solid #9ca3af; padding: 4px; vertical-align: top; }
.total { font-size: 13pt; font-weight: bold; }
</style>
"""
