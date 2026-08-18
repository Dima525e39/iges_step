from __future__ import annotations

from html import escape
from pathlib import Path

from cad.sheet_analyzer import SheetAnalysisResult, SheetContour


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
