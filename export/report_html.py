from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from core.file_job import FileJob
from purchase.tube_grouping import number_from_text
from purchase.tube_purchase_calculator import TubePurchaseRow
from settings.contractors_manager import contractor_by_name
from settings.logo_manager import logo_path_from_settings


def commercial_offer_html(
    jobs: list[FileJob],
    purchase_rows: list[TubePurchaseRow],
    settings: dict[str, Any],
) -> str:
    offer = settings.get("commercial_offer", {})
    if not isinstance(offer, dict):
        offer = {}
    title = str(offer.get("document_title", "Счет на оплату")) or "Счет на оплату"
    number = str(offer.get("number", "")) or "без номера"
    offer_date = str(offer.get("date", "")) or date.today().isoformat()
    contractor = contractor_by_name(settings, str(offer.get("contractor", "")))
    total = sum(number_from_text(job.price) for job in jobs)
    vat_text, vat_amount = _vat_text(offer, total)
    logo = _logo_html(settings)
    supplier_name = str(offer.get("supplier_name", "")) or str(offer.get("seller", ""))
    supplier_recipient = str(offer.get("supplier_recipient", "")) or supplier_name
    return f"""
<html><body>
{_style()}
{logo}
{_bank_table(offer, supplier_recipient)}
<h1>{escape(title)} № {escape(number)} от {escape(_human_date(offer_date))}</h1>
<hr>
<p><span class="label">Поставщик<br>(Исполнитель):</span>
<b>{escape(_party_line(supplier_name, str(offer.get("supplier_inn", "")), str(offer.get("supplier_kpp", "")), str(offer.get("supplier_address", ""))))}</b></p>
<p><span class="label">Покупатель<br>(Заказчик):</span>
<b>{escape(_party_line(contractor.name, contractor.inn, contractor.kpp, contractor.address))}</b></p>
<p><span class="label">Основание:</span> <b>{escape(str(offer.get("basis", "Договор поставки")))}</b></p>
{_invoice_items_table(jobs, str(offer.get("unit", "шт")) or "шт")}
<table class="totals">
<tr><td>Итого:</td><td>{_money(total)}</td></tr>
<tr><td>{escape(vat_text)}:</td><td>{_money(vat_amount) if vat_amount > 0 else ""}</td></tr>
<tr><td>Всего к оплате:</td><td>{_money(total)}</td></tr>
</table>
<p>Всего наименований {len(jobs)}, на сумму {_money(total)} руб.</p>
<p><b>{escape(_amount_to_words(total))}</b></p>
{_terms_html(offer)}
<div class="signature-row">
<b>Руководитель</b><span class="line"></span>{escape(str(offer.get("contact_person", "")) or supplier_name)}
<b>Бухгалтер</b><span class="line"></span>{escape(str(offer.get("contact_person", "")) or supplier_name)}
</div>
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


def _bank_table(offer: dict[str, Any], recipient: str) -> str:
    bank = str(offer.get("supplier_bank", ""))
    bik = str(offer.get("supplier_bik", ""))
    corr = str(offer.get("supplier_corr_account", ""))
    inn = str(offer.get("supplier_inn", ""))
    kpp = str(offer.get("supplier_kpp", ""))
    account = str(offer.get("supplier_account", ""))
    return f"""
<table class="bank">
<tr><td rowspan="2" colspan="2"><b>{escape(bank)}</b><br><span>Банк получателя</span></td><td>БИК</td><td>{escape(bik)}</td></tr>
<tr><td>Сч. №</td><td>{escape(corr)}</td></tr>
<tr><td>ИНН {escape(inn)}</td><td>КПП {escape(kpp)}</td><td>Сч. №</td><td>{escape(account)}</td></tr>
<tr><td colspan="2"><b>{escape(recipient)}</b><br><span>Получатель</span></td><td></td><td></td></tr>
</table>
"""


def _party_line(name: str, inn: str, kpp: str, address: str) -> str:
    parts = [name]
    if inn:
        parts.append(f"ИНН {inn}")
    if kpp:
        parts.append(f"КПП {kpp}")
    if address:
        parts.append(address)
    return ", ".join(part for part in parts if part)


def _invoice_items_table(jobs: list[FileJob], unit: str) -> str:
    headers = ["№", "Товары (работы, услуги)", "Кол-во", "Ед.", "Цена", "Сумма"]
    rows = []
    for index, job in enumerate(jobs, start=1):
        quantity = max(1, int(getattr(job, "quantity", 1) or 1))
        total = number_from_text(job.price)
        unit_price = total / quantity if quantity > 0 else total
        description = _invoice_description(job)
        values = [
            str(index),
            description,
            str(quantity),
            unit,
            _money(unit_price),
            _money(total),
        ]
        rows.append(
            "<tr>"
            + "".join(f"<td>{escape(value)}</td>" for value in values)
            + "</tr>"
        )
    return _table(headers, rows)


def _invoice_description(job: FileJob) -> str:
    details = []
    if job.tube_size != "—":
        details.append(f"размер {job.tube_size}")
    if job.wall_thickness_mm != "—":
        details.append(f"толщина {job.wall_thickness_mm}")
    if job.cut_length_mm != "—":
        details.append(f"длина реза {job.cut_length_mm}")
    if job.pierce_count != "—":
        details.append(f"врезки {job.pierce_count}")
    suffix = f" ({'; '.join(details)})" if details else ""
    return f"Лазерная резка: {job.name}{suffix}"


def _vat_text(offer: dict[str, Any], total: float) -> tuple[str, float]:
    if str(offer.get("vat_mode", "none")) != "included":
        return "В том числе НДС", 0.0
    rate = float(offer.get("vat_rate", 20.0) or 20.0)
    if rate <= 0.0:
        return "В том числе НДС", 0.0
    vat = total * rate / (100.0 + rate)
    return f"В том числе НДС ({rate:g}%)", vat


def _terms_html(offer: dict[str, Any]) -> str:
    lines = [
        str(offer.get("validity_text", "")),
        str(offer.get("payment_terms", "")),
        str(offer.get("production_terms", "")),
        str(offer.get("note", "")),
    ]
    escaped = [escape(line) for line in lines if line.strip()]
    return "".join(f"<p>{line}</p>" for line in escaped)


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _human_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    months = (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year} г."


def _amount_to_words(value: float) -> str:
    rubles = int(value)
    kopecks = int(round((value - rubles) * 100))
    return f"{_int_to_ru_words(rubles).capitalize()} {_rub_word(rubles)} {kopecks:02d} {_kop_word(kopecks)}"


def _int_to_ru_words(value: int) -> str:
    if value == 0:
        return "ноль"
    units = [
        ("", "", ""),
        ("один", "одна", "тысяча"),
        ("два", "две", "тысяча"),
        ("три", "три", "тысяча"),
        ("четыре", "четыре", "тысяча"),
        ("пять", "пять", "тысяча"),
        ("шесть", "шесть", "тысяча"),
        ("семь", "семь", "тысяча"),
        ("восемь", "восемь", "тысяча"),
        ("девять", "девять", "тысяча"),
    ]
    teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    def chunk_words(chunk: int, female: bool) -> list[str]:
        result: list[str] = []
        result.append(hundreds[chunk // 100])
        rest = chunk % 100
        if 10 <= rest <= 19:
            result.append(teens[rest - 10])
        else:
            result.append(tens[rest // 10])
            unit = rest % 10
            if unit:
                result.append(units[unit][1 if female else 0])
        return [word for word in result if word]

    words: list[str] = []
    groups = [
        (value // 1_000_000, False, ("миллион", "миллиона", "миллионов")),
        ((value // 1000) % 1000, True, ("тысяча", "тысячи", "тысяч")),
        (value % 1000, False, None),
    ]
    for chunk, female, forms in groups:
        if not chunk:
            continue
        words.extend(chunk_words(chunk, female=female))
        if forms is not None:
            words.append(_plural(chunk, *forms))
    return " ".join(words)


def _rub_word(value: int) -> str:
    return _plural(value, "рубль", "рубля", "рублей")


def _kop_word(value: int) -> str:
    return _plural(value, "копейка", "копейки", "копеек")


def _plural(value: int, one: str, few: str, many: str) -> str:
    value = abs(value) % 100
    if 11 <= value <= 19:
        return many
    last = value % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def _details_table(jobs: list[FileJob], *, technical: bool = False) -> str:
    headers = [
        "№",
        "Файл",
        "Материал",
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
            job.material,
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
body { font-family: Arial, sans-serif; font-size: 10pt; color: #111; }
h1 { font-size: 18pt; margin: 22px 0 14px; }
h2 { font-size: 13pt; margin-top: 18px; }
hr { border: 0; border-top: 2px solid #333; margin: 12px 0; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
th { font-weight: bold; text-align: center; }
td, th { border: 1px solid #333; padding: 4px; vertical-align: top; }
.bank td { height: 22px; }
.bank span { font-size: 8pt; }
.label { display: inline-block; width: 118px; vertical-align: top; }
.totals { width: 42%; margin-left: auto; margin-top: 8px; }
.totals td { border: 0; font-weight: bold; font-size: 12pt; text-align: right; }
.signature-row { margin-top: 28px; border-top: 2px solid #333; padding-top: 16px; }
.line { display: inline-block; width: 150px; border-bottom: 1px solid #333; margin: 0 12px; }
.total { font-size: 13pt; font-weight: bold; }
</style>
"""
