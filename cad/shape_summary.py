from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ShapeSummary:
    diagonal_mm: float
    size_x_mm: float
    size_y_mm: float
    size_z_mm: float
    face_count: int
    edge_count: int


def summarize_shape(shape: object) -> ShapeSummary:
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer

    box = Bnd_Box()
    _add_shape_to_box(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    size_x = max(0.0, xmax - xmin)
    size_y = max(0.0, ymax - ymin)
    size_z = max(0.0, zmax - zmin)
    diagonal = (size_x**2 + size_y**2 + size_z**2) ** 0.5

    return ShapeSummary(
        diagonal_mm=diagonal,
        size_x_mm=size_x,
        size_y_mm=size_y,
        size_z_mm=size_z,
        face_count=_count_topology(shape, TopAbs_FACE),
        edge_count=_count_topology(shape, TopAbs_EDGE),
    )


def _count_topology(shape: object, shape_type: int) -> int:
    explorer = TopExp_Explorer(shape, shape_type)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _add_shape_to_box(shape: object, box: object) -> None:
    try:
        from OCC.Core.BRepBndLib import brepbndlib

        brepbndlib.Add(shape, box)
    except ImportError:
        from OCC.Core.BRepBndLib import brepbndlib_Add

        brepbndlib_Add(shape, box)
