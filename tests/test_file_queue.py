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
    IGNORED_PLANE_RADIUS,
    IGNORED_PROFILE,
    EdgeRecord,
    EdgeClassificationResult,
    FaceRecord,
    ThicknessFaceRecord,
    _analyze_cut_faces,
    _analyze_round_tube_bspline_bbox_fallback,
    _analyze_round_tube_edge_fallback,
    _analyze_round_tube_outer_loops,
    _classify_edge_groups,
    _collect_thickness_outer_cut_edges,
    _count_cut_edge_components,
    _count_thickness_face_components,
    _estimate_face_thickness,
    _is_cut_edge_candidate,
    _is_outer_longitudinal_face,
    _is_thickness_face_candidate,
    WireRecord,
    estimate_wall_thickness,
)
from cad.debug_edges import write_debug_edges_csv
from cad.importer import CadImportError, CadImporter, _sew_iges_shape
from cad.pierce_counter import _count_components_from_pairs
from cad.profile_detector import detect_profile_from_dimensions
from cad.shape_summary import ShapeSummary
from cad.supported_formats import collect_supported_files, is_supported_cad_file
from core.file_job import parse_quantity_from_filename
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


class FakeCylinderFace:
    def __init__(self, radius_mm: float) -> None:
        self.radius_mm = radius_mm


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

    def test_queue_parses_quantity_from_filename(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "bracket_x5.dxf"
            file_path.write_text("", encoding="utf-8")

            queue = FileQueue()
            result = queue.add_paths([file_path])

        self.assertEqual(len(result.added), 1)
        self.assertEqual(result.added[0].quantity, 5)

    def test_parse_quantity_from_filename(self) -> None:
        cases = {
            "part_x5.dxf": 5,
            "part 12шт.dxf": 12,
            "part qty-7.step": 7,
            "part (3).igs": 1,
            "part 3шт.igs": 3,
            "МС-УСК-240-002.step": 1,
            "tube 40x20x2.dxf": 1,
            "profile_35x2.5.dxf": 1,
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(parse_quantity_from_filename(filename), expected)


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

    def test_sew_iges_shape_returns_shape_unchanged_when_sewing_unavailable(self) -> None:
        # When OpenCascade (or its sewing API) is not importable, healing must
        # be a no-op that returns the original shape so import never regresses.
        sentinel = object()
        self.assertIs(_sew_iges_shape(sentinel), sentinel)

    def test_sew_iges_shape_passes_none_through(self) -> None:
        self.assertIsNone(_sew_iges_shape(None))

    def test_sew_iges_shape_returns_sewed_result(self) -> None:
        sewed_marker = object()

        class FakeSewing:
            def __init__(self, tolerance: float) -> None:
                self.tolerance = tolerance
                self.added: list[object] = []
                self.performed = False

            def Add(self, shape: object) -> None:
                self.added.append(shape)

            def Perform(self) -> None:
                self.performed = True

            def SewedShape(self) -> object:
                return types.SimpleNamespace(IsNull=lambda: False, _marker=sewed_marker)

        module_names = ["OCC", "OCC.Core", "OCC.Core.BRepBuilderAPI"]
        originals = {name: sys.modules.get(name) for name in module_names}

        occ_module = types.ModuleType("OCC")
        core_module = types.ModuleType("OCC.Core")
        builder_module = types.ModuleType("OCC.Core.BRepBuilderAPI")
        builder_module.BRepBuilderAPI_Sewing = FakeSewing

        try:
            sys.modules["OCC"] = occ_module
            sys.modules["OCC.Core"] = core_module
            sys.modules["OCC.Core.BRepBuilderAPI"] = builder_module

            result = _sew_iges_shape(object())
        finally:
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        self.assertIs(result._marker, sewed_marker)

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

    def test_outer_longitudinal_face_uses_orientation_not_length_fraction(self) -> None:
        # Envelope of a 25x25 tube, 1000 mm long along Z.
        gb = Bounds(0.0, 0.0, 0.0, 25.0, 25.0, 1000.0)
        kw = dict(axis="Z", length_mm=1000.0, global_bounds=gb, tolerance=0.5)

        def outer(bounds: Bounds) -> bool:
            return _is_outer_longitudinal_face(bounds, **kw)

        # Flat wall segment on the X=25 face, short axially because features
        # split it: still outer skin (≈0 extent perpendicular to the side).
        self.assertTrue(outer(Bounds(25.0, 2.0, 400.0, 25.0, 22.0, 500.0)))
        # Corner-radius face hugging the x+/y+ envelope corner, running along
        # the axis: outer skin even though features split it into a segment.
        self.assertTrue(outer(Bounds(22.75, 22.75, 100.0, 25.0, 25.0, 500.0)))

        # Short cope corner at a tube end (tiny axial run) is NOT skin — it is a
        # cut face and must stay available for pierce grouping.
        self.assertFalse(outer(Bounds(22.75, 22.75, 0.0, 25.0, 25.0, 2.0)))
        # A cut/thickness wall reaches inward by the wall thickness (~1.5 mm),
        # so its perpendicular extent is non-zero -> not outer skin.
        self.assertFalse(outer(Bounds(23.5, 10.0, 400.0, 25.0, 14.0, 404.0)))
        # End-cap (axial extent ~0) is never longitudinal skin.
        self.assertFalse(outer(Bounds(0.0, 0.0, 0.0, 25.0, 25.0, 0.0)))
        # Inner wall does not touch the outer envelope.
        self.assertFalse(outer(Bounds(2.0, 2.0, 0.0, 2.0, 22.0, 1000.0)))

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

    def test_plane_radius_transition_is_ignored_separately(self) -> None:
        first_outer = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        second_outer = FaceRecord(
            face=object(),
            bounds=Bounds(80.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            is_outer_longitudinal=True,
        )
        transition = EdgeRecord(
            edge=object(),
            length_mm=1000.0,
            bounds=Bounds(80.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            faces=[first_outer, second_outer],
        )

        groups = _classify_edge_groups(
            (transition,),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            has_outer_faces=True,
            tolerance=0.01,
        )

        self.assertEqual(groups.ignored_plane_radius_edges, (transition,))
        self.assertEqual(transition.edge_type, IGNORED_PLANE_RADIUS)

    def test_wall_thickness_uses_flat_outer_and_inner_walls(self) -> None:
        global_bounds = Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0)
        faces = (
            FaceRecord(object(), Bounds(0.0, 0.0, 0.0, 0.0, 40.0, 1000.0), True),
            FaceRecord(object(), Bounds(80.0, 0.0, 0.0, 80.0, 40.0, 1000.0), True),
            FaceRecord(object(), Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0), True),
            FaceRecord(object(), Bounds(0.0, 40.0, 0.0, 80.0, 40.0, 1000.0), True),
            FaceRecord(object(), Bounds(3.0, 3.0, 0.0, 3.0, 37.0, 1000.0), False),
            FaceRecord(object(), Bounds(77.0, 3.0, 0.0, 77.0, 37.0, 1000.0), False),
            FaceRecord(object(), Bounds(3.0, 3.0, 0.0, 77.0, 3.0, 1000.0), False),
            FaceRecord(object(), Bounds(3.0, 37.0, 0.0, 77.0, 37.0, 1000.0), False),
        )

        estimate = estimate_wall_thickness(
            faces,
            (),
            axis="Z",
            length_mm=1000.0,
            global_bounds=global_bounds,
            tolerance=0.01,
        )

        self.assertEqual(estimate.thickness_mm, 3.0)
        self.assertEqual(estimate.method, "плоские стенки наружный/внутренний контур")
        self.assertEqual(estimate.confidence, "высокая")

    def test_wall_thickness_uses_round_radii_when_cylinders_are_reliable(self) -> None:
        faces = (
            FaceRecord(
                FakeCylinderFace(50.0),
                Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
                True,
            ),
            FaceRecord(
                FakeCylinderFace(47.0),
                Bounds(-47.0, -47.0, 0.0, 47.0, 47.0, 1000.0),
                False,
            ),
        )

        estimate = estimate_wall_thickness(
            faces,
            (),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            tolerance=0.01,
        )

        self.assertEqual(estimate.thickness_mm, 3.0)
        self.assertEqual(estimate.method, "цилиндры R_outer - R_inner")
        self.assertEqual(estimate.confidence, "высокая")

    def test_wall_thickness_normalizes_diameter_like_round_values(self) -> None:
        faces = (
            FaceRecord(
                FakeCylinderFace(100.0),
                Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
                True,
            ),
            FaceRecord(
                FakeCylinderFace(94.0),
                Bounds(-47.0, -47.0, 0.0, 47.0, 47.0, 1000.0),
                False,
            ),
        )

        estimate = estimate_wall_thickness(
            faces,
            (),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            tolerance=0.01,
        )

        self.assertEqual(estimate.thickness_mm, 3.0)
        self.assertEqual(estimate.method, "цилиндры R_outer - R_inner")

    def test_wall_thickness_accepts_doubled_round_bbox_with_real_radius(self) -> None:
        faces = (
            FaceRecord(
                FakeCylinderFace(17.5),
                Bounds(-35.0, -33.65, 0.0, 35.0, 33.65, 1000.0),
                True,
            ),
            FaceRecord(
                FakeCylinderFace(15.0),
                Bounds(-30.0, -28.65, 0.0, 30.0, 28.65, 1000.0),
                False,
            ),
        )

        estimate = estimate_wall_thickness(
            faces,
            (),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(-35.0, -33.65, 0.0, 35.0, 33.65, 1000.0),
            tolerance=0.01,
        )

        self.assertEqual(estimate.thickness_mm, 2.5)
        self.assertEqual(estimate.method, "цилиндры R_outer - R_inner")

    def test_round_tube_uses_outer_cylindrical_face_loops(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(50.0),
            Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            True,
        )
        inner_face = FaceRecord(
            FakeCylinderFace(47.0),
            Bounds(-47.0, -47.0, 0.0, 47.0, 47.0, 1000.0),
            False,
        )
        end_face = FaceRecord(
            object(),
            Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 0.0),
            False,
        )
        cut_face = FaceRecord(
            object(),
            Bounds(0.0, -50.0, 400.0, 20.0, -47.0, 420.0),
            False,
        )
        end_edge_shape = object()
        cut_edge_shape = object()
        end_edge = EdgeRecord(
            edge=end_edge_shape,
            length_mm=314.0,
            bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 0.0),
            faces=[outer_face, end_face],
        )
        cut_edge = EdgeRecord(
            edge=cut_edge_shape,
            length_mm=30.0,
            bounds=Bounds(0.0, -50.0, 400.0, 20.0, -50.0, 420.0),
            faces=[outer_face, cut_face],
        )
        seam_edge = EdgeRecord(
            edge=object(),
            length_mm=1000.0,
            bounds=Bounds(50.0, 0.0, 0.0, 50.0, 0.0, 1000.0),
            faces=[outer_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [
                WireRecord(object(), face_record, (end_edge_shape,), 314.0),
                WireRecord(object(), face_record, (cut_edge_shape, seam_edge.edge), 1030.0),
            ]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face, inner_face, end_face, cut_face),
                (end_edge, cut_edge, seam_edge),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (end_edge, cut_edge))
        self.assertEqual(analysis.pierce_count, 2)
        self.assertEqual(end_edge.edge_type, CUT_END)
        self.assertEqual(cut_edge.edge_type, CUT_FEATURE)
        self.assertEqual(seam_edge.edge_type, "")

    def test_round_bspline_tube_uses_outer_bbox_contours(self) -> None:
        faces = (
            FaceRecord(object(), Bounds(0.0, -133.0, -66.5, 3910.0, 0.0, 66.5), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -66.5, 3910.0, 133.0, 66.5), False),
            FaceRecord(object(), Bounds(0.0, -121.0, -60.5, 3910.0, 0.0, 60.5), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -60.5, 3910.0, 121.0, 60.5), False),
        )
        edges: list[EdgeRecord] = []
        for x in (0.0, 3910.0):
            edges.extend(
                [
                    EdgeRecord(
                        object(),
                        208.915911,
                        bounds=Bounds(x, -66.5, -66.5, x, 0.0, 66.5),
                    ),
                    EdgeRecord(
                        object(),
                        208.915911,
                        bounds=Bounds(x, 0.0, -66.5, x, 66.5, 66.5),
                    ),
                    EdgeRecord(
                        object(),
                        190.066356,
                        bounds=Bounds(x, -60.5, -60.5, x, 0.0, 60.5),
                    ),
                    EdgeRecord(
                        object(),
                        190.066356,
                        bounds=Bounds(x, 0.0, -60.5, x, 60.5, 60.5),
                    ),
                ]
            )

        for index in range(38):
            start = 405.748119 + index * 90.0
            middle = start + 29.252677
            end = middle + 29.254698
            edges.extend(
                [
                    EdgeRecord(
                        object(),
                        93.112948,
                        bounds=Bounds(start, 6.841503, 35.145982, middle, 56.453909, 66.147852),
                    ),
                    EdgeRecord(
                        object(),
                        93.113290,
                        bounds=Bounds(middle, 6.840258, 35.144737, end, 56.455155, 66.149097),
                    ),
                    EdgeRecord(
                        object(),
                        93.399673,
                        bounds=Bounds(start, 3.257850, 29.410999, middle, 52.870457, 60.413069),
                    ),
                    EdgeRecord(
                        object(),
                        6.762450,
                        bounds=Bounds(middle, 3.258747, 60.412172, middle, 6.842299, 66.147056),
                    ),
                ]
            )

        for start in (53.497532, 3811.497532):
            end = start + 45.004936
            edges.extend(
                [
                    EdgeRecord(
                        object(),
                        71.219007,
                        bounds=Bounds(start, -0.002468, -66.502468, end, 22.503209, -62.575217),
                    ),
                    EdgeRecord(
                        object(),
                        71.219359,
                        bounds=Bounds(start, -22.502281, -66.502055, end, 0.002055, -62.575815),
                    ),
                    EdgeRecord(
                        object(),
                        71.338471,
                        bounds=Bounds(start, -22.501082, -60.500485, end, 0.000485, -56.159760),
                    ),
                ]
            )

        analysis = _analyze_round_tube_bspline_bbox_fallback(
            faces,
            edges,
            axis="X",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -66.5, -66.5, 3910.0, 66.5, 66.5),
            has_outer_faces=False,
            tolerance=0.01,
        )
        estimate = estimate_wall_thickness(
            faces,
            edges,
            axis="X",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -66.5, -66.5, 3910.0, 66.5, 66.5),
            tolerance=0.01,
        )

        self.assertEqual(analysis.pierce_count, 42)
        self.assertEqual(len(analysis.cut_edges), 84)
        self.assertAlmostEqual(analysis.outer_radius_mm * 2.0, 133.0)
        self.assertAlmostEqual(sum(edge.length_mm for edge in analysis.cut_edges), 8197.137420)
        self.assertAlmostEqual(estimate.thickness_mm, 6.0)
        self.assertEqual(estimate.method, "bbox круглой BSpline-трубы R_outer - R_inner")

    def test_round_tube_loop_analysis_accepts_outer_cylinder_without_inner_radius(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(50.0),
            Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            True,
        )
        cut_face = FaceRecord(
            object(),
            Bounds(0.0, -50.0, 400.0, 20.0, -47.0, 420.0),
            False,
        )
        cut_edge_shape = object()
        cut_edge = EdgeRecord(
            edge=cut_edge_shape,
            length_mm=30.0,
            bounds=Bounds(0.0, -50.0, 400.0, 20.0, -50.0, 420.0),
            faces=[outer_face, cut_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [WireRecord(object(), face_record, (cut_edge_shape,), 30.0)]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face, cut_face),
                (cut_edge,),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (cut_edge,))
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual(analysis.outer_radius_mm, 50.0)
        self.assertEqual(cut_edge.edge_type, CUT_FEATURE)

    def test_round_tube_loop_analysis_normalizes_diameter_like_cylinder_value(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(100.0),
            Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            True,
        )
        end_edge_shape = object()
        end_edge = EdgeRecord(
            edge=end_edge_shape,
            length_mm=314.0,
            bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 0.0),
            faces=[outer_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [WireRecord(object(), face_record, (end_edge_shape,), 314.0)]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face,),
                (end_edge,),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (end_edge,))
        self.assertEqual(analysis.outer_radius_mm, 50.0)
        self.assertEqual(end_edge.edge_type, CUT_END)

    def test_round_tube_loop_analysis_accepts_doubled_bbox_with_real_radius(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(17.5),
            Bounds(-35.0, -33.65, 0.0, 35.0, 33.65, 1000.0),
            True,
        )
        inner_face = FaceRecord(
            FakeCylinderFace(15.0),
            Bounds(-30.0, -28.65, 0.0, 30.0, 28.65, 1000.0),
            False,
        )
        end_edge_shape = object()
        end_edge = EdgeRecord(
            edge=end_edge_shape,
            length_mm=110.0,
            bounds=Bounds(-17.5, -17.5, 0.0, 17.5, 17.5, 0.0),
            faces=[outer_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [WireRecord(object(), face_record, (end_edge_shape,), 110.0)]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face, inner_face),
                (end_edge,),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-35.0, -33.65, 0.0, 35.0, 33.65, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (end_edge,))
        self.assertEqual(analysis.outer_radius_mm, 17.5)
        self.assertEqual(end_edge.edge_type, CUT_END)

    def test_round_tube_loop_analysis_deduplicates_same_physical_loop(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(17.5),
            Bounds(-17.5, -17.5, 0.0, 17.5, 17.5, 1000.0),
            True,
        )
        first_edge_shape = object()
        second_edge_shape = object()
        first_edge = EdgeRecord(
            edge=first_edge_shape,
            length_mm=407.2,
            bounds=Bounds(-17.5, -17.5, 120.0, 17.5, 17.5, 120.0),
            faces=[outer_face],
        )
        second_edge = EdgeRecord(
            edge=second_edge_shape,
            length_mm=423.7,
            bounds=Bounds(-17.4, -17.4, 120.0, 17.4, 17.4, 120.0),
            faces=[outer_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [
                WireRecord(object(), face_record, (first_edge_shape,), 407.2),
                WireRecord(object(), face_record, (second_edge_shape,), 423.7),
            ]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face,),
                (first_edge, second_edge),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-17.5, -17.5, 0.0, 17.5, 17.5, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (first_edge,))
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual(sum(edge.length_mm for edge in analysis.cut_edges), 407.2)

    def test_round_tube_loop_analysis_counts_both_tube_ends(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(17.5),
            Bounds(-17.5, -17.5, 0.0, 17.5, 17.5, 1000.0),
            True,
        )
        min_end_shape = object()
        max_end_shape = object()
        min_end = EdgeRecord(
            edge=min_end_shape,
            length_mm=110.0,
            bounds=Bounds(-17.5, -17.5, 0.0, 17.5, 17.5, 0.0),
            faces=[outer_face],
        )
        max_end = EdgeRecord(
            edge=max_end_shape,
            length_mm=112.0,
            bounds=Bounds(-17.5, -17.5, 997.0, 17.5, 17.5, 1000.0),
            faces=[outer_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [
                WireRecord(object(), face_record, (min_end_shape,), 110.0),
                WireRecord(object(), face_record, (max_end_shape,), 112.0),
            ]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face,),
                (min_end, max_end),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-17.5, -17.5, 0.0, 17.5, 17.5, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (min_end, max_end))
        self.assertEqual(analysis.pierce_count, 2)
        self.assertEqual(min_end.edge_type, CUT_END)
        self.assertEqual(max_end.edge_type, CUT_END)

    def test_round_tube_loop_analysis_keeps_edges_with_incomplete_adjacency(self) -> None:
        import cad.edge_classifier as edge_classifier

        outer_face = FaceRecord(
            FakeCylinderFace(50.0),
            Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            True,
        )
        end_edge_shape = object()
        end_edge = EdgeRecord(
            edge=end_edge_shape,
            length_mm=314.0,
            bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 0.0),
            faces=[outer_face],
        )
        original_collect_wire_records = edge_classifier._collect_wire_records

        def fake_collect_wire_records(face_record, *, warnings):
            if face_record is not outer_face:
                return []
            return [WireRecord(object(), face_record, (end_edge_shape,), 314.0)]

        edge_classifier._collect_wire_records = fake_collect_wire_records
        try:
            analysis = _analyze_round_tube_outer_loops(
                (outer_face,),
                (end_edge,),
                axis="Z",
                length_mm=1000.0,
                global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
                tolerance=0.01,
                warnings=[],
            )
        finally:
            edge_classifier._collect_wire_records = original_collect_wire_records

        self.assertEqual(analysis.cut_edges, (end_edge,))
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual(end_edge.edge_type, CUT_END)

    def test_round_tube_loop_analysis_does_not_handle_rectangular_profile(self) -> None:
        outer_face = FaceRecord(
            FakeCylinderFace(5.0),
            Bounds(20.0, 10.0, 0.0, 25.0, 15.0, 1000.0),
            True,
        )
        inner_face = FaceRecord(
            FakeCylinderFace(3.0),
            Bounds(21.0, 11.0, 0.0, 24.0, 14.0, 1000.0),
            False,
        )

        analysis = _analyze_round_tube_outer_loops(
            (outer_face, inner_face),
            (),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(-25.0, -15.0, 0.0, 25.0, 15.0, 1000.0),
            tolerance=0.01,
            warnings=[],
        )

        self.assertEqual(analysis.cut_edges, ())
        self.assertEqual(analysis.pierce_count, 0)

    def test_round_tube_edge_fallback_counts_without_outer_faces(self) -> None:
        end_edge = EdgeRecord(
            edge=object(),
            length_mm=314.0,
            bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 0.0),
        )
        feature_edge = EdgeRecord(
            edge=object(),
            length_mm=40.0,
            bounds=Bounds(0.0, -50.0, 400.0, 20.0, -50.0, 420.0),
        )
        longitudinal_edge = EdgeRecord(
            edge=object(),
            length_mm=1000.0,
            bounds=Bounds(50.0, 0.0, 0.0, 50.0, 0.0, 1000.0),
        )

        analysis = _analyze_round_tube_edge_fallback(
            (end_edge, feature_edge, longitudinal_edge),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(-50.0, -50.0, 0.0, 50.0, 50.0, 1000.0),
            has_outer_faces=False,
            tolerance=0.01,
        )

        self.assertEqual(analysis.cut_edges, (end_edge, feature_edge))
        self.assertEqual(analysis.pierce_count, 2)
        self.assertEqual(end_edge.edge_type, CUT_END)
        self.assertEqual(feature_edge.edge_type, CUT_FEATURE)

    def test_manual_wall_thickness_override_wins(self) -> None:
        estimate = estimate_wall_thickness(
            (),
            (),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            tolerance=0.01,
            manual_wall_thickness_mm=4.2,
        )

        self.assertEqual(estimate.thickness_mm, 4.2)
        self.assertEqual(estimate.method, "ручной ввод")
        self.assertEqual(estimate.confidence, "высокая")

    def test_debug_edges_csv_lists_each_edge_and_inclusion_reason(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        cut_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            edge_type=CUT_FEATURE,
            reason="CUT_FEATURE inner contour",
        )
        ignored_edge = EdgeRecord(
            edge=object(),
            length_mm=1000.0,
            edge_type=IGNORED_LONGITUDINAL,
            reason="ignored longitudinal tube edge",
        )
        classification = EdgeClassificationResult(
            cut_edges=(cut_edge,),
            all_edge_count=2,
            outer_face_count=1,
            calculated_cut_edges=(cut_edge,),
            ignored_longitudinal_edges=(ignored_edge,),
            edge_records=(cut_edge, ignored_edge),
        )

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "debug_edges.csv"
            write_debug_edges_csv(classification, target, source_file="part.step")
            content = target.read_text(encoding="utf-8-sig")

        self.assertIn("source_file,edge_index,length_mm,edge_type,included_in_cut", content)
        self.assertIn("part.step,1,30.000000,CUT_FEATURE,yes", content)
        self.assertIn("part.step,2,1000.000000,IGNORED_LONGITUDINAL,no", content)

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

    def test_cut_face_analysis_counts_wrapped_feature_as_one_pierce(self) -> None:
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        first_face = FaceRecord(
            face=object(),
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 3.0, 330.0),
            is_outer_longitudinal=False,
        )
        second_face = FaceRecord(
            face=object(),
            bounds=Bounds(50.0, 0.0, 300.0, 80.0, 20.0, 330.0),
            is_outer_longitudinal=False,
        )
        third_face = FaceRecord(
            face=object(),
            bounds=Bounds(20.0, 20.0, 300.0, 50.0, 40.0, 330.0),
            is_outer_longitudinal=False,
        )
        first_outer_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 0.0, 300.0),
            faces=[outer_face, first_face],
        )
        second_outer_edge = EdgeRecord(
            edge=object(),
            length_mm=25.0,
            bounds=Bounds(80.0, 0.0, 300.0, 80.0, 20.0, 300.0),
            faces=[outer_face, second_face],
        )
        third_outer_edge = EdgeRecord(
            edge=object(),
            length_mm=35.0,
            bounds=Bounds(20.0, 40.0, 300.0, 50.0, 40.0, 300.0),
            faces=[outer_face, third_face],
        )
        first_join = EdgeRecord(
            edge=object(),
            length_mm=3.0,
            start_point=(50.0, 0.0, 300.0),
            end_point=(50.0, 3.0, 300.0),
            faces=[first_face, second_face],
        )
        second_join = EdgeRecord(
            edge=object(),
            length_mm=3.0,
            start_point=(50.0, 20.0, 300.0),
            end_point=(50.0, 23.0, 300.0),
            faces=[second_face, third_face],
        )
        records = (
            ThicknessFaceRecord(
                face=first_face,
                area_mm2=90.0,
                thickness_mm=3.0,
                cut_length_mm=30.0,
                edges=(first_outer_edge, first_join),
            ),
            ThicknessFaceRecord(
                face=second_face,
                area_mm2=75.0,
                thickness_mm=3.0,
                cut_length_mm=25.0,
                edges=(second_outer_edge, first_join, second_join),
            ),
            ThicknessFaceRecord(
                face=third_face,
                area_mm2=105.0,
                thickness_mm=3.0,
                cut_length_mm=35.0,
                edges=(third_outer_edge, second_join),
            ),
        )

        analysis = _analyze_cut_faces(
            records,
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            tolerance=0.01,
        )

        self.assertEqual(analysis.cut_edges, (first_outer_edge, second_outer_edge, third_outer_edge))
        self.assertEqual(sum(edge.length_mm for edge in analysis.cut_edges), 90.0)
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual({edge.edge_type for edge in analysis.cut_edges}, {CUT_FEATURE})
        self.assertEqual({edge.cut_component_id for edge in analysis.cut_edges}, {1})

    def test_three_plane_cut_with_internal_middle_face_is_one_pierce(self) -> None:
        # A 3-plane notch where the middle (bottom) plane never reaches the
        # outer skin. The two outer planes are connected only through that
        # internal plane. Grouping must still report a single pierce instead of
        # splitting the cut in two when the internal plane is dropped.
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        left_face = FaceRecord(
            face=object(),
            bounds=Bounds(20.0, 0.0, 300.0, 30.0, 10.0, 330.0),
            is_outer_longitudinal=False,
        )
        bottom_face = FaceRecord(
            face=object(),
            bounds=Bounds(30.0, 10.0, 300.0, 60.0, 13.0, 330.0),
            is_outer_longitudinal=False,
        )
        right_face = FaceRecord(
            face=object(),
            bounds=Bounds(60.0, 0.0, 300.0, 70.0, 10.0, 330.0),
            is_outer_longitudinal=False,
        )
        left_outer_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 300.0, 30.0, 0.0, 300.0),
            faces=[outer_face, left_face],
        )
        right_outer_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(60.0, 0.0, 300.0, 70.0, 0.0, 300.0),
            faces=[outer_face, right_face],
        )
        left_join = EdgeRecord(
            edge=object(),
            length_mm=3.0,
            start_point=(30.0, 10.0, 300.0),
            end_point=(30.0, 10.0, 330.0),
            faces=[left_face, bottom_face],
        )
        right_join = EdgeRecord(
            edge=object(),
            length_mm=3.0,
            start_point=(60.0, 10.0, 300.0),
            end_point=(60.0, 10.0, 330.0),
            faces=[bottom_face, right_face],
        )
        records = (
            ThicknessFaceRecord(
                face=left_face,
                area_mm2=90.0,
                thickness_mm=3.0,
                cut_length_mm=30.0,
                edges=(left_outer_edge, left_join),
            ),
            ThicknessFaceRecord(
                face=bottom_face,
                area_mm2=90.0,
                thickness_mm=3.0,
                cut_length_mm=30.0,
                edges=(left_join, right_join),
            ),
            ThicknessFaceRecord(
                face=right_face,
                area_mm2=90.0,
                thickness_mm=3.0,
                cut_length_mm=30.0,
                edges=(right_outer_edge, right_join),
            ),
        )

        analysis = _analyze_cut_faces(
            records,
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            tolerance=0.01,
        )

        # The internal bottom face carries no outer edge, so only the two outer
        # planes contribute to the cut length, but both belong to one pierce.
        self.assertEqual(analysis.cut_edges, (left_outer_edge, right_outer_edge))
        self.assertEqual(sum(edge.length_mm for edge in analysis.cut_edges), 60.0)
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual({edge.cut_component_id for edge in analysis.cut_edges}, {1})

    def test_two_separate_cuts_remain_two_pierces(self) -> None:
        # Guard against over-merging: two thickness faces that do not touch must
        # stay two pierces.
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=True,
        )
        first_face = FaceRecord(
            face=object(),
            bounds=Bounds(20.0, 0.0, 200.0, 30.0, 3.0, 230.0),
            is_outer_longitudinal=False,
        )
        second_face = FaceRecord(
            face=object(),
            bounds=Bounds(50.0, 0.0, 600.0, 60.0, 3.0, 630.0),
            is_outer_longitudinal=False,
        )
        first_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 200.0, 30.0, 0.0, 200.0),
            faces=[outer_face, first_face],
        )
        second_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(50.0, 0.0, 600.0, 60.0, 0.0, 600.0),
            faces=[outer_face, second_face],
        )
        records = (
            ThicknessFaceRecord(
                face=first_face,
                area_mm2=90.0,
                thickness_mm=3.0,
                cut_length_mm=30.0,
                edges=(first_edge,),
            ),
            ThicknessFaceRecord(
                face=second_face,
                area_mm2=90.0,
                thickness_mm=3.0,
                cut_length_mm=30.0,
                edges=(second_edge,),
            ),
        )

        analysis = _analyze_cut_faces(
            records,
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            tolerance=0.01,
        )

        self.assertEqual(analysis.pierce_count, 2)
        self.assertEqual({edge.cut_component_id for edge in analysis.cut_edges}, {1, 2})

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
