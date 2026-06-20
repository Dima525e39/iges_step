from __future__ import annotations

import unittest

from cad.edge_classifier import Bounds, EdgeRecord, FaceRecord, ThicknessFaceRecord
from cad.outer_contour_patch import (
    _collect_thickness_outer_cut_edges,
    _count_cut_edge_components,
)


class OuterContourPatchTests(unittest.TestCase):
    def test_collects_only_outer_boundary_edges(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        inner_face = FaceRecord(
            face=object(),
            bounds=Bounds(3.0, 3.0, 0.0, 77.0, 37.0, 1000.0),
            is_outer_longitudinal=False,
        )
        thickness_face = FaceRecord(
            face=object(),
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 3.0, 330.0),
            is_outer_longitudinal=False,
        )
        outer_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 0.0, 300.0),
            faces=[outer_face, thickness_face],
        )
        inner_edge = EdgeRecord(
            edge=object(),
            length_mm=24.0,
            bounds=Bounds(23.0, 3.0, 303.0, 47.0, 3.0, 303.0),
            faces=[inner_face, thickness_face],
        )
        thickness_record = ThicknessFaceRecord(
            face=thickness_face,
            area_mm2=90.0,
            thickness_mm=3.0,
            cut_length_mm=30.0,
            edges=(outer_edge, inner_edge),
        )

        cut_edges = _collect_thickness_outer_cut_edges(
            edge_classifier,
            (thickness_record,),
            axis="Z",
            length_mm=1000.0,
            tolerance=0.01,
        )

        self.assertEqual(cut_edges, (outer_edge,))

    def test_connected_outer_edges_are_one_pierce(self) -> None:
        import cad.edge_classifier as edge_classifier

        first = EdgeRecord(
            edge=object(),
            length_mm=40.0,
            start_point=(0.0, 0.0, 0.0),
            end_point=(40.0, 0.0, 0.0),
        )
        second = EdgeRecord(
            edge=object(),
            length_mm=20.0,
            start_point=(40.0, 0.0, 0.004),
            end_point=(40.0, 20.0, 0.0),
        )
        third = EdgeRecord(
            edge=object(),
            length_mm=25.0,
            start_point=(100.0, 0.0, 0.0),
            end_point=(125.0, 0.0, 0.0),
        )

        self.assertEqual(
            _count_cut_edge_components(
                edge_classifier,
                (first, second, third),
                tolerance=0.01,
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
