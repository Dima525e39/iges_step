from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cad.dxf_reader import read_dxf_sheet
from cad.sheet_analyzer import SheetContour, SheetPoint, build_sheet_analysis_from_contours
from export.vector_exporter import export_nesting_dxf, export_sheet_svg
from nesting.core import MaxRectsNestingEngine, NestingPart, TrueShapeNestingEngine


class SheetDxfAndNestingTests(unittest.TestCase):
    def test_reads_dxf_sheet_contours_as_cut_length_and_pierces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "part.dxf"
            path.write_text(
                "\n".join(
                    [
                        "0",
                        "SECTION",
                        "2",
                        "ENTITIES",
                        "0",
                        "LWPOLYLINE",
                        "8",
                        "CUT",
                        "90",
                        "4",
                        "70",
                        "1",
                        "10",
                        "0",
                        "20",
                        "0",
                        "10",
                        "100",
                        "20",
                        "0",
                        "10",
                        "100",
                        "20",
                        "50",
                        "10",
                        "0",
                        "20",
                        "50",
                        "0",
                        "CIRCLE",
                        "8",
                        "CUT",
                        "10",
                        "50",
                        "20",
                        "25",
                        "40",
                        "10",
                        "0",
                        "ENDSEC",
                        "0",
                        "EOF",
                    ]
                ),
                encoding="utf-8",
            )

            summary, analysis = read_dxf_sheet(path)

        self.assertEqual(summary.size_x_mm, 100.0)
        self.assertEqual(summary.size_y_mm, 50.0)
        self.assertEqual(analysis.pierce_count, 2)
        self.assertGreater(analysis.cut_length_mm, 360.0)
        self.assertEqual(len(analysis.contours), 2)

    def test_dxf_open_curves_are_merged_into_one_pierce(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "spline_outer.dxf"
            path.write_text(
                "\n".join(
                    [
                        "0",
                        "SECTION",
                        "2",
                        "ENTITIES",
                        "0",
                        "LINE",
                        "8",
                        "CUT",
                        "10",
                        "0",
                        "20",
                        "0",
                        "11",
                        "100",
                        "21",
                        "0",
                        "0",
                        "SPLINE",
                        "8",
                        "CUT",
                        "70",
                        "0",
                        "10",
                        "100",
                        "20",
                        "0",
                        "10",
                        "110",
                        "20",
                        "25",
                        "10",
                        "100",
                        "20",
                        "50",
                        "0",
                        "LINE",
                        "8",
                        "CUT",
                        "10",
                        "100",
                        "20",
                        "50",
                        "11",
                        "0",
                        "21",
                        "50",
                        "0",
                        "LINE",
                        "8",
                        "CUT",
                        "10",
                        "0",
                        "20",
                        "50",
                        "11",
                        "0",
                        "21",
                        "0",
                        "0",
                        "CIRCLE",
                        "8",
                        "CUT",
                        "10",
                        "35",
                        "20",
                        "25",
                        "40",
                        "5",
                        "0",
                        "ENDSEC",
                        "0",
                        "EOF",
                    ]
                ),
                encoding="utf-8",
            )

            _, analysis = read_dxf_sheet(path)

        self.assertEqual(analysis.pierce_count, 2)
        self.assertEqual(len(analysis.contours), 2)
        outer = next(contour for contour in analysis.contours if contour.is_outer)
        self.assertGreater(len(outer.points), 8)

    def test_maxrects_nesting_uses_rotation_and_multiple_parts(self) -> None:
        analysis = build_sheet_analysis_from_contours(
            (
                SheetContour(
                    points=(
                        SheetPoint(0.0, 0.0),
                        SheetPoint(80.0, 0.0),
                        SheetPoint(80.0, 40.0),
                        SheetPoint(0.0, 40.0),
                        SheetPoint(0.0, 0.0),
                    ),
                    length_mm=240.0,
                    component_id=1,
                ),
            ),
            width_mm=80.0,
            height_mm=40.0,
            thickness_mm=2.0,
        )
        part = NestingPart.from_sheet_analysis(name="plate", analysis=analysis, quantity=3)

        layout = MaxRectsNestingEngine().nest(
            (part,),
            sheet_width_mm=100.0,
            sheet_height_mm=100.0,
            spacing_mm=2.0,
            allow_rotation=True,
        )

        self.assertEqual(layout.sheet_count, 2)
        self.assertEqual(len(layout.placements), 3)

    def test_nesting_uses_arbitrary_rotation_step(self) -> None:
        analysis = build_sheet_analysis_from_contours(
            (
                SheetContour(
                    points=(
                        SheetPoint(0.0, 0.0),
                        SheetPoint(120.0, 0.0),
                        SheetPoint(120.0, 20.0),
                        SheetPoint(0.0, 20.0),
                        SheetPoint(0.0, 0.0),
                    ),
                    length_mm=280.0,
                    component_id=1,
                ),
            ),
            width_mm=120.0,
            height_mm=20.0,
            thickness_mm=2.0,
        )

        layout = MaxRectsNestingEngine().nest(
            (NestingPart.from_sheet_analysis(name="long", analysis=analysis),),
            sheet_width_mm=100.0,
            sheet_height_mm=100.0,
            spacing_mm=0.0,
            allow_rotation=True,
            rotation_step_degrees=45.0,
        )

        self.assertEqual(layout.sheet_count, 1)
        self.assertAlmostEqual(layout.placements[0].rotation_deg, 45.0)
        self.assertLessEqual(layout.placements[0].width_mm, 100.0)
        self.assertLessEqual(layout.placements[0].height_mm, 100.0)

    def test_true_shape_nesting_interlocks_l_shaped_parts(self) -> None:
        analysis = build_sheet_analysis_from_contours(
            (
                SheetContour(
                    points=(
                        SheetPoint(0.0, 0.0),
                        SheetPoint(60.0, 0.0),
                        SheetPoint(60.0, 20.0),
                        SheetPoint(20.0, 20.0),
                        SheetPoint(20.0, 60.0),
                        SheetPoint(0.0, 60.0),
                        SheetPoint(0.0, 0.0),
                    ),
                    length_mm=240.0,
                    component_id=1,
                ),
            ),
            width_mm=60.0,
            height_mm=60.0,
            thickness_mm=2.0,
        )

        layout = TrueShapeNestingEngine().nest(
            (NestingPart.from_sheet_analysis(name="l-part", analysis=analysis, quantity=2),),
            sheet_width_mm=80.2,
            sheet_height_mm=80.2,
            spacing_mm=0.1,
            allow_rotation=True,
            rotation_step_degrees=90.0,
        )

        self.assertEqual(layout.sheet_count, 1)
        self.assertEqual(len(layout.placements), 2)
        self.assertTrue(any(abs(item.rotation_deg - 180.0) <= 0.001 for item in layout.placements))

    def test_exports_sheet_svg_and_nesting_dxf(self) -> None:
        analysis = build_sheet_analysis_from_contours(
            (
                SheetContour(
                    points=(
                        SheetPoint(0.0, 0.0),
                        SheetPoint(10.0, 0.0),
                        SheetPoint(10.0, 10.0),
                        SheetPoint(0.0, 10.0),
                        SheetPoint(0.0, 0.0),
                    ),
                    length_mm=40.0,
                    component_id=1,
                ),
            ),
            width_mm=10.0,
            height_mm=10.0,
            thickness_mm=1.0,
        )
        layout = MaxRectsNestingEngine().nest(
            (NestingPart.from_sheet_analysis(name="square", analysis=analysis),),
            sheet_width_mm=50.0,
            sheet_height_mm=50.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            svg_path = export_sheet_svg(analysis, Path(temp_dir) / "part.svg")
            dxf_path = export_nesting_dxf(layout, Path(temp_dir) / "nesting.dxf")
            self.assertIn("<polyline", svg_path.read_text(encoding="utf-8"))
            dxf_text = dxf_path.read_text(encoding="utf-8")
            self.assertIn("LINE", dxf_text)
            self.assertIn("CUT", dxf_text)


if __name__ == "__main__":
    unittest.main()
