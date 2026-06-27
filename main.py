from __future__ import annotations

import sys
from pathlib import Path

from app_info import APP_NAME, APP_VERSION


def main() -> int:
    if "--self-test-imports" in sys.argv:
        output_path = _self_test_output_path(sys.argv)
        return _run_import_self_test(output_path)

    from PySide6.QtWidgets import QApplication
    from cad.outer_contour_patch import install_outer_contour_patch

    install_outer_contour_patch()

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    window = MainWindow()
    window.show()
    return app.exec()


def _self_test_output_path(args: list[str]) -> Path | None:
    for index, arg in enumerate(args):
        if arg == "--self-test-output" and index + 1 < len(args):
            return Path(args[index + 1])
        if arg.startswith("--self-test-output="):
            return Path(arg.split("=", 1)[1])
    return None


def _run_import_self_test(output_path: Path | None) -> int:
    lines: list[str] = []

    def record(message: str) -> None:
        lines.append(message)

    exit_code = 0
    try:
        record(f"{APP_NAME} {APP_VERSION} import self-test")
        from PySide6.QtCore import qVersion

        record(f"PySide6 Qt {qVersion()}: OK")
        from PySide6.QtPrintSupport import QPrinter

        _ = QPrinter
        record("PySide6 QtPrintSupport: OK")

        from OCC.Core.Bnd import Bnd_Box
        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
        import OCC.Core.BRepGProp as brep_gprop
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.GProp import GProp_GProps
        from OCC.Core.IGESControl import IGESControl_Reader
        from OCC.Core.Interface import Interface_Static
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.TopAbs import (
            TopAbs_EDGE,
            TopAbs_FACE,
            TopAbs_SHELL,
            TopAbs_SOLID,
            TopAbs_WIRE,
        )
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopTools import TopTools_IndexedMapOfShape
        from OCC.Core.TopoDS import TopoDS_Shape

        try:
            from OCC.Core.BRepBndLib import brepbndlib

            bbox_add = brepbndlib.Add
        except ImportError:
            from OCC.Core.BRepBndLib import brepbndlib_Add

            bbox_add = brepbndlib_Add

        _ = (
            Bnd_Box,
            bbox_add,
            brep_gprop,
            IFSelect_RetDone,
            IGESControl_Reader,
            Interface_Static,
            BRepAdaptor_Surface,
            GProp_GProps,
            STEPControl_Reader,
            TopAbs_EDGE,
            TopAbs_FACE,
            TopAbs_SHELL,
            TopAbs_SOLID,
            TopAbs_WIRE,
            TopExp_Explorer,
            TopTools_IndexedMapOfShape,
            TopoDS_Shape,
        )
        record("pythonocc-core import modules: OK")

        from cad.analyzer import analyze_shape
        from cad.dxf_reader import read_dxf_sheet
        from cad.profile_detector import detect_profile_from_dimensions
        from cad.sheet_analyzer import build_sheet_analysis_from_contours
        from cad.shape_summary import _count_topology
        from cad.unfolder import TubeUnfolder, build_unfolding_preview_from_edges
        from export.excel_exporter import export_excel_workbook
        from export.pdf_commercial_offer import export_commercial_offer_pdf
        from export.pdf_technical_report import export_technical_report_pdf
        from export.vector_exporter import export_nesting_dxf, export_sheet_svg
        from nesting.core import MaxRectsNestingEngine
        from pricing.price_selector import calculate_job_price
        from purchase.tube_purchase_calculator import calculate_tube_purchase

        _count_topology(TopoDS_Shape(), TopAbs_FACE)
        record("shape summary topology helper: OK")

        analyze_shape(
            None,
            summary=type(
                "SelfTestSummary",
                (),
                {
                    "size_x_mm": 10.0,
                    "size_y_mm": 20.0,
                    "size_z_mm": 100.0,
                    "face_count": 6,
                    "edge_count": 12,
                },
            )(),
            file_format="SELFTEST",
        )
        record("geometry analyzer helper: OK")

        from cad.edge_classifier import (
            Bounds,
            EdgeRecord,
            FaceRecord,
            _analyze_round_tube_bspline_bbox_fallback,
            estimate_wall_thickness,
        )

        split_faces = (
            FaceRecord(object(), Bounds(-51.0, 0.0, -51.0, 0.0, 1000.0, 51.0), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -51.0, 51.0, 1000.0, 51.0), False),
            FaceRecord(object(), Bounds(-48.0, 0.0, -48.0, 0.0, 1000.0, 48.0), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -48.0, 48.0, 1000.0, 48.0), False),
        )
        split_edges = (
            EdgeRecord(object(), 160.221, bounds=Bounds(-51.0, 0.0, -51.0, 0.0, 0.0, 51.0), wire_roles={"outer_wire_cut"}),
            EdgeRecord(object(), 150.796, bounds=Bounds(-48.0, 0.0, -48.0, 0.0, 0.0, 48.0), wire_roles={"inner_wire", "outer_wire_cut"}),
            EdgeRecord(object(), 160.221, bounds=Bounds(0.0, 997.0, -51.0, 51.0, 1000.0, 0.0), wire_roles={"outer_wire_cut"}),
            EdgeRecord(object(), 42.0, bounds=Bounds(36.0, 450.0, 36.0, 51.0, 455.0, 51.0), wire_roles={"outer_wire_cut"}),
        )
        split_analysis = _analyze_round_tube_bspline_bbox_fallback(
            split_faces,
            split_edges,
            axis="Y",
            length_mm=1000.0,
            global_bounds=Bounds(-51.0, 0.0, -51.0, 51.0, 1000.0, 51.0),
            has_outer_faces=False,
            tolerance=0.01,
        )
        split_thickness = estimate_wall_thickness(
            split_faces,
            (),
            axis="Y",
            length_mm=1000.0,
            global_bounds=Bounds(-51.0, 0.0, -51.0, 51.0, 1000.0, 51.0),
            tolerance=0.01,
        )
        if (
            round(split_analysis.outer_radius_mm * 2.0, 3) != 102.0
            or split_analysis.pierce_count != 3
            or round(split_thickness.thickness_mm, 3) != 3.0
        ):
            raise RuntimeError("round split-surface fallback self-test failed")

        collector_faces = (
            FaceRecord(object(), Bounds(0.0, -66.5, -66.5, 1000.0, 0.0, 66.5), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -66.5, 1000.0, 66.5, 66.5), False),
            FaceRecord(object(), Bounds(0.0, -60.5, -60.5, 1000.0, 0.0, 60.5), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -60.5, 1000.0, 60.5, 60.5), False),
        )
        collector_edges = (
            EdgeRecord(object(), 208.916, bounds=Bounds(0.0, -66.5, -66.5, 0.0, 0.0, 66.5)),
            EdgeRecord(object(), 208.916, bounds=Bounds(1000.0, 0.0, -66.5, 1000.0, 66.5, 66.5)),
            EdgeRecord(object(), 6.0, bounds=Bounds(200.0, 5.0, 60.5, 210.0, 7.0, 66.5), wire_roles={"outer_wire_cut"}),
            EdgeRecord(object(), 93.1, bounds=Bounds(200.0, 16.0, 35.0, 230.0, 56.0, 66.0), wire_roles={"inner_wire"}),
            EdgeRecord(object(), 93.1, bounds=Bounds(230.0, 16.0, 35.0, 260.0, 56.0, 66.0), wire_roles={"inner_wire"}),
            EdgeRecord(object(), 93.1, bounds=Bounds(200.0, -56.0, 35.0, 230.0, -16.0, 66.0), wire_roles={"inner_wire"}),
            EdgeRecord(object(), 93.1, bounds=Bounds(230.0, -56.0, 35.0, 260.0, -16.0, 66.0), wire_roles={"inner_wire"}),
        )
        collector_analysis = _analyze_round_tube_bspline_bbox_fallback(
            collector_faces,
            collector_edges,
            axis="X",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, -66.5, -66.5, 1000.0, 66.5, 66.5),
            has_outer_faces=True,
            tolerance=0.01,
        )
        if collector_analysis.pierce_count != 4:
            raise RuntimeError("round mixed-inner fallback self-test failed")
        record("round IGES fallback helpers: OK")

        detect_profile_from_dimensions(100.0, 20.0, 10.0)
        record("profile detector helper: OK")

        _ = (TubeUnfolder, build_unfolding_preview_from_edges)
        record("unfolding preview helper: OK")

        _ = (
            read_dxf_sheet,
            build_sheet_analysis_from_contours,
            MaxRectsNestingEngine,
            export_nesting_dxf,
            export_sheet_svg,
            export_excel_workbook,
            export_commercial_offer_pdf,
            export_technical_report_pdf,
            calculate_job_price,
            calculate_tube_purchase,
        )
        record("DXF/nesting/pricing/export/purchase helpers: OK")
    except Exception as exc:
        exit_code = 1
        record(f"FAILED: {exc.__class__.__name__}: {exc}")

    text = "\n".join(lines) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
