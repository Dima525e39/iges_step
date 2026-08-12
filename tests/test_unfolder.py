from __future__ import annotations

import unittest

from cad.edge_classifier import AUXILIARY_UNFOLD, CUT_END, CUT_FEATURE, Bounds, EdgeRecord
from cad.unfolder import build_unfolding_preview_from_edges


class TubeUnfolderTests(unittest.TestCase):
    def test_builds_preview_segments_from_counted_edges(self) -> None:
        global_bounds = Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0)
        cut_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 0.0, 300.0),
            start_point=(20.0, 0.0, 300.0),
            end_point=(50.0, 0.0, 300.0),
            reason="unfolded inner contour",
            edge_type=CUT_FEATURE,
        )

        preview = build_unfolding_preview_from_edges(
            (cut_edge,),
            axis="Z",
            global_bounds=global_bounds,
            cut_length_mm=30.0,
            pierce_count=1,
            tolerance=0.01,
            diagnostic_edge_length_mm=150.0,
        )

        self.assertEqual(preview.length_mm, 1000.0)
        self.assertEqual(preview.perimeter_mm, 240.0)
        self.assertEqual(preview.cut_length_mm, 30.0)
        self.assertEqual(preview.diagnostic_edge_length_mm, 150.0)
        self.assertEqual(preview.pierce_count, 1)
        self.assertEqual(len(preview.calculated_cut_segments), 1)
        self.assertEqual(len(preview.auxiliary_unfold_segments), 4)
        self.assertTrue(
            all(segment.length_mm == 0.0 for segment in preview.auxiliary_unfold_segments)
        )
        self.assertTrue(
            all(
                segment.edge_type == AUXILIARY_UNFOLD
                for segment in preview.auxiliary_unfold_segments
            )
        )
        self.assertEqual(preview.calculated_cut_segments[0].start.x_mm, 300.0)
        self.assertEqual(preview.calculated_cut_segments[0].start.y_mm, 20.0)

    def test_same_tube_end_segments_share_component_id(self) -> None:
        global_bounds = Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0)
        first = EdgeRecord(
            edge=object(),
            length_mm=80.0,
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 0.0),
            reason="unfolded tube end",
            edge_type=CUT_END,
        )
        second = EdgeRecord(
            edge=object(),
            length_mm=40.0,
            bounds=Bounds(80.0, 0.0, 0.0, 80.0, 40.0, 0.0),
            reason="unfolded tube end",
            edge_type=CUT_END,
        )
        opposite = EdgeRecord(
            edge=object(),
            length_mm=80.0,
            bounds=Bounds(0.0, 0.0, 1000.0, 80.0, 0.0, 1000.0),
            reason="unfolded tube end",
            edge_type=CUT_END,
        )

        preview = build_unfolding_preview_from_edges(
            (first, second, opposite),
            axis="Z",
            global_bounds=global_bounds,
            cut_length_mm=200.0,
            pierce_count=2,
            tolerance=0.01,
        )

        self.assertEqual(
            preview.calculated_cut_segments[0].component_id,
            preview.calculated_cut_segments[1].component_id,
        )
        self.assertNotEqual(
            preview.calculated_cut_segments[0].component_id,
            preview.calculated_cut_segments[2].component_id,
        )

    def test_preview_keeps_supplemental_and_reconstructed_cut_layers(self) -> None:
        global_bounds = Bounds(0.0, -50.0, 0.0, 1000.0, 50.0, 800.0)
        base = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            start_point=(100.0, -50.0, 200.0),
            end_point=(130.0, -50.0, 200.0),
            edge_type=CUT_FEATURE,
        )
        supplemental = EdgeRecord(
            edge=object(),
            length_mm=88.0,
            start_point=(200.0, -44.0, 300.0),
            end_point=(200.0, 44.0, 300.0),
            edge_type="SUPPLEMENTAL_CUT",
        )
        reconstructed = EdgeRecord(
            edge=None,
            length_mm=100.0,
            start_point=(300.0, -50.0, 400.0),
            end_point=(300.0, 50.0, 400.0),
            edge_type="RECONSTRUCTED_CUT",
        )

        preview = build_unfolding_preview_from_edges(
            (base,),
            axis="X",
            global_bounds=global_bounds,
            cut_length_mm=218.0,
            pierce_count=1,
            tolerance=0.01,
            supplemental_cut_edges=(supplemental,),
            reconstructed_cut_edges=(reconstructed,),
        )

        self.assertEqual(len(preview.calculated_cut_segments), 1)
        self.assertEqual(len(preview.supplemental_cut_segments), 1)
        self.assertEqual(len(preview.reconstructed_cut_segments), 1)
        self.assertEqual(preview.supplemental_cut_segments[0].length_mm, 88.0)
        self.assertEqual(preview.reconstructed_cut_segments[0].length_mm, 100.0)


if __name__ == "__main__":
    unittest.main()
