from __future__ import annotations

import binascii
import math
import struct
import zlib


Point3D = tuple[float, float, float]
Point2D = tuple[float, float]


def render_shape_isometry_png(shape: object, *, width: int = 220, height: int = 140) -> bytes:
    polylines = _shape_edge_polylines(shape)
    if not polylines:
        raise ValueError("Не удалось получить ребра модели для изометрии.")

    projected = [
        [_project_isometric(point) for point in polyline]
        for polyline in polylines
        if len(polyline) >= 2
    ]
    points = [point for polyline in projected for point in polyline]
    if not points:
        raise ValueError("Не удалось спроецировать модель для изометрии.")

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    span_x = max(1e-6, max_x - min_x)
    span_y = max(1e-6, max_y - min_y)
    margin = 12.0
    scale = min((width - margin * 2.0) / span_x, (height - margin * 2.0) / span_y)

    def to_canvas(point: Point2D) -> tuple[int, int]:
        x = margin + (point[0] - min_x) * scale
        y = height - margin - (point[1] - min_y) * scale
        return int(round(x)), int(round(y))

    pixels = bytearray([255, 255, 255] * width * height)
    for polyline in projected:
        canvas_points = [to_canvas(point) for point in polyline]
        for first, second in zip(canvas_points, canvas_points[1:], strict=False):
            _draw_line(pixels, width, height, first, second, (31, 41, 55), thickness=2)
    return _png(width, height, bytes(pixels))


def _shape_edge_polylines(shape: object) -> list[list[Point3D]]:
    try:
        from OCC.Core.TopAbs import TopAbs_EDGE
        from OCC.Core.TopExp import TopExp_Explorer
    except Exception as exc:
        raise ValueError(f"OCC недоступен для изометрии: {exc}") from exc

    polylines: list[list[Point3D]] = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = explorer.Current()
        points = _sample_edge(edge)
        if len(points) >= 2:
            polylines.append(points)
        explorer.Next()
    return polylines


def _sample_edge(edge: object) -> list[Point3D]:
    try:
        from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

        curve = BRepAdaptor_Curve(edge)
        first = float(curve.FirstParameter())
        last = float(curve.LastParameter())
        if not math.isfinite(first) or not math.isfinite(last) or abs(last - first) < 1e-9:
            return _edge_endpoint_points(edge)

        steps = max(8, min(80, int(_safe_edge_length(edge) / 4.0) + 8))
        points: list[Point3D] = []
        for index in range(steps + 1):
            parameter = first + (last - first) * (index / steps)
            point = curve.Value(parameter)
            points.append((float(point.X()), float(point.Y()), float(point.Z())))
        return points
    except Exception:
        return _edge_endpoint_points(edge)


def _edge_endpoint_points(edge: object) -> list[Point3D]:
    try:
        from cad.edge_classifier import _edge_vertices, _vertex_point

        first_vertex, last_vertex = _edge_vertices(edge)
        first = _vertex_point(first_vertex)
        last = _vertex_point(last_vertex)
        if first is None or last is None:
            return []
        return [first, last]
    except Exception:
        return []


def _safe_edge_length(edge: object) -> float:
    try:
        from OCC.Core.GProp import GProp_GProps
        import OCC.Core.BRepGProp as brep_gprop

        props = GProp_GProps()
        brepgprop = getattr(brep_gprop, "brepgprop", None)
        if brepgprop is not None:
            method = getattr(brepgprop, "LinearProperties", None) or getattr(
                brepgprop,
                "LinearProperties_s",
                None,
            )
            if method is not None:
                method(edge, props)
                return max(0.0, float(props.Mass()))
        method = getattr(brep_gprop, "brepgprop_LinearProperties", None)
        if method is not None:
            method(edge, props)
            return max(0.0, float(props.Mass()))
    except Exception:
        pass
    return 0.0


def _project_isometric(point: Point3D) -> Point2D:
    x, y, z = point
    cos30 = math.cos(math.radians(30.0))
    sin30 = math.sin(math.radians(30.0))
    return ((x - y) * cos30, (x + y) * sin30 - z)


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    *,
    thickness: int = 1,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    error = dx + dy
    while True:
        _set_pixel_block(pixels, width, height, x1, y1, color, thickness=thickness)
        if x1 == x2 and y1 == y2:
            break
        e2 = 2 * error
        if e2 >= dy:
            error += dy
            x1 += sx
        if e2 <= dx:
            error += dx
            y1 += sy


def _set_pixel_block(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    *,
    thickness: int,
) -> None:
    radius = max(0, thickness - 1)
    for px in range(x - radius, x + radius + 1):
        for py in range(y - radius, y + radius + 1):
            if 0 <= px < width and 0 <= py < height:
                index = (py * width + px) * 3
                pixels[index : index + 3] = bytes(color)


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
