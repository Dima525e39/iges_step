from __future__ import annotations

import binascii
import math
import struct
import zipfile
import zlib
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
    *,
    isometry_images: dict[str, bytes] | None = None,
) -> None:
    detail_rows = [
        [
            "Изометрия",
            "Файл",
            "Размер",
            "Толщина",
            "Длина",
            "Длина реза",
            "Врезки",
            "Количество",
            "Цена",
        ],
        *[["", *job.to_table_row()] for job in jobs],
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
    settings_sheet = [["Раздел", "Значение"], ["Версия настроек", "v0.5.0"]]
    settings_sheet.extend(_flatten_settings(settings))

    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels())
        archive.writestr("xl/styles.xml", _styles())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet(detail_rows, with_drawing=bool(jobs)))
        if jobs:
            archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", _sheet1_rels())
            archive.writestr("xl/drawings/drawing1.xml", _drawing(jobs))
            archive.writestr("xl/drawings/_rels/drawing1.xml.rels", _drawing_rels(len(jobs)))
            for index, job in enumerate(jobs, start=1):
                image = (isometry_images or {}).get(job.normalized_path)
                if not image:
                    image = _fallback_isometry_png(job)
                archive.writestr(f"xl/media/isometry{index}.png", image)
        archive.writestr("xl/worksheets/sheet2.xml", _sheet(purchase_sheet))
        archive.writestr("xl/worksheets/sheet3.xml", _sheet(settings_sheet))


def _sheet(rows: list[list[object]], *, with_drawing: bool = False) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            text = escape(str(value))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        height = ' ht="62" customHeight="1"' if with_drawing and row_index > 1 else ""
        xml_rows.append(f'<row r="{row_index}"{height}>{"".join(cells)}</row>')
    cols = (
        '<cols><col min="1" max="1" width="18" customWidth="1"/>'
        '<col min="2" max="9" width="18" customWidth="1"/></cols>'
        if with_drawing
        else ""
    )
    drawing = '<drawing r:id="rId1"/>' if with_drawing else ""
    namespaces = (
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        if with_drawing
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"{namespaces}>'
        + cols
        + '<sheetData>'
        + "".join(xml_rows)
        + "</sheetData>"
        + drawing
        + "</worksheet>"
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
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>
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


def _sheet1_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>
</Relationships>"""


def _drawing(jobs: list[FileJob]) -> str:
    anchors = []
    for index, _job in enumerate(jobs, start=1):
        row = index
        rel_id = f"rId{index}"
        anchors.append(
            f"""
<xdr:twoCellAnchor editAs="oneCell">
<xdr:from><xdr:col>0</xdr:col><xdr:colOff>95250</xdr:colOff><xdr:row>{row}</xdr:row><xdr:rowOff>95250</xdr:rowOff></xdr:from>
<xdr:to><xdr:col>1</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{row + 1}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
<xdr:pic>
<xdr:nvPicPr><xdr:cNvPr id="{index}" name="isometry{index}.png"/><xdr:cNvPicPr/></xdr:nvPicPr>
<xdr:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
<xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>
</xdr:pic>
<xdr:clientData/>
</xdr:twoCellAnchor>"""
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        + "".join(anchors)
        + "</xdr:wsDr>"
    )


def _drawing_rels(count: int) -> str:
    relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/isometry{index}.png"/>'
        for index in range(1, count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + relationships
        + "</Relationships>"
    )


def _fallback_isometry_png(job: FileJob) -> bytes:
    width, height = 160, 84
    pixels = bytearray([255, 255, 255] * width * height)

    def set_pixel(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            index = (y * width + x) * 3
            pixels[index : index + 3] = bytes(color)

    def line(start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int]) -> None:
        x1, y1 = start
        x2, y2 = end
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        error = dx + dy
        while True:
            set_pixel(x1, y1, color)
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * error
            if e2 >= dy:
                error += dy
                x1 += sx
            if e2 <= dx:
                error += dx
                y1 += sy

    def poly(points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
        for first, second in zip(points, points[1:], strict=False):
            line(first, second, color)

    blue = (37, 99, 235)
    gray = (100, 116, 139)
    accent = (220, 38, 38)
    if job.tube_size.startswith("Ø"):
        front = _ellipse_points(54, 46, 24, 15)
        back = [(x + 54, y - 18) for x, y in front]
        poly(front + [front[0]], blue)
        poly(back + [back[0]], blue)
        for index in (0, 8, 16, 24):
            line(front[index], back[index], gray)
    else:
        front = [(34, 56), (80, 56), (80, 28), (34, 28), (34, 56)]
        back = [(88, 38), (134, 38), (134, 10), (88, 10), (88, 38)]
        poly(front, blue)
        poly(back, blue)
        for first, second in zip(front[:-1], back[:-1], strict=False):
            line(first, second, gray)
    line((20, 70), (140, 70), accent)
    return _png(width, height, bytes(pixels))


def _ellipse_points(cx: int, cy: int, rx: int, ry: int) -> list[tuple[int, int]]:
    return [
        (
            int(cx + rx * math.cos(math.tau * index / 32)),
            int(cy + ry * math.sin(math.tau * index / 32)),
        )
        for index in range(32)
    ]


def _png(width: int, height: int, rgb: bytes) -> bytes:
    raw = b"".join(
        b"\x00" + rgb[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
