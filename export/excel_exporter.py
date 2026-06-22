from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from core.file_job import FileJob
from purchase.tube_purchase_calculator import TubePurchaseRow


def export_excel_workbook(
    jobs: list[FileJob],
    purchase_rows: list[TubePurchaseRow],
    settings: dict[str, Any],
    target_path: str | Path,
) -> None:
    detail_rows = [
        [
            "Файл",
            "Размер / толщина",
            "Длина",
            "Длина реза",
            "Врезки",
            "Цена",
            "Материал",
            "Контрагент",
            "Статус",
            "Предупреждения",
            "Ошибка",
        ],
        *[job.to_table_row() for job in jobs],
    ]
    purchase_header = [
        "Материал",
        "Тип трубы",
        "Размер / толщина",
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
    settings_sheet = [["Раздел", "Значение"], ["Версия настроек", "v0.4.11"]]
    settings_sheet.extend(_flatten_settings(settings))

    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels())
        archive.writestr("xl/styles.xml", _styles())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet(detail_rows))
        archive.writestr("xl/worksheets/sheet2.xml", _sheet(purchase_sheet))
        archive.writestr("xl/worksheets/sheet3.xml", _sheet(settings_sheet))


def _sheet(rows: list[list[object]]) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            text = escape(str(value))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )


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
<fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellXfs>
</styleSheet>"""
