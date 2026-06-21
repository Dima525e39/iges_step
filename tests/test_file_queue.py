from __future__ import annotations

import sys
import types
import unittest

from cad.analyzer import GeometryAnalysisResult, analyze_shape
from cad.edge_classifier import (
    Bounds,
    CUT_END,
    CUT_FEATURE,
    IGNORED_LONGITUDINAL,
    IGNORED_PROFILE,
    EdgeRecord,
    FaceRecord,
    ThicknessFaceRecord,
    _classify_edge_groups,
    _collect_thickness_outer_cut_edges,
    _count_cut_edge_components,
    _count_thickness_face_components,
    _estimate_face_thickness,
    _is_cut_edge_candidate,
    _is_thickness_face_candidate,
)
from cad.importer import CadImportError, CadImporter
from cad.pierce_counter import _count_components_from_pairs
from cad.profile_detector import detect_profile_from_dimensions
from cad.shape_summary import ShapeSummary
from cad.supported_formats import collect_supported_files, is_supported_cad_file
from core.file_queue import FileQueue


class FakeTopExpExplorer:
    def __init__(self, shape: object, shape_type: int) -> None:
        self.remaining = 2

    def More(self) -> bool:
        return self.remaining > 0

    def Next(self) -> None:
        self.remaining -= 1


class FakeVertex:
    def __init__(self, name: str) -> None:
        self.name = name

    def IsSame(self, other: object) -> bool:
        return isinstance(other, FakeVertex) and self.name == other.name


class SupportedFormatTests(unittest.TestCase):
    def test_supported_extensions_are_case_insensitive(self) -> None:
        self.assertTrue(is_supported_cad_file("part.STEP"))
        self.assertTrue(is_supported_cad_file("part.igs"))
        self.assertFalse(is_supported_cad_file("part.txt"))

    def test_folder_scan_collects_supported_files(self) -> None:
        with self.subTest("recursive supported-file scan"):
            from tempfile import TemporaryDirectory
            from pathlib import Path

            with TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "a.step").write_text("", encoding="utf-8")
                (root / "nested").mkdir()
                (root / "nested" / "b.IGES").write_text("", encoding="utf-8")
                (root / "nested" / "ignore.txt").write_text("", encoding="utf-8")

                supported, unsupported = collect_supported_files([root])

        self.assertEqual([path.name for path in supported], ["a.step", "b.IGES"])
        self.assertEqual(unsupported, [])


class FileQueueTests(unittest.TestCase):
    def test_queue_skips_duplicates(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "tube.stp"
            file_path.write_text("", encoding="utf-8")

            queue = FileQueue()
            first = queue.add_paths([file_path])
            second = queue.add_paths([file_path])

        self.assertEqual(len(first.added), 1)
        self.assertEqual(len(second.added), 0)
        self.assertEqual(len(second.duplicates), 1)


class CadImporterTests(unittest.TestCase):
    def test_detect_format_uses_supported_extensions(self) -> None:
        self.assertEqual(CadImporter.detect_format("tube.step"), "STEP")
        self.assertEqual(CadImporter.detect_format("tube.STP"), "STEP")
        self.assertEqual(CadImporter.detect_format("tube.iges"), "IGES")
        self.assertEqual(CadImporter.detect_format("tube.IGS"), "IGES")
        self.assertEqual(CadImporter.detect_format("tube.txt"), "UNKNOWN")

    def test_unsupported_import_raises_before_occ_dependency_is_needed(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            unsupported = Path(temp_dir) / "tube.txt"
            unsupported.write_text("", encoding="utf-8")

            with self.assertRaises(CadImportError):
                CadImporter().import_file(unsupported)

    def test_non_ascii_path_is_copied_to_ascii_temp_path_for_opencascade(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "деталь.step"
            source.write_text("STEP DATA", encoding="utf-8")

            with CadImporter._path_for_opencascade(source) as read_path:
                self.assertTrue(str(read_path).isascii())
                self.assertEqual(read_path.suffix, ".step")
                self.assertEqual(read_path.read_text(encoding="utf-8"), "STEP DATA")

    def test_ascii_path_is_used_directly_for_opencascade(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "part.step"
            source.write_text("STEP DATA", encoding="utf-8")

            with CadImporter._path_for_opencascade(source) as read_path:
                self.assertEqual(read_path, source)

    def test_count_topology_imports_top_exp_explorer_in_helper_scope(self) -> None:
        from cad.shape_summary import _count_topology

        module_names = ["OCC", "OCC.Core", "OCC.Core.TopExp"]
        originals = {name: sys.modules.get(name) for name in module_names}

        occ_module = types.ModuleType("OCC")
        core_module = types.ModuleType("OCC.Core")
        top_exp_module = types.ModuleType("OCC.Core.TopExp")
        top_exp_module.TopExp_Explorer = FakeTopExpExplorer

        try:
            sys.modules["OCC"] = occ_module
            sys.modules["OCC.Core"] = core_module
            sys.modules["OCC.Core.TopExp"] = top_exp_module

            self.assertEqual(_count_topology(object(), 1), 2)
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original


class GeometryAnalyzerTests(unittest.TestCase):
    def test_analyze_shape_uses_longest_bounding_box_axis_as_length(self) -> None:
        summary = ShapeSummary(
            diagonal_mm=105.0,
            size_x_mm=20.0,
            size_y_mm=10.0,
            size_z_mm=100.0,
            face_count=6,
            edge_count=12,
        )

        result = analyze_shape(None, summary=summary, file_format="STEP")

        self.assertIsInstance(result, GeometryAnalysisResult)
        self.assertEqual(result.length_axis, "Z")
        self.assertEqual(result.length_mm, 100.0)
        self.assertEqual(result.width_mm, 20.0)
        self.assertEqual(result.height_mm, 10.0)
        self.assertEqual(result.face_count, 6)
        self.assertEqual(result.profile_hint, "Прямоугольная профильная труба")

    def test_analyze_shape_requires_shape_or_summary(self) -> None:
        with self.assertRaises(ValueError):
            analyze_shape(None)

    def test_profile_detector_marks_rectangular_tube_from_bbox(self) -> None:
        profile = detect_profile_from_dimensions(1000.0, 80.0, 40.0)

        self.assertEqual(profile.profile_type, "Прямоугольная профильная труба")
        self.assertEqual(profile.confidence, "средняя")

    def test_pierce_counter_groups_connected_edges(self) -> None:
        a = FakeVertex("a")
        b = FakeVertex("b")
        c = FakeVertex("c")
        d = FakeVertex("d")
        e = FakeVertex("e")
        f = FakeVertex("f")

        estimate = _count_components_from_pairs(
            (
                (a, b),
                (b, c),
                (d, e),
                (e, f),
                (f, d),
            )
        )

        self.assertEqual(estimate.pierce_count, 2)

    def test_pierce_counter_groups_edges_by_matching_points(self) -> None:
        estimate = _count_components_from_pairs(
            (
                ((None, (0.0, 0.0, 0.0)), (None, (10.0, 0.0, 0.0))),
                ((None, (10.0, 0.0, 0.005)), (None, (20.0, 0.0, 0.0))),
            )
        )

        self.assertEqual(estimate.pierce_count, 1)

    def test_cut_edge_candidate_accepts_outer_cut_face_boundary(self) -> None:
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        cut_face = FaceRecord(
            face=object(),
            bounds=Bounds(70.0, 0.0, 430.0, 80.0, 20.0, 470.0),
            is_outer_longitudinal=False,
        )
        edge = EdgeRecord(
            edge=object(),
            length_mm=35.0,
            bounds=Bounds(70.0, 0.0, 450.0, 80.0, 20.0, 450.0),
            faces=[outer_face, cut_face],
        )

        self.assertTrue(
            _is_cut_edge_candidate(
                edge,
                axis="Z",
                length_mm=1000.0,
                has_outer_faces=True,
                tolerance=0.01,
            )
        )
        self.assertEqual(edge.reason, "outer/cut face boundary")

    def test_cut_edge_candidate_accepts_marked_outer_wire_segment(self) -> None:
        first_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        second_face = FaceRecord(
            face=object(),
            bounds=Bounds(80.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            is_outer_longitudinal=True,
        )
        edge = EdgeRecord(
            edge=object(),
            length_mm=35.0,
            bounds=Bounds(70.0, 0.0, 450.0, 80.0, 20.0, 450.0),
            faces=[first_face, second_face],
            wire_roles={"outer_wire_cut"},
        )

        self.assertTrue(
            _is_cut_edge_candidate(
                edge,
                axis="Z",
                length_mm=1000.0,
                has_outer_faces=True,
                tolerance=0.01,
            )
        )
        self.assertEqual(edge.reason, "outer wire cut segment")

    def test_cut_edge_candidate_rejects_longitudinal_tube_seam(self) -> None:
        first_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        second_face = FaceRecord(
            face=object(),
            bounds=Bounds(80.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            is_outer_longitudinal=True,
        )
        edge = EdgeRecord(
            edge=object(),
            length_mm=1000.0,
            bounds=Bounds(80.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            faces=[first_face, second_face],
        )

        self.assertFalse(
            _is_cut_edge_candidate(
                edge,
                axis="Z",
                length_mm=1000.0,
                has_outer_faces=True,
                tolerance=0.01,
            )
        )

    def test_classify_edge_groups_counts_only_cut_feature_and_cut_end(self) -> None:
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        end_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 0.0),
            is_outer_longitudinal=False,
        )
        feature_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 0.0, 300.0),
            faces=[outer_face],
            wire_roles={"inner_wire"},
        )
        end_edge = EdgeRecord(
            edge=object(),
            length_mm=80.0,
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 0.0),
            faces=[outer_face, end_face],
        )
        longitudinal_edge = EdgeRecord(
            edge=object(),
            length_mm=1000.0,
            bounds=Bounds(0.0, 0.0, 0.0, 0.0, 0.0, 1000.0),
            faces=[outer_face],
        )
        profile_edge = EdgeRecord(
            edge=object(),
            length_mm=40.0,
            bounds=Bounds(0.0, 0.0, 500.0, 40.0, 0.0, 500.0),
            faces=[outer_face],
        )

        groups = _classify_edge_groups(
            (feature_edge, end_edge, longitudinal_edge, profile_edge),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            has_outer_faces=True,
            tolerance=0.01,
        )

        self.assertEqual(groups.calculated_cut_edges, (feature_edge, end_edge))
        self.assertEqual(feature_edge.edge_type, CUT_FEATURE)
        self.assertEqual(end_edge.edge_type, CUT_END)
        self.assertEqual(longitudinal_edge.edge_type, IGNORED_LONGITUDINAL)
        self.assertEqual(profile_edge.edge_type, IGNORED_PROFILE)

    def test_thickness_face_candidate_requires_outer_touch(self) -> None:
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        thickness_face = FaceRecord(
            face=object(),
            bounds=Bounds(30.0, 0.0, 430.0, 50.0, 3.0, 470.0),
            is_outer_longitudinal=False,
        )
        edge = EdgeRecord(
            edge=object(),
            length_mm=20.0,
            bounds=Bounds(30.0, 0.0, 450.0, 50.0, 0.0, 450.0),
            faces=[outer_face, thickness_face],
        )

        self.assertTrue(
            _is_thickness_face_candidate(
                thickness_face,
                (edge,),
                axis="Z",
                length_mm=1000.0,
                tolerance=0.01,
            )
        )

    def test_estimate_face_thickness_uses_short_boundary_edges(self) -> None:
        thickness = _estimate_face_thickness(
            Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 0.0),
            (3.0, 3.0, 40.0, 40.0, 80.0, 80.0),
            tolerance=0.01,
        )

        self.assertEqual(thickness, 3.0)

    def test_thickness_face_components_group_touching_faces(self) -> None:
        first_edge = EdgeRecord(
            edge=object(),
            length_mm=40.0,
            start_point=(0.0, 0.0, 0.0),
            end_point=(40.0, 0.0, 0.0),
        )
        second_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            start_point=(40.0, 0.0, 0.005),
            end_point=(40.0, 30.0, 0.0),
        )
        first_face = ThicknessFaceRecord(
            face=FaceRecord(object(), Bounds(0.0, 0.0, 0.0, 40.0, 3.0, 3.0), False),
            area_mm2=120.0,
            thickness_mm=3.0,
            cut_length_mm=40.0,
            edges=(first_edge,),
        )
        second_face = ThicknessFaceRecord(
            face=FaceRecord(object(), Bounds(40.0, 0.0, 0.0, 43.0, 30.0, 3.0), False),
            area_mm2=90.0,
            thickness_mm=3.0,
            cut_length_mm=30.0,
            edges=(second_edge,),
        )

        self.assertEqual(
            _count_thickness_face_components((first_face, second_face), tolerance=0.01),
            1,
        )

    def test_thickness_outer_cut_edges_use_only_outer_boundary(self) -> None:
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
        short_edge = EdgeRecord(
            edge=object(),
            length_mm=3.0,
            bounds=Bounds(20.0, 0.0, 300.0, 20.0, 3.0, 300.0),
            faces=[thickness_face],
        )
        thickness_record = ThicknessFaceRecord(
            face=thickness_face,
            area_mm2=90.0,
            thickness_mm=3.0,
            cut_length_mm=30.0,
            edges=(outer_edge, inner_edge, short_edge),
        )

        cut_edges = _collect_thickness_outer_cut_edges(
            (thickness_record,),
            axis="Z",
            length_mm=1000.0,
            tolerance=0.01,
        )

        self.assertEqual(cut_edges, (outer_edge,))
        self.assertEqual(outer_edge.reason, "outer thickness contour")

    def test_cut_edge_components_count_one_wrapped_cut_as_one_pierce(self) -> None:
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
            _count_cut_edge_components((first, second, third), tolerance=0.01),
            2,
        )


if __name__ == "__main__":
    unittest.main()
