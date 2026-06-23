from __future__ import annotations

import csv
from pathlib import Path

from cad.edge_classifier import EdgeClassificationResult, FaceRecord


def write_debug_faces_csv(
    classification: EdgeClassificationResult,
    target_path: str | Path,
    *,
    length_axis: str,
) -> Path:
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "face_index",
                "surface_type",
                "radius_mm",
                "is_outer_longitudinal",
                "length_axis",
                "bbox_xmin",
                "bbox_ymin",
                "bbox_zmin",
                "bbox_xmax",
                "bbox_ymax",
                "bbox_zmax",
                "size_x",
                "size_y",
                "size_z",
                "reason",
            ]
        )
        for index, face in enumerate(classification.face_records, start=1):
            surface_type, radius = _surface_info(face)
            writer.writerow(
                [
                    index,
                    surface_type,
                    f"{radius:.6f}" if radius is not None else "",
                    "yes" if face.is_outer_longitudinal else "no",
                    length_axis,
                    f"{face.bounds.xmin:.6f}",
                    f"{face.bounds.ymin:.6f}",
                    f"{face.bounds.zmin:.6f}",
                    f"{face.bounds.xmax:.6f}",
                    f"{face.bounds.ymax:.6f}",
                    f"{face.bounds.zmax:.6f}",
                    f"{face.bounds.sizes[0]:.6f}",
                    f"{face.bounds.sizes[1]:.6f}",
                    f"{face.bounds.sizes[2]:.6f}",
                    _face_reason(face, surface_type),
                ]
            )
    return path


def _surface_info(face: FaceRecord) -> tuple[str, float | None]:
    attr_radius = getattr(face.face, "radius_mm", None)
    if attr_radius is None:
        attr_radius = getattr(face.face, "radius", None)
    if attr_radius is not None:
        try:
            return ("cylinder", float(attr_radius))
        except (TypeError, ValueError):
            pass

    try:
        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
        from OCC.Core.GeomAbs import (
            GeomAbs_BSplineSurface,
            GeomAbs_Cylinder,
            GeomAbs_Plane,
        )

        surface = BRepAdaptor_Surface(face.face)
        surface_type = surface.GetType()
        if surface_type == GeomAbs_Cylinder:
            return ("cylinder", float(surface.Cylinder().Radius()))
        if surface_type == GeomAbs_Plane:
            return ("plane", None)
        if surface_type == GeomAbs_BSplineSurface:
            return ("bspline", None)
        return (f"surface_type_{surface_type}", None)
    except Exception:
        return ("unknown", None)


def _face_reason(face: FaceRecord, surface_type: str) -> str:
    if face.is_outer_longitudinal:
        return "accepted as outer longitudinal face"
    if surface_type != "cylinder":
        return "not a detected cylinder"
    return "cylinder was not classified as outer longitudinal face"
