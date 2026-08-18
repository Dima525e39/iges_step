from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cad.analyzer import analyze_shape
from cad.edge_classifier import Bounds, CUT_FEATURE, EdgeClassificationResult, EdgeRecord
from cad.kernel_v6 import TubeFrame, build_tube_kernel_model, infer_tube_frame
from cad.unfolder import build_unfolding_preview_from_edges


class TubeKernelV6Tests(unittest.TestCase):
    def test_analyzer_attaches_v6_kernel_without_replacing_numeric_result(self) -> None:
        cut = EdgeRecord(
            object(),
            30.0,
            bounds=Bounds(0.0, 0.0, 0.0, 0.0, 30.0, 0.0),
            start_point=(0.0, 0.0, 0.0),
            end_point=(0.0, 30.0, 0.0),
            edge_type=CUT_FEATURE,
            cut_component_id=1,
        )
        frame_edges = (
            EdgeRecord(object(), 1000.0, start_point=(0.0, 0.0, 0.0), end_point=(1000.0, 0.0, 0.0)),
            EdgeRecord(object(), 100.0, start_point=(0.0, 0.0, 0.0), end_point=(0.0, 100.0, 0.0)),
            EdgeRecord(object(), 100.0, start_point=(0.0, 0.0, 0.0), end_point=(0.0, 0.0, 100.0)),
            EdgeRecord(object(), 1000.0, start_point=(0.0, 100.0, 100.0), end_point=(1000.0, 100.0, 100.0)),
        )
        classification = EdgeClassificationResult(
            cut_edges=(cut,),
            calculated_cut_edges=(cut,),
            all_edge_count=len(frame_edges),
            outer_face_count=4,
            edge_records=frame_edges,
            length_axis="X",
            global_bounds=Bounds(0.0, 0.0, 0.0, 1000.0, 100.0, 100.0),
            tolerance=0.01,
            pierce_count_override=1,
            wall_thickness_mm=4.0,
            wall_thickness_method="плоские стенки",
            wall_thickness_confidence="высокая",
        )
        summary = SimpleNamespace(
            size_x_mm=1000.0,
            size_y_mm=100.0,
            size_z_mm=100.0,
            face_count=12,
            edge_count=24,
        )

        with (
            patch("cad.analyzer._count_topology_safely", return_value=0),
            patch("cad.analyzer.classify_cut_edges", return_value=classification),
        ):
            result = analyze_shape(
                object(),
                summary=summary,
                file_format="IGES",
                import_warnings=("IGES содержит поверхности без B-Rep solid/shell.",),
            )

        self.assertAlmostEqual(result.cut_length_mm, 30.0)
        self.assertEqual(result.pierce_count, 1)
        self.assertIsNotNone(result.tube_kernel)
        assert result.tube_kernel is not None
        self.assertAlmostEqual(result.tube_kernel.reported_cut_length_mm, 30.0)
        self.assertEqual(result.tube_kernel.schema_version, "tube-kernel-v6")

    def test_analyzer_uses_early_frame_dimensions_without_changing_cut_result(self) -> None:
        cut = EdgeRecord(
            object(),
            30.0,
            start_point=(0.0, 0.0, 0.0),
            end_point=(0.0, 30.0, 0.0),
            edge_type=CUT_FEATURE,
            cut_component_id=1,
        )
        frame = TubeFrame(
            origin=(0.0, 0.0, 0.0),
            axis=(0.8, 0.0, 0.6),
            cross_u=(0.0, 1.0, 0.0),
            cross_v=(-0.6, 0.0, 0.8),
            length_mm=100.0,
            width_mm=10.0,
            height_mm=10.0,
            method="oriented-edge-frame",
            confidence="high",
        )
        classification = EdgeClassificationResult(
            cut_edges=(cut,),
            calculated_cut_edges=(cut,),
            all_edge_count=1,
            outer_face_count=4,
            edge_records=(cut,),
            length_axis="X",
            global_bounds=Bounds(-6.0, 0.0, 0.0, 80.0, 10.0, 68.0),
            tolerance=0.01,
            pierce_count_override=1,
            cut_length_override_mm=30.0,
            tube_frame=frame,
            analysis_space="oriented-frame-legacy-shell-guard",
        )
        summary = SimpleNamespace(
            size_x_mm=86.0,
            size_y_mm=10.0,
            size_z_mm=68.0,
            face_count=12,
            edge_count=24,
        )

        with (
            patch("cad.analyzer._count_topology_safely", return_value=0),
            patch("cad.analyzer.classify_cut_edges", return_value=classification),
        ):
            result = analyze_shape(object(), summary=summary, file_format="IGES")

        self.assertAlmostEqual(result.length_mm, 100.0)
        self.assertAlmostEqual(result.width_mm, 10.0)
        self.assertAlmostEqual(result.height_mm, 10.0)
        self.assertAlmostEqual(result.cut_length_mm, 30.0)
        self.assertEqual(result.pierce_count, 1)
        self.assertIs(result.tube_kernel.frame, frame)

    def test_builds_model_from_confirmed_three_dimensional_contours(self) -> None:
        cut_edges = (
            EdgeRecord(
                object(),
                10.0,
                bounds=Bounds(0.0, 0.0, 0.0, 0.0, 10.0, 0.0),
                start_point=(0.0, 0.0, 0.0),
                end_point=(0.0, 10.0, 0.0),
                edge_type=CUT_FEATURE,
                cut_component_id=1,
            ),
            EdgeRecord(
                object(),
                10.0,
                bounds=Bounds(0.0, 10.0, 0.0, 0.0, 10.0, 10.0),
                start_point=(0.0, 10.0, 0.0),
                end_point=(0.0, 10.0, 10.0),
                edge_type=CUT_FEATURE,
                cut_component_id=1,
            ),
        )
        frame_edges = (
            EdgeRecord(
                object(),
                100.0,
                start_point=(0.0, 0.0, 0.0),
                end_point=(100.0, 0.0, 0.0),
            ),
            EdgeRecord(
                object(),
                10.0,
                start_point=(0.0, 0.0, 0.0),
                end_point=(0.0, 10.0, 0.0),
            ),
            EdgeRecord(
                object(),
                10.0,
                start_point=(0.0, 0.0, 0.0),
                end_point=(0.0, 0.0, 10.0),
            ),
            EdgeRecord(
                object(),
                100.0,
                start_point=(0.0, 10.0, 10.0),
                end_point=(100.0, 10.0, 10.0),
            ),
        )
        classification = EdgeClassificationResult(
            cut_edges=cut_edges,
            calculated_cut_edges=cut_edges,
            all_edge_count=len(frame_edges),
            outer_face_count=4,
            edge_records=frame_edges,
            length_axis="X",
            global_bounds=Bounds(0.0, 0.0, 0.0, 100.0, 10.0, 10.0),
            tolerance=0.01,
            pierce_count_override=1,
        )

        model = build_tube_kernel_model(
            classification,
            profile_type="Квадратная труба",
            outer_width_mm=10.0,
            outer_height_mm=10.0,
            wall_thickness_mm=1.0,
            wall_thickness_method="плоские стенки",
            wall_thickness_confidence="высокая",
            reported_cut_length_mm=20.0,
            reported_pierce_count=1,
        )

        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.schema_version, "tube-kernel-v6")
        self.assertEqual(model.frame.method, "oriented-edge-frame")
        self.assertAlmostEqual(model.reported_cut_length_mm, 20.0)
        self.assertAlmostEqual(model.contour_edge_length_mm, 20.0)
        self.assertEqual(model.reported_pierce_count, 1)
        self.assertEqual(len(model.cut_contours), 1)
        self.assertEqual(len(model.unfolded_contours), 1)
        self.assertEqual(model.toolpath_order.steps[0].component_id, 1)
        self.assertEqual(model.warnings, ())

    def test_infers_frame_for_slanted_tube(self) -> None:
        axis_end = (80.0, 0.0, 60.0)
        cross_u = (0.0, 10.0, 0.0)
        cross_v = (-6.0, 0.0, 8.0)
        far_corner = tuple(
            axis_end[index] + cross_u[index] + cross_v[index]
            for index in range(3)
        )
        edges = (
            EdgeRecord(object(), 100.0, start_point=(0.0, 0.0, 0.0), end_point=axis_end),
            EdgeRecord(object(), 100.0, start_point=(-6.0, 10.0, 8.0), end_point=far_corner),
            EdgeRecord(object(), 10.0, start_point=(0.0, 0.0, 0.0), end_point=cross_u),
            EdgeRecord(object(), 10.0, start_point=(0.0, 0.0, 0.0), end_point=cross_v),
            EdgeRecord(
                object(),
                10.0,
                start_point=tuple(axis_end[index] + cross_v[index] for index in range(3)),
                end_point=far_corner,
            ),
        )

        frame = infer_tube_frame(
            edges,
            length_axis="X",
            global_bounds=Bounds(-6.0, 0.0, 0.0, 80.0, 10.0, 68.0),
            tolerance=0.01,
        )

        self.assertEqual(frame.method, "oriented-edge-frame")
        self.assertAlmostEqual(frame.length_mm, 100.0, places=6)
        self.assertAlmostEqual(frame.width_mm, 10.0, places=6)
        self.assertAlmostEqual(frame.height_mm, 10.0, places=6)
        self.assertAlmostEqual(frame.local_coordinates((40.0, 0.0, 30.0))[0], 50.0)

    def test_unfold_preview_uses_oriented_frame_without_changing_cut_length(self) -> None:
        frame = infer_tube_frame(
            (
                EdgeRecord(
                    object(),
                    100.0,
                    start_point=(0.0, 0.0, 0.0),
                    end_point=(80.0, 0.0, 60.0),
                ),
                EdgeRecord(
                    object(),
                    10.0,
                    start_point=(0.0, 0.0, 0.0),
                    end_point=(0.0, 10.0, 0.0),
                ),
                EdgeRecord(
                    object(),
                    10.0,
                    start_point=(0.0, 0.0, 0.0),
                    end_point=(-6.0, 0.0, 8.0),
                ),
                EdgeRecord(
                    object(),
                    100.0,
                    start_point=(-6.0, 10.0, 8.0),
                    end_point=(74.0, 10.0, 68.0),
                ),
            ),
            length_axis="X",
            global_bounds=Bounds(-6.0, 0.0, 0.0, 80.0, 10.0, 68.0),
            tolerance=0.01,
        )
        cut = EdgeRecord(
            object(),
            10.0,
            start_point=(40.0, 0.0, 30.0),
            end_point=(40.0, 10.0, 30.0),
            edge_type=CUT_FEATURE,
            cut_component_id=1,
        )

        preview = build_unfolding_preview_from_edges(
            (cut,),
            axis="X",
            global_bounds=Bounds(-6.0, 0.0, 0.0, 80.0, 10.0, 68.0),
            cut_length_mm=123.456,
            pierce_count=1,
            tolerance=0.01,
            tube_frame=frame,
        )

        self.assertEqual(preview.frame_method, "oriented-edge-frame")
        self.assertAlmostEqual(preview.length_mm, 100.0)
        self.assertAlmostEqual(preview.calculated_cut_segments[0].start.x_mm, 50.0)
        self.assertAlmostEqual(preview.cut_length_mm, 123.456)


if __name__ == "__main__":
    unittest.main()
