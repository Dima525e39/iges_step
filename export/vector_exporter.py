from __future__ import annotations

from html import escape
from pathlib import Path

from cad.sheet_analyzer import SheetAnalysisResult, SheetContour, SheetPoint
from nesting.core import NestingLayout, transformed_contours


def export_sheet_svg(
    analysis: SheetAnalysisResult,
    target_path: str | Path,
    *,
    title: str = "Sheet part",
) -> Path:
    return _write_svg(
        target_path,
        width_mm=max(analysis.width_mm, 1.0),
        height_mm=max(analysis.height_mm, 1.0),
        contours=analysis.contours,
        title=title,
    )


def export_sheet_dxf(analysis: SheetAnalysisResult, target_path: str | Path) -> Path:
    return _write_dxf(target_path, contours=analysis.contours)


def export_nesting_svg(
    layout: NestingLayout,
    target_path: str | Path,
    *,
    title: str = "Nesting layout",
) -> Path:
    sheet_gap = max(25.0, layout.spacing_mm * 4.0)
    contours: list[SheetContour] = []
    for sheet in layout.sheets:
        offset_y = sheet.index * (layout.sheet_height_mm + sheet_gap)
        contours.extend(
            _rectangle_contour(
                0.0,
                offset_y,
                layout.sheet_width_mm,
                layout.sheet_height_mm,
                component_id=-(sheet.index + 1),
            )
        )
        for placement in sheet.placements:
            for contour in transformed_contours(placement):
                contours.append(_offset_contour(contour, dx=0.0, dy=offset_y))
    total_height = max(1.0, len(layout.sheets) * layout.sheet_height_mm + max(0, len(layout.sheets) - 1) * sheet_gap)
    return _write_svg(
        target_path,
        width_mm=max(layout.sheet_width_mm, 1.0),
        height_mm=total_height,
        contours=tuple(contours),
        title=title,
    )


def export_nesting_dxf(layout: NestingLayout, target_path: str | Path) -> Path:
    sheet_gap = max(25.0, layout.spacing_mm * 4.0)
    contours: list[SheetContour] = []
    for sheet in layout.sheets:
        offset_y = sheet.index * (layout.sheet_height_mm + sheet_gap)
        contours.extend(
            _rectangle_contour(
                0.0,
                offset_y,
                layout.sheet_width_mm,
                layout.sheet_height_mm,
                component_id=-(sheet.index + 1),
            )
        )
        for placement in sheet.placements:
            contours.extend(
                _offset_contour(contour, dx=0.0, dy=offset_y)
                for contour in transformed_contours(placement)
            )
    return _write_dxf(target_path, contours=tuple(contours))


def _write_svg(
    target_path: str | Path,
    *,
    width_mm: float,
    height_mm: float,
    contours: tuple[SheetContour, ...] | list[SheetContour],
    title: str,
) -> Path:
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.3f}mm" '
            f'height="{height_mm:.3f}mm" viewBox="0 0 {width_mm:.3f} {height_mm:.3f}">'
        ),
        f"<title>{escape(title)}</title>",
        '<g fill="none" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for contour in contours:
        color = "#94a3b8" if contour.component_id < 0 else "#dc2626"
        width = "0.35" if contour.component_id < 0 else "0.20"
        points = " ".join(f"{point.x_mm:.3f},{point.y_mm:.3f}" for point in contour.points)
        if points:
            lines.append(
                f'<polyline points="{points}" stroke="{color}" stroke-width="{width}" />'
            )
    lines.extend(["</g>", "</svg>"])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_dxf(
    target_path: str | Path,
    *,
    contours: tuple[SheetContour, ...] | list[SheetContour],
) -> Path:
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [
        "0",
        "SECTION",
        "2",
        "HEADER",
        "9",
        "$INSUNITS",
        "70",
        "4",
        "0",
        "ENDSEC",
        "0",
        "SECTION",
        "2",
        "TABLES",
        "0",
        "TABLE",
        "2",
        "LAYER",
        "70",
        "2",
        "0",
        "LAYER",
        "2",
        "CUT",
        "70",
        "0",
        "62",
        "1",
        "6",
        "CONTINUOUS",
        "0",
        "LAYER",
        "2",
        "SHEET",
        "70",
        "0",
        "62",
        "8",
        "6",
        "CONTINUOUS",
        "0",
        "ENDTAB",
        "0",
        "ENDSEC",
        "0",
        "SECTION",
        "2",
        "ENTITIES",
    ]
    for contour in contours:
        layer = "SHEET" if contour.component_id < 0 else "CUT"
        points = contour.points
        if len(points) < 2:
            continue
        for start, end in zip(points, points[1:], strict=False):
            chunks.extend(
                [
                    "0",
                    "LINE",
                    "8",
                    layer,
                    "10",
                    f"{start.x_mm:.6f}",
                    "20",
                    f"{start.y_mm:.6f}",
                    "30",
                    "0.000000",
                    "11",
                    f"{end.x_mm:.6f}",
                    "21",
                    f"{end.y_mm:.6f}",
                    "31",
                    "0.000000",
                ]
            )
    chunks.extend(["0", "ENDSEC", "0", "EOF"])
    path.write_text("\n".join(chunks) + "\n", encoding="utf-8")
    return path


def _rectangle_contour(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    component_id: int,
) -> tuple[SheetContour, ...]:
    points = (
        SheetPoint(x, y),
        SheetPoint(x + width, y),
        SheetPoint(x + width, y + height),
        SheetPoint(x, y + height),
        SheetPoint(x, y),
    )
    return (
        SheetContour(
            points=points,
            length_mm=2.0 * (width + height),
            component_id=component_id,
            is_outer=True,
        ),
    )


def _offset_contour(contour: SheetContour, *, dx: float, dy: float) -> SheetContour:
    return SheetContour(
        points=tuple(
            SheetPoint(point.x_mm + dx, point.y_mm + dy) for point in contour.points
        ),
        length_mm=contour.length_mm,
        component_id=contour.component_id,
        is_outer=contour.is_outer,
    )


def _is_closed(points: tuple[SheetPoint, ...]) -> bool:
    if len(points) < 3:
        return False
    return (
        abs(points[0].x_mm - points[-1].x_mm) <= 0.001
        and abs(points[0].y_mm - points[-1].y_mm) <= 0.001
    )
