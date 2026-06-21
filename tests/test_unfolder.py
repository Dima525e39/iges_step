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


if __name__ == "__main__":
    unittest.main()
