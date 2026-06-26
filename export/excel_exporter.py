from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from core.file_job import FileJob
from purchase.tube_grouping import number_from_text
from purchase.tube_purchase_calculator import TubePurchaseRow


def export_excel_workbook(
    jobs: list[FileJob],
    purchase_rows: list[TubePurchaseRow],
    settings: dict[str, Any],
    target_path: str | Path,
) -> None:
    detail_rows = calculation_detail_rows(jobs, include_totals=True)
    purchase_header = [
        "Материал",
        "Тип трубы",
        "Размер",
        "Толщина, мм",
        "Количество деталей",
        "Длина деталей, мм",
        "Припуски, мм",
        "Запас, %",
        "Длина с запасом, мм",
        "Длина хлыста, мм",
        "Количество хлыстов",
        "Общая длина закупки, мм",
        "Остаток, мм",
        "Стоимость закупки",
        "Предупреждения",
    ]
    purchase_sheet = [purchase_header, *[row.to_table_row() for row in purchase_rows]]
    settings_sheet = [["Раздел", "Значение"], ["Версия настроек", "v0.5.0"]]
    settings_sheet.extend(_flatten_settings(settings))

    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels())
        archive.writestr("xl/styles.xml", _styles())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet(detail_rows, total_row=len(detail_rows)))
        archive.writestr("xl/worksheets/sheet2.xml", _sheet(purchase_sheet))
        archive.writestr("xl/worksheets/sheet3.xml", _sheet(settings_sheet))


def calculation_detail_rows(jobs: list[FileJob], *, include_totals: bool) -> list[list[str]]:
    rows = [
        [
            "Файл",
            "Материал",
            "Размер",
            "Толщина",
            "Длина",
            "Длина реза",
            "Врезки",
            "Количество",
            "Цена",
        ],
        *[job.to_table_row() for job in jobs],
    ]
    if include_totals:
        rows.append(calculation_totals_row(jobs))
    return rows


def calculation_totals_row(jobs: list[FileJob]) -> list[str]:
    total_cut_length = 0.0
    total_pierces = 0
    total_quantity = 0
    total_price = 0.0
    currency = next((job.currency for job in jobs if job.currency), "руб.")

    for job in jobs:
        quantity = max(1, int(getattr(job, "quantity", 1) or 1))
        total_quantity += quantity
        total_cut_length += number_from_text(job.cut_length_mm) * quantity
        total_pierces += int(round(number_from_text(job.pierce_count))) * quantity
        total_price += number_from_text(job.price)

    return [
        "Итого",
        "",
        "",
        "",
        "",
        f"{total_cut_length:.1f} мм",
        str(total_pierces),
        str(total_quantity),
        f"{total_price:.2f} {currency}",
    ]


def _sheet(rows: list[list[object]], *, total_row: int | None = None) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        style = ' s="1"' if row_index == 1 else ""
        if total_row is not None and row_index == total_row:
            style = ' s="2"'
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            text = escape(str(value))
            cells.append(f'<c r="{ref}"{style} t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + _columns_for_width(max((len(row) for row in rows), default=1))
        + '<sheetData>'
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )


def _columns_for_width(count: int) -> str:
    widths = [32, 18, 18, 14, 18, 18, 12, 12, 18]
    cols = []
    for index in range(1, count + 1):
        width = widths[index - 1] if index <= len(widths) else 18
        cols.append(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>')
    return "<cols>" + "".join(cols) + "</cols>"


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _flatten_settings(settings: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, value in settings.items():
        if isinstance(value, (dict, list)):
            rows.append([key, str(value)])
        else:
            rows.append([key, str(value)])
    return rows


def _content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""


def _root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Расчет деталей" sheetId="1" r:id="rId1"/>
<sheet name="Закупка трубы" sheetId="2" r:id="rId2"/>
<sheet name="Настройки" sheetId="3" r:id="rId3"/>
</sheets>
</workbook>"""


def _workbook_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE5E7EB"/></patternFill></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" applyFont="1" applyFill="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" applyFont="1"/></cellXfs>
</styleSheet>"""
