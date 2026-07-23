from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

from cad.analyzer import GeometryAnalysisResult, analyze_shape
from cad.edge_classifier import (
    Bounds,
    CUT_END,
    CUT_FEATURE,
    CutFaceAnalysis,
    IGNORED_LONGITUDINAL,
    IGNORED_PLANE_RADIUS,
    IGNORED_PROFILE,
    UNCERTAIN,
    EdgeRecord,
    EdgeClassificationResult,
    FaceRecord,
    ThicknessFaceRecord,
    _add_diagonal_profile_side_holes,
    _analyze_complex_profile_contour_fallback,
    _analyze_cut_faces,
    _analyze_round_tube_bspline_bbox_fallback,
    _analyze_round_tube_edge_fallback,
    _analyze_round_tube_outer_loops,
    _analyze_shell_open_boundary_fallback,
    _classify_edge_groups,
    _collect_thickness_outer_cut_edges,
    _count_cut_edge_components,
    _count_thickness_face_components,
    _estimate_face_thickness,
    _is_cut_edge_candidate,
    _is_outer_longitudinal_face,
    _is_thickness_face_candidate,
    _prefer_cut_edge_components_for_cut_faces,
    _round_bbox_should_use_compact_mixed_features,
    _tolerance_from_summary,
    WireRecord,
    estimate_wall_thickness,
)
from cad.debug_edges import write_debug_edges_csv
from cad.importer import (
    CadImportError,
    CadImporter,
    IGES_SURFACE_ONLY_SOLID_HEAL_ENTITY_LIMIT,
    IgesEntitySummary,
    _heal_surface_only_iges_shape,
    _sanitize_iges_ascii_bytes,
    _sew_iges_shape,
    scan_iges_entity_summary,
)
from cad.inventor_converter import InventorConversionError, convert_iges_to_step
from cad.pierce_counter import _count_components_from_pairs
from cad.profile_detector import detect_profile_from_dimensions
from cad.shape_summary import ShapeSummary
from cad.step_text_analyzer import analyze_step_round_tube_text
from cad.supported_formats import collect_supported_files, is_supported_cad_file
from core.file_job import (
    explicit_quantity_from_filename,
    has_explicit_quantity_in_filename,
    parse_quantity_from_filename,
)
from core.file_queue import FileQueue
from core import dev_reloader
from core.dev_reloader import reload_calculation_core
from core.specification_importer import (
    SpecificationItem,
    load_quantity_specification,
    normalize_spec_name,
    quantity_for_file,
)


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


def _openpyxl_or_skip(test_case: unittest.TestCase):
    try:
        import openpyxl
    except ImportError:
        test_case.skipTest("openpyxl is not installed in this Python environment")
    return openpyxl


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

    def test_explicit_quantity_from_filename_marks_missing_quantity(self) -> None:
        self.assertEqual(explicit_quantity_from_filename("Корпус бок Д2_3шт.igs"), 3)
        self.assertIsNone(explicit_quantity_from_filename("Корпус бок Д2.igs"))
        self.assertTrue(has_explicit_quantity_in_filename("Корпус бок Д2_3шт.igs"))
        self.assertFalse(has_explicit_quantity_in_filename("Корпус бок Д2.igs"))

    def test_quantity_specification_matches_file_stem(self) -> None:
        items = {
            normalize_spec_name("Корпус центр Д2"): SpecificationItem(
                name="Корпус центр Д2",
                quantity=2,
                row=12,
            )
        }

        item = quantity_for_file("Корпус центр Д2.IGS", items)

        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 2)

    def test_quantity_specification_reads_named_columns(self) -> None:
        openpyxl = _openpyxl_or_skip(self)
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "spec.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["", "Название", "Кол-во", "Заготовка"])
            sheet.append(["", "Корпус центр Д2", 2, "труба 60х60х3"])
            workbook.save(path)

            items = load_quantity_specification(path)

        item = quantity_for_file("Корпус центр Д2.IGS", items)
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 2)

    def test_quantity_specification_guesses_columns_without_headers(self) -> None:
        openpyxl = _openpyxl_or_skip(self)
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "spec.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["Корпус бок Д2", 2, "труба 60х60х3"])
            sheet.append(["Корпус центр Д2", 2, "труба 60х60х3"])
            workbook.save(path)

            items = load_quantity_specification(path)

        item = quantity_for_file("Корпус бок Д2.IGS", items)
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 2)

    def test_dev_reloader_adds_source_root_and_skips_missing_modules(self) -> None:
        from tempfile import TemporaryDirectory

        original_modules = dev_reloader.CALCULATION_MODULES
        try:
            with TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "cad").mkdir()
                (root / "cad" / "__init__.py").write_text("", encoding="utf-8")
                (root / "cad" / "profile_detector.py").write_text(
                    "VALUE = 42\n",
                    encoding="utf-8",
                )
                dev_reloader.CALCULATION_MODULES = (
                    "cad.profile_detector",
                    "cad.missing_debug_module",
                )

                result = reload_calculation_core(root)

            self.assertEqual(result.modules, ("cad.profile_detector",))
            self.assertEqual(result.skipped, ("cad.missing_debug_module",))
        finally:
            dev_reloader.CALCULATION_MODULES = original_modules


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

    def test_iges_ascii_sanitizer_preserves_fixed_width_records(self) -> None:
        content = b"1H,,9H\xf1\xf2.1_1\xf8\xf2.,15HSolidWorks 2023"
        raw = content.ljust(72) + b"G      1\r\n"

        sanitized = _sanitize_iges_ascii_bytes(raw)
        first_line = sanitized.rstrip(b"\r\n")

        self.assertEqual(len(first_line), 80)
        self.assertTrue(sanitized.isascii())
        self.assertEqual(chr(first_line[72]), "G")
        self.assertIn(b"__.1_1__", sanitized)

    def test_iges_prescan_detects_surface_only_model(self) -> None:
        from tempfile import TemporaryDirectory

        def directory_line(entity_type: int, seq: int) -> bytes:
            prefix = (
                f"{entity_type:8d}{1:8d}{0:8d}{0:8d}{0:8d}"
                f"{'':32}"
            )
            return f"{prefix}D{seq:7d}\r\n".encode("ascii")

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "surface.igs"
            path.write_bytes(
                b"surface".ljust(72) + b"S      1\r\n"
                + directory_line(144, 1)
                + directory_line(144, 2)
                + directory_line(128, 3)
                + directory_line(128, 4)
                + b"S      1G      1D      4P      0T      1\r\n"
            )

            summary = scan_iges_entity_summary(path)

        self.assertEqual(summary.entity_count, 2)
        self.assertTrue(summary.is_surface_only_model)
        self.assertFalse(summary.has_brep_topology)

    def test_iges_prescan_detects_brep_topology(self) -> None:
        from tempfile import TemporaryDirectory

        def directory_line(entity_type: int, seq: int) -> bytes:
            prefix = (
                f"{entity_type:8d}{1:8d}{0:8d}{0:8d}{0:8d}"
                f"{'':32}"
            )
            return f"{prefix}D{seq:7d}\r\n".encode("ascii")

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "solid.igs"
            path.write_bytes(
                b"solid".ljust(72) + b"S      1\r\n"
                + directory_line(186, 1)
                + directory_line(186, 2)
                + directory_line(144, 3)
                + directory_line(144, 4)
                + b"S      1G      1D      4P      0T      1\r\n"
            )

            summary = scan_iges_entity_summary(path)

        self.assertEqual(summary.entity_count, 2)
        self.assertTrue(summary.has_brep_topology)
        self.assertFalse(summary.is_surface_only_model)

    def test_surface_only_iges_attempts_solid_healing(self) -> None:
        import cad.importer as importer_module
        from tempfile import TemporaryDirectory

        class FakeShape:
            def IsNull(self) -> bool:
                return False

        class FakeSolid:
            def IsNull(self) -> bool:
                return False

        original_read_once = CadImporter._read_iges_once
        original_heal = importer_module._heal_surface_only_iges_shape
        heal_calls: list[object] = []
        shape = FakeShape()
        solid = FakeSolid()

        try:
            CadImporter._read_iges_once = staticmethod(lambda path: shape)
            importer_module._heal_surface_only_iges_shape = (
                lambda candidate: heal_calls.append(candidate) or solid
            )
            with TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "surface.igs"
                path.write_text("", encoding="ascii")
                result = CadImporter._read_iges(
                    path,
                    iges_summary=IgesEntitySummary(
                        entity_count=1,
                        entity_counts={144: 1},
                    ),
                )
        finally:
            CadImporter._read_iges_once = original_read_once
            importer_module._heal_surface_only_iges_shape = original_heal

        self.assertIs(result, solid)
        self.assertEqual(heal_calls, [shape])

    def test_heavy_surface_only_iges_skips_solid_healing(self) -> None:
        import cad.importer as importer_module
        from tempfile import TemporaryDirectory

        class FakeShape:
            def IsNull(self) -> bool:
                return False

        class FakeSewedShape:
            def IsNull(self) -> bool:
                return False

        original_read_once = CadImporter._read_iges_once
        original_heal = importer_module._heal_surface_only_iges_shape
        original_sew = importer_module._sew_iges_shape
        heal_calls: list[object] = []
        sew_calls: list[object] = []
        shape = FakeShape()
        sewed_shape = FakeSewedShape()

        try:
            CadImporter._read_iges_once = staticmethod(lambda path: shape)
            importer_module._heal_surface_only_iges_shape = (
                lambda candidate: heal_calls.append(candidate) or candidate
            )
            importer_module._sew_iges_shape = (
                lambda candidate: sew_calls.append(candidate) or sewed_shape
            )
            with TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "heavy_surface.igs"
                path.write_text("", encoding="ascii")
                result = CadImporter._read_iges(
                    path,
                    iges_summary=IgesEntitySummary(
                        entity_count=IGES_SURFACE_ONLY_SOLID_HEAL_ENTITY_LIMIT + 1,
                        entity_counts={144: IGES_SURFACE_ONLY_SOLID_HEAL_ENTITY_LIMIT + 1},
                    ),
                )
        finally:
            CadImporter._read_iges_once = original_read_once
            importer_module._heal_surface_only_iges_shape = original_heal
            importer_module._sew_iges_shape = original_sew

        self.assertIs(result, sewed_shape)
        self.assertEqual(heal_calls, [])
        self.assertEqual(sew_calls, [shape])

    def test_forced_heavy_surface_only_iges_attempts_solid_healing(self) -> None:
        import cad.importer as importer_module
        from tempfile import TemporaryDirectory

        class FakeShape:
            def IsNull(self) -> bool:
                return False

        class FakeSolid:
            def IsNull(self) -> bool:
                return False

        original_read_once = CadImporter._read_iges_once
        original_heal = importer_module._heal_surface_only_iges_shape
        original_sew = importer_module._sew_iges_shape
        heal_calls: list[object] = []
        sew_calls: list[object] = []
        shape = FakeShape()
        solid = FakeSolid()

        try:
            CadImporter._read_iges_once = staticmethod(lambda path: shape)
            importer_module._heal_surface_only_iges_shape = (
                lambda candidate: heal_calls.append(candidate) or solid
            )
            importer_module._sew_iges_shape = (
                lambda candidate: sew_calls.append(candidate) or candidate
            )
            with TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "heavy_surface.igs"
                path.write_text("", encoding="ascii")
                result = CadImporter._read_iges(
                    path,
                    iges_summary=IgesEntitySummary(
                        entity_count=IGES_SURFACE_ONLY_SOLID_HEAL_ENTITY_LIMIT + 1,
                        entity_counts={144: IGES_SURFACE_ONLY_SOLID_HEAL_ENTITY_LIMIT + 1},
                    ),
                    force_solid_healing=True,
                )
        finally:
            CadImporter._read_iges_once = original_read_once
            importer_module._heal_surface_only_iges_shape = original_heal
            importer_module._sew_iges_shape = original_sew

        self.assertIs(result, solid)
        self.assertEqual(heal_calls, [shape])
        self.assertEqual(sew_calls, [])

    def test_surface_only_iges_healing_falls_back_to_original_shape(self) -> None:
        sentinel = object()
        self.assertIs(_heal_surface_only_iges_shape(sentinel), sentinel)

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

    def test_inventor_converter_rejects_non_iges_files(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "part.step"
            path.write_text("", encoding="utf-8")

            with self.assertRaises(InventorConversionError):
                convert_iges_to_step(path, temp_dir)

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

    def test_surface_only_iges_skips_automatic_sheet_analysis(self) -> None:
        import cad.analyzer as analyzer_module
        from cad.sheet_analyzer import SheetAnalysisResult

        calls = {"sheet": 0}
        original_sheet = analyzer_module.analyze_sheet_shape
        original_classify = analyzer_module.classify_cut_edges

        def fake_sheet_analysis(*args, **kwargs):
            calls["sheet"] += 1
            return SheetAnalysisResult(
                width_mm=1500.0,
                height_mm=100.0,
                thickness_mm=3.0,
                thickness_axis="X",
                cut_length_mm=3200.0,
                pierce_count=1,
                contours=(),
                segments=(),
            )

        def fake_classification(*args, **kwargs):
            return EdgeClassificationResult(
                cut_edges=(),
                all_edge_count=0,
                outer_face_count=0,
            )

        analyzer_module.analyze_sheet_shape = fake_sheet_analysis
        analyzer_module.classify_cut_edges = fake_classification
        try:
            result = analyze_shape(
                object(),
                summary=ShapeSummary(
                    diagonal_mm=1503.3,
                    size_x_mm=3.0,
                    size_y_mm=100.0,
                    size_z_mm=1500.0,
                    face_count=281,
                    edge_count=2002,
                ),
                file_format="IGES",
                import_warnings=(IgesEntitySummary(entity_count=1, entity_counts={144: 1}).warning(),),
            )
        finally:
            analyzer_module.analyze_sheet_shape = original_sheet
            analyzer_module.classify_cut_edges = original_classify

        self.assertEqual(calls["sheet"], 0)
        self.assertNotEqual(result.profile_hint, "листовая деталь")
        self.assertIsNone(result.sheet_analysis)
        self.assertTrue(
            any("Листовой анализ пропущен" in warning for warning in result.warnings)
        )

    def test_profile_size_uses_cross_face_when_bbox_contains_diagonal_length(self) -> None:
        import cad.analyzer as analyzer_module

        original_classify = analyzer_module.classify_cut_edges

        def fake_classification(*args, **kwargs):
            return EdgeClassificationResult(
                cut_edges=(),
                all_edge_count=0,
                outer_face_count=2,
                face_records=(
                    FaceRecord(
                        object(),
                        Bounds(-1707.5, -50.0, -181.1, -1600.4, 50.0, -175.1),
                        False,
                    ),
                    FaceRecord(
                        object(),
                        Bounds(-1704.7, 50.0, -1389.0, -1091.1, 50.0, -168.2),
                        True,
                    ),
                ),
            )

        analyzer_module.classify_cut_edges = fake_classification
        try:
            result = analyze_shape(
                object(),
                summary=ShapeSummary(
                    diagonal_mm=1377.4,
                    size_x_mm=618.247665,
                    size_y_mm=100.0,
                    size_z_mm=1220.880616,
                    face_count=296,
                    edge_count=3789,
                ),
                file_format="IGES",
                import_warnings=(IgesEntitySummary(entity_count=1, entity_counts={144: 1}).warning(),),
            )
        finally:
            analyzer_module.classify_cut_edges = original_classify

        self.assertEqual(result.width_mm, 100.0)
        self.assertEqual(result.height_mm, 100.0)
        self.assertEqual(result.profile_hint, "Квадратная профильная труба")
        self.assertTrue(
            any("Сечение трубы уточнено" in warning for warning in result.warnings)
        )

    def test_profile_size_uses_local_square_face_for_slanted_surface_tube(self) -> None:
        import cad.analyzer as analyzer_module

        original_classify = analyzer_module.classify_cut_edges

        def fake_classification(*args, **kwargs):
            return EdgeClassificationResult(
                cut_edges=(),
                all_edge_count=0,
                outer_face_count=2,
                face_records=(
                    FaceRecord(
                        object(),
                        Bounds(0.0, 0.0, 0.0, 15.0, 0.0, 17.885),
                        False,
                    ),
                    FaceRecord(
                        object(),
                        Bounds(0.0, 0.0, 0.0, 84.111, 111.422, 1.5),
                        True,
                    ),
                ),
            )

        analyzer_module.classify_cut_edges = fake_classification
        try:
            result = analyze_shape(
                object(),
                summary=ShapeSummary(
                    diagonal_mm=112.8,
                    size_x_mm=84.111,
                    size_y_mm=111.422,
                    size_z_mm=17.418,
                    face_count=29,
                    edge_count=684,
                ),
                file_format="IGES",
            )
        finally:
            analyzer_module.classify_cut_edges = original_classify

        self.assertEqual(result.width_mm, 15.0)
        self.assertEqual(result.height_mm, 15.0)
        self.assertEqual(result.profile_hint, "Квадратная профильная труба")
        self.assertTrue(
            any("Сечение трубы уточнено" in warning for warning in result.warnings)
        )

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

    def test_summary_tolerance_keeps_small_spline_segments(self) -> None:
        summary = ShapeSummary(
            diagonal_mm=3912.72,
            size_x_mm=103.2,
            size_y_mm=103.2,
            size_z_mm=3910.0,
            face_count=283,
            edge_count=4229,
        )
        tolerance = _tolerance_from_summary(summary)
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 50.0, 0.0, 103.2, 50.0, 3910.0),
            is_outer_longitudinal=True,
        )
        short_spline_segment = EdgeRecord(
            edge=object(),
            length_mm=0.490877,
            bounds=Bounds(20.0, 50.0, 100.0, 20.4, 50.0, 100.2),
            faces=[outer_face],
            wire_roles={"inner_wire"},
        )

        groups = _classify_edge_groups(
            (short_spline_segment,),
            axis="Z",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -50.0, 0.0, 103.2, 50.0, 3910.0),
            has_outer_faces=True,
            tolerance=tolerance,
        )

        self.assertLess(tolerance, short_spline_segment.length_mm)
        self.assertEqual(groups.calculated_cut_edges, (short_spline_segment,))
        self.assertEqual(short_spline_segment.edge_type, CUT_FEATURE)

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

        long_tube_faces = (
            FaceRecord(
                FakeCylinderFace(17.5),
                Bounds(-35.0, -33.65, 0.0, 35.0, 33.65, 3910.0),
                True,
            ),
            FaceRecord(
                FakeCylinderFace(15.0),
                Bounds(-30.0, -28.65, 0.0, 30.0, 28.65, 3910.0),
                False,
            ),
        )
        long_tube_estimate = estimate_wall_thickness(
            long_tube_faces,
            (),
            axis="Z",
            length_mm=3910.0,
            global_bounds=Bounds(-35.0, -33.65, 0.0, 35.0, 33.65, 3910.0),
            tolerance=3.91,
        )

        self.assertEqual(long_tube_estimate.thickness_mm, 2.5)
        self.assertEqual(long_tube_estimate.method, "цилиндры R_outer - R_inner")

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
            global_bounds=Bounds(0.0, -133.0, -66.5, 3910.0, 133.0, 72.821),
            has_outer_faces=False,
            tolerance=0.01,
        )
        estimate = estimate_wall_thickness(
            faces,
            edges,
            axis="X",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -133.0, -66.5, 3910.0, 133.0, 72.821),
            tolerance=0.01,
        )

        self.assertEqual(analysis.pierce_count, 42)
        self.assertEqual(len(analysis.cut_edges), 84)
        self.assertAlmostEqual(analysis.outer_radius_mm * 2.0, 133.0)
        self.assertAlmostEqual(sum(edge.length_mm for edge in analysis.cut_edges), 8197.137420)
        self.assertAlmostEqual(estimate.thickness_mm, 6.0)
        self.assertEqual(estimate.method, "bbox круглой BSpline-трубы R_outer - R_inner")

        edges_with_outer_flag = tuple(
            EdgeRecord(object(), edge.length_mm, bounds=edge.bounds)
            for edge in edges
        )
        analysis_with_outer_flag = _analyze_round_tube_bspline_bbox_fallback(
            faces,
            edges_with_outer_flag,
            axis="X",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -133.0, -66.5, 3910.0, 133.0, 72.821),
            has_outer_faces=True,
            tolerance=0.01,
        )

        self.assertEqual(analysis_with_outer_flag.pierce_count, 42)
        self.assertAlmostEqual(analysis_with_outer_flag.outer_radius_mm * 2.0, 133.0)

        production_tolerance = 3910.0 * 0.001
        high_tolerance_edges = tuple(
            EdgeRecord(object(), edge.length_mm, bounds=edge.bounds)
            for edge in edges
        )
        high_tolerance_analysis = _analyze_round_tube_bspline_bbox_fallback(
            faces,
            high_tolerance_edges,
            axis="X",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -133.0, -66.5, 3910.0, 133.0, 72.821),
            has_outer_faces=False,
            tolerance=production_tolerance,
        )
        high_tolerance_estimate = estimate_wall_thickness(
            faces,
            high_tolerance_edges,
            axis="X",
            length_mm=3910.0,
            global_bounds=Bounds(0.0, -133.0, -66.5, 3910.0, 133.0, 72.821),
            tolerance=production_tolerance,
        )

        self.assertEqual(high_tolerance_analysis.pierce_count, 42)
        self.assertEqual(len(high_tolerance_analysis.cut_edges), 84)
        self.assertAlmostEqual(
            sum(edge.length_mm for edge in high_tolerance_analysis.cut_edges),
            8197.137420,
        )
        self.assertAlmostEqual(high_tolerance_estimate.thickness_mm, 6.0)
        self.assertAlmostEqual(
            sum(edge.length_mm for edge in analysis_with_outer_flag.cut_edges),
            8197.137420,
        )

    def test_square_profile_tube_does_not_use_round_bspline_bbox_fallback(self) -> None:
        faces = (
            FaceRecord(object(), Bounds(-255.0, 1206.0, -440.0, -255.0, 1254.0, -60.0), True),
            FaceRecord(object(), Bounds(-309.0, 1200.0, -440.0, -261.0, 1200.0, -60.0), True),
            FaceRecord(object(), Bounds(-315.0, 1206.0, -440.0, -315.0, 1254.0, -60.0), True),
            FaceRecord(object(), Bounds(-309.0, 1260.0, -440.0, -261.0, 1260.0, -60.0), True),
            FaceRecord(object(), Bounds(-315.0, 1200.0, -440.0, -309.0, 1206.0, -60.0), True),
            FaceRecord(object(), Bounds(-261.0, 1200.0, -440.0, -255.0, 1206.0, -60.0), True),
            FaceRecord(object(), Bounds(-315.0, 1254.0, -440.0, -309.0, 1260.0, -60.0), True),
            FaceRecord(object(), Bounds(-261.0, 1254.0, -440.0, -255.0, 1260.0, -60.0), True),
            FaceRecord(object(), Bounds(-258.0, 1206.0, -440.0, -258.0, 1254.0, -60.0), False),
            FaceRecord(object(), Bounds(-309.0, 1203.0, -440.0, -261.0, 1203.0, -60.0), False),
        )
        end_edge = EdgeRecord(
            object(),
            670.248,
            bounds=Bounds(-315.0, 1200.0, -440.0, -255.0, 1260.0, -440.0),
        )
        feature_edge = EdgeRecord(
            object(),
            15.708,
            bounds=Bounds(-315.0, 1227.5, -427.5, -315.0, 1232.5, -422.5),
        )

        analysis = _analyze_round_tube_bspline_bbox_fallback(
            faces,
            (end_edge, feature_edge),
            axis="Z",
            length_mm=380.0,
            global_bounds=Bounds(-315.0, 1200.0, -440.0, -255.0, 1260.0, -60.0),
            has_outer_faces=True,
            tolerance=0.01,
        )

        self.assertEqual(analysis.cut_edges, ())
        self.assertEqual(analysis.pierce_count, 0)

    def test_diagonal_profile_side_hole_fallback_adds_missing_pierces(self) -> None:
        base_edges = tuple(
            EdgeRecord(
                object(),
                15.71,
                bounds=Bounds(float(index), 900.0, 0.0, float(index) + 1.0, 901.0, 0.0),
                edge_type=CUT_FEATURE,
                cut_component_id=index + 1,
            )
            for index in range(8)
        )

        def loop_edges(name: str, cx: float, cy: float, cz: float, z_span: float) -> tuple[EdgeRecord, ...]:
            vertices = [FakeVertex(f"{name}-{index}") for index in range(4)]
            bounds = Bounds(cx - 2.8, cy - 2.8, cz - z_span / 2.0, cx + 2.8, cy + 2.8, cz + z_span / 2.0)
            return tuple(
                EdgeRecord(
                    object(),
                    9.354,
                    bounds=bounds,
                    start_vertex=vertices[index],
                    end_vertex=vertices[(index + 1) % 4],
                    wire_roles={"inner_wire", "outer_wire_cut"},
                    edge_type=UNCERTAIN,
                    reason="edge is not on outer tube shell",
                )
                for index in range(4)
            )

        side_holes = tuple(
            edge
            for component in (
                loop_edges("side-1", 44.65, 1188.23, -30.0, 5.0),
                loop_edges("side-2", 108.29, 1124.59, -30.0, 5.0),
                loop_edges("side-3", 179.59, 1053.29, -30.0, 5.0),
                loop_edges("side-4", 243.23, 989.65, -30.0, 5.0),
            )
            for edge in component
        )
        inner_thickness_loops = loop_edges("inner-noise", 123.78, 1068.78, -57.0, 0.001)
        large_end_noise = tuple(
            EdgeRecord(
                object(),
                64.7,
                bounds=Bounds(255.0, 895.14, -60.0, 315.0, 920.0, 0.0),
                start_vertex=FakeVertex(f"large-{index}"),
                end_vertex=FakeVertex(f"large-{(index + 1) % 4}"),
                wire_roles={"outer_wire_cut"},
                edge_type=UNCERTAIN,
                reason="edge is not on outer tube shell",
            )
            for index in range(4)
        )

        analysis = _add_diagonal_profile_side_holes(
            CutFaceAnalysis(cut_edges=base_edges, pierce_count=8),
            (*base_edges, *side_holes, *inner_thickness_loops, *large_end_noise),
            axis="Y",
            global_bounds=Bounds(-51.610173, 893.389827, -60.0, 315.0, 1260.0, 0.0),
            tolerance=0.01,
        )

        self.assertEqual(analysis.pierce_count, 12)
        self.assertEqual(len(analysis.cut_edges), len(base_edges) + len(side_holes))
        self.assertTrue(all(edge.edge_type == CUT_FEATURE for edge in side_holes))
        self.assertTrue(all(edge.edge_type == UNCERTAIN for edge in inner_thickness_loops))

    def test_round_split_surface_tube_uses_half_cylinder_bbox(self) -> None:
        faces = (
            FaceRecord(object(), Bounds(-51.0, 0.0, -51.0, 0.0, 1000.0, 51.0), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -51.0, 51.0, 1000.0, 51.0), False),
            FaceRecord(object(), Bounds(-48.0, 0.0, -48.0, 0.0, 1000.0, 48.0), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -48.0, 48.0, 1000.0, 48.0), False),
        )
        min_end_outer = EdgeRecord(
            object(),
            160.221,
            bounds=Bounds(-51.0, 0.0, -51.0, 0.0, 0.0, 51.0),
            wire_roles={"outer_wire_cut"},
        )
        min_end_inner = EdgeRecord(
            object(),
            150.796,
            bounds=Bounds(-48.0, 0.0, -48.0, 0.0, 0.0, 48.0),
            wire_roles={"inner_wire", "outer_wire_cut"},
        )
        max_end_outer = EdgeRecord(
            object(),
            160.221,
            bounds=Bounds(0.0, 997.0, -51.0, 51.0, 1000.0, 0.0),
            wire_roles={"outer_wire_cut"},
        )
        feature_outer = EdgeRecord(
            object(),
            42.0,
            bounds=Bounds(36.0, 450.0, 36.0, 51.0, 455.0, 51.0),
            wire_roles={"outer_wire_cut"},
        )
        longitudinal = EdgeRecord(
            object(),
            1000.0,
            bounds=Bounds(51.0, 0.0, 0.0, 51.0, 1000.0, 0.0),
        )

        analysis = _analyze_round_tube_bspline_bbox_fallback(
            faces,
            (min_end_outer, min_end_inner, max_end_outer, feature_outer, longitudinal),
            axis="Y",
            length_mm=1000.0,
            global_bounds=Bounds(-51.0, 0.0, -51.0, 51.0, 1000.0, 51.0),
            has_outer_faces=False,
            tolerance=0.01,
        )
        estimate = estimate_wall_thickness(
            faces,
            (),
            axis="Y",
            length_mm=1000.0,
            global_bounds=Bounds(-51.0, 0.0, -51.0, 51.0, 1000.0, 51.0),
            tolerance=0.01,
        )

        self.assertEqual(analysis.cut_edges, (min_end_outer, max_end_outer, feature_outer))
        self.assertEqual(analysis.pierce_count, 3)
        self.assertAlmostEqual(analysis.outer_radius_mm * 2.0, 102.0)
        self.assertEqual(min_end_outer.edge_type, CUT_END)
        self.assertEqual(max_end_outer.edge_type, CUT_END)
        self.assertEqual(feature_outer.edge_type, CUT_FEATURE)
        self.assertAlmostEqual(estimate.thickness_mm, 3.0)
        self.assertEqual(estimate.method, "bbox круглой BSpline-трубы R_outer - R_inner")

    def test_round_mixed_inner_wire_holes_prefer_full_contours(self) -> None:
        faces = (
            FaceRecord(object(), Bounds(0.0, -66.5, -66.5, 1000.0, 0.0, 66.5), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -66.5, 1000.0, 66.5, 66.5), False),
            FaceRecord(object(), Bounds(0.0, -60.5, -60.5, 1000.0, 0.0, 60.5), False),
            FaceRecord(object(), Bounds(0.0, 0.0, -60.5, 1000.0, 60.5, 60.5), False),
        )
        end_min = EdgeRecord(object(), 208.916, bounds=Bounds(0.0, -66.5, -66.5, 0.0, 0.0, 66.5))
        end_max = EdgeRecord(object(), 208.916, bounds=Bounds(1000.0, 0.0, -66.5, 1000.0, 66.5, 66.5))
        outer_noise = EdgeRecord(
            object(),
            6.0,
            bounds=Bounds(200.0, 5.0, 60.5, 210.0, 7.0, 66.5),
            wire_roles={"outer_wire_cut"},
        )
        top_a = EdgeRecord(
            object(),
            93.1,
            bounds=Bounds(200.0, 16.0, 35.0, 230.0, 56.0, 66.0),
            wire_roles={"inner_wire"},
        )
        top_b = EdgeRecord(
            object(),
            93.1,
            bounds=Bounds(230.0, 16.0, 35.0, 260.0, 56.0, 66.0),
            wire_roles={"inner_wire"},
        )
        bottom_a = EdgeRecord(
            object(),
            93.1,
            bounds=Bounds(200.0, -56.0, 35.0, 230.0, -16.0, 66.0),
            wire_roles={"inner_wire"},
        )
        bottom_b = EdgeRecord(
            object(),
            93.1,
            bounds=Bounds(230.0, -56.0, 35.0, 260.0, -16.0, 66.0),
            wire_roles={"inner_wire"},
        )

        analysis = _analyze_round_tube_bspline_bbox_fallback(
            faces,
            (end_min, end_max, outer_noise, top_a, top_b, bottom_a, bottom_b),
            axis="X",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, -66.5, -66.5, 1000.0, 66.5, 66.5),
            has_outer_faces=True,
            tolerance=0.01,
        )

        self.assertEqual(analysis.pierce_count, 4)
        self.assertAlmostEqual(sum(edge.length_mm for edge in analysis.cut_edges), 790.232)
        self.assertEqual(outer_noise.edge_type, "")
        self.assertEqual(top_a.edge_type, CUT_FEATURE)
        self.assertEqual(bottom_a.edge_type, CUT_FEATURE)

    def test_step_round_tube_text_analysis_keeps_slanted_end_length(self) -> None:
        from tempfile import TemporaryDirectory

        step_text = """
ISO-10303-21;
DATA;
#21 = EDGE_CURVE('',#22,#22,#24,.T.);
#24 = SURFACE_CURVE('',#25,(#30),.PCURVE_S1.);
#30 = PCURVE('',#31,#36);
#31 = CYLINDRICAL_SURFACE('',#32,21.15);
#36 = DEFINITIONAL_REPRESENTATION('',(#37),#47);
#37 = B_SPLINE_CURVE_WITH_KNOTS('',8,(#38,#39,#40,#41,#42,#43,#44,#45,#46),
  .UNSPECIFIED.,.F.,.F.,(9,9),(0.,6.28318530718),.PIECEWISE_BEZIER_KNOTS.);
#38 = CARTESIAN_POINT('',(-6.28318530718,-33.84137342829));
#39 = CARTESIAN_POINT('',(-5.497787143782,-33.84137342829));
#40 = CARTESIAN_POINT('',(-4.712388980386,-39.87681422705));
#41 = CARTESIAN_POINT('',(-3.92699081698,-51.69378024837));
#42 = CARTESIAN_POINT('',(-3.14159265362,-62.83701688579));
#43 = CARTESIAN_POINT('',(-2.356194490184,-51.69378024854));
#44 = CARTESIAN_POINT('',(-1.570796326798,-39.87681422705));
#45 = CARTESIAN_POINT('',(-0.785398163397,-33.84137342829));
#46 = CARTESIAN_POINT('',(0.,-33.84137342829));
#82 = EDGE_CURVE('',#62,#62,#83,.T.);
#83 = SURFACE_CURVE('',#84,(#89),.PCURVE_S1.);
#89 = PCURVE('',#31,#90);
#90 = DEFINITIONAL_REPRESENTATION('',(#91),#94);
#91 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#92,#93),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,6.28318530718),.PIECEWISE_BEZIER_KNOTS.);
#92 = CARTESIAN_POINT('',(0.,-4.52192E+03));
#93 = CARTESIAN_POINT('',(-6.28318530718,-4.52192E+03));
#132 = CYLINDRICAL_SURFACE('',#133,18.35);
ENDSEC;
END-ISO-10303-21;
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "tube.stp"
            path.write_text(step_text, encoding="utf-8")
            analysis = analyze_step_round_tube_text(path)

        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertAlmostEqual(analysis.outer_diameter_mm, 42.3)
        self.assertAlmostEqual(analysis.wall_thickness_mm, 2.8)
        self.assertAlmostEqual(analysis.length_mm, 4521.92)
        self.assertEqual(analysis.pierce_count, 2)
        self.assertAlmostEqual(analysis.cut_length_mm, 271.028, places=3)

    def test_step_round_tube_text_analysis_uses_long_seam_radii_for_profile(self) -> None:
        from tempfile import TemporaryDirectory

        step_text = """
ISO-10303-21;
DATA;
#21 = EDGE_CURVE('',#22,#24,#26,.T.);
#26 = SEAM_CURVE('',#27,(#31),.PCURVE_S1.);
#31 = PCURVE('',#32,#36);
#32 = CYLINDRICAL_SURFACE('',#33,16.75);
#36 = DEFINITIONAL_REPRESENTATION('',(#37),#47);
#37 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#38,#39),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,1.),.PIECEWISE_BEZIER_KNOTS.);
#38 = CARTESIAN_POINT('',(0.,-287.35));
#39 = CARTESIAN_POINT('',(0.,-16.917));
#49 = EDGE_CURVE('',#22,#22,#50,.T.);
#50 = SURFACE_CURVE('',#51,(#56),.PCURVE_S1.);
#56 = PCURVE('',#32,#60);
#60 = DEFINITIONAL_REPRESENTATION('',(#61),#70);
#61 = B_SPLINE_CURVE_WITH_KNOTS('',8,(#62,#63,#64,#65,#66,#67,#68,#69,#70),
  .UNSPECIFIED.,.F.,.F.,(9,9),(0.,6.28318530718),.PIECEWISE_BEZIER_KNOTS.);
#62 = CARTESIAN_POINT('',(-6.28318530718,-43.694));
#63 = CARTESIAN_POINT('',(-5.497787143782,-43.694));
#64 = CARTESIAN_POINT('',(-4.712388980386,-40.0));
#65 = CARTESIAN_POINT('',(-3.92699081698,-20.0));
#66 = CARTESIAN_POINT('',(-3.14159265362,9.859));
#67 = CARTESIAN_POINT('',(-2.356194490184,-20.0));
#68 = CARTESIAN_POINT('',(-1.570796326798,-40.0));
#69 = CARTESIAN_POINT('',(-0.785398163397,-43.694));
#70 = CARTESIAN_POINT('',(0.,-43.694));
#82 = EDGE_CURVE('',#24,#24,#83,.T.);
#83 = SURFACE_CURVE('',#84,(#89),.PCURVE_S1.);
#89 = PCURVE('',#32,#90);
#90 = DEFINITIONAL_REPRESENTATION('',(#91),#94);
#91 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#92,#93),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,6.28318530718),.PIECEWISE_BEZIER_KNOTS.);
#92 = CARTESIAN_POINT('',(0.,-287.35));
#93 = CARTESIAN_POINT('',(-6.28318530718,-287.35));
#711 = EDGE_CURVE('',#712,#712,#714,.T.);
#714 = SURFACE_CURVE('',#715,(#720),.PCURVE_S1.);
#720 = PCURVE('',#490,#724);
#724 = DEFINITIONAL_REPRESENTATION('',(#725),#730);
#725 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#726,#727),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,1.),.PIECEWISE_BEZIER_KNOTS.);
#726 = CARTESIAN_POINT('',(-6.28318530718,-39.218));
#727 = CARTESIAN_POINT('',(0.,5.383));
#745 = EDGE_CURVE('',#712,#376,#746,.T.);
#746 = SEAM_CURVE('',#747,(#751),.PCURVE_S1.);
#751 = PCURVE('',#490,#755);
#755 = DEFINITIONAL_REPRESENTATION('',(#756),#760);
#756 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#757,#758),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,1.),.PIECEWISE_BEZIER_KNOTS.);
#757 = CARTESIAN_POINT('',(0.,-287.35));
#758 = CARTESIAN_POINT('',(0.,-16.917));
#178 = CYLINDRICAL_SURFACE('',#179,21.15);
#490 = CYLINDRICAL_SURFACE('',#491,13.95);
ENDSEC;
END-ISO-10303-21;
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "tube.stp"
            path.write_text(step_text, encoding="utf-8")
            analysis = analyze_step_round_tube_text(path)

        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertAlmostEqual(analysis.outer_diameter_mm, 33.5)
        self.assertAlmostEqual(analysis.wall_thickness_mm, 2.8)
        self.assertEqual(analysis.pierce_count, 2)

    def test_step_round_tube_text_analysis_wins_over_sheet_like_bbox(self) -> None:
        from tempfile import TemporaryDirectory

        step_text = """
ISO-10303-21;
DATA;
#21 = EDGE_CURVE('',#22,#24,#26,.T.);
#26 = SEAM_CURVE('',#27,(#31),.PCURVE_S1.);
#31 = PCURVE('',#32,#36);
#32 = CYLINDRICAL_SURFACE('',#33,21.15);
#36 = DEFINITIONAL_REPRESENTATION('',(#37),#47);
#37 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#38,#39),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,1.),.PIECEWISE_BEZIER_KNOTS.);
#38 = CARTESIAN_POINT('',(0.,-3956.92));
#39 = CARTESIAN_POINT('',(0.,0.));
#49 = EDGE_CURVE('',#22,#22,#50,.T.);
#50 = SURFACE_CURVE('',#51,(#56),.PCURVE_S1.);
#56 = PCURVE('',#32,#60);
#60 = DEFINITIONAL_REPRESENTATION('',(#61),#70);
#61 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#62,#63),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,6.28318530718),.PIECEWISE_BEZIER_KNOTS.);
#62 = CARTESIAN_POINT('',(0.,-3956.92));
#63 = CARTESIAN_POINT('',(-6.28318530718,-3956.92));
#82 = EDGE_CURVE('',#24,#24,#83,.T.);
#83 = SURFACE_CURVE('',#84,(#89),.PCURVE_S1.);
#89 = PCURVE('',#32,#90);
#90 = DEFINITIONAL_REPRESENTATION('',(#91),#94);
#91 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#92,#93),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,6.28318530718),.PIECEWISE_BEZIER_KNOTS.);
#92 = CARTESIAN_POINT('',(0.,0.));
#93 = CARTESIAN_POINT('',(-6.28318530718,0.));
#132 = CYLINDRICAL_SURFACE('',#133,18.35);
#145 = EDGE_CURVE('',#146,#147,#148,.T.);
#148 = SEAM_CURVE('',#149,(#150),.PCURVE_S1.);
#150 = PCURVE('',#132,#151);
#151 = DEFINITIONAL_REPRESENTATION('',(#152),#155);
#152 = B_SPLINE_CURVE_WITH_KNOTS('',1,(#153,#154),.UNSPECIFIED.,.F.,.F.,
  (2,2),(0.,1.),.PIECEWISE_BEZIER_KNOTS.);
#153 = CARTESIAN_POINT('',(0.,-3956.92));
#154 = CARTESIAN_POINT('',(0.,0.));
ENDSEC;
END-ISO-10303-21;
"""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sheet_like_round_tube.stp"
            path.write_text(step_text, encoding="utf-8")
            result = analyze_shape(
                None,
                summary=ShapeSummary(
                    size_x_mm=3.0,
                    size_y_mm=3956.92,
                    size_z_mm=42.3,
                    diagonal_mm=3957.15,
                    face_count=5,
                    edge_count=10,
                ),
                file_format="STEP",
                source_path=path,
            )

        self.assertEqual(result.profile_hint, "Круглая труба")
        self.assertAlmostEqual(result.round_outer_diameter_mm, 42.3)
        self.assertEqual(result.pierce_count, 2)
        self.assertIsNone(result.sheet_analysis)

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

        self.assertIn(
            "source_file,app_version,build_commit,calc_core,edge_index,length_mm,edge_type,included_in_cut",
            content,
        )
        self.assertIn(
            "part.step,v0.5.5,local,round-iges-fallback-v2,1,30.000000,CUT_FEATURE,yes",
            content,
        )
        self.assertIn(
            "part.step,v0.5.5,local,round-iges-fallback-v2,2,1000.000000,IGNORED_LONGITUDINAL,no",
            content,
        )

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

    def test_cut_face_analysis_uses_unlabeled_stitched_brep_boundary(self) -> None:
        stitched_outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 80.0, 0.0, 1000.0),
            is_outer_longitudinal=False,
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
        stitched_outer_edge = EdgeRecord(
            edge=object(),
            length_mm=30.0,
            bounds=Bounds(20.0, 0.0, 300.0, 50.0, 0.0, 300.0),
            faces=[stitched_outer_face, thickness_face],
        )
        inner_edge = EdgeRecord(
            edge=object(),
            length_mm=24.0,
            bounds=Bounds(23.0, 3.0, 303.0, 47.0, 3.0, 303.0),
            faces=[inner_face, thickness_face],
            wire_roles={"inner_wire"},
        )
        record = ThicknessFaceRecord(
            face=thickness_face,
            area_mm2=90.0,
            thickness_mm=3.0,
            cut_length_mm=30.0,
            edges=(stitched_outer_edge, inner_edge),
        )

        analysis = _analyze_cut_faces(
            (record,),
            axis="Z",
            length_mm=1000.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 80.0, 40.0, 1000.0),
            tolerance=0.01,
        )

        self.assertEqual(analysis.cut_edges, (stitched_outer_edge,))
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual(stitched_outer_edge.edge_type, CUT_FEATURE)

    def test_shell_open_boundary_fallback_counts_merged_boundary_components(self) -> None:
        base_end = EdgeRecord(
            edge=object(),
            length_mm=88.0,
            bounds=Bounds(0.0, 0.0, 0.0, 88.0, 0.0, 0.0),
            edge_type=CUT_END,
            cut_component_id=1,
        )
        first = EdgeRecord(
            edge=object(),
            length_mm=10.0,
            bounds=Bounds(0.0, 0.0, 100.0, 10.0, 0.0, 100.0),
            start_point=(0.0, 0.0, 100.0),
            end_point=(10.0, 0.0, 100.0),
            faces=[FaceRecord(object(), Bounds(0.0, 0.0, 100.0, 10.0, 0.0, 100.0), False)],
        )
        near_duplicate_side = EdgeRecord(
            edge=object(),
            length_mm=10.0,
            bounds=Bounds(0.0, 0.4, 100.0, 10.0, 0.4, 100.0),
            start_point=(0.0, 0.4, 100.0),
            end_point=(10.0, 0.4, 100.0),
            faces=[FaceRecord(object(), Bounds(0.0, 0.4, 100.0, 10.0, 0.4, 100.0), False)],
        )
        separate = EdgeRecord(
            edge=object(),
            length_mm=12.0,
            bounds=Bounds(30.0, 0.0, 300.0, 42.0, 0.0, 300.0),
            start_point=(30.0, 0.0, 300.0),
            end_point=(42.0, 0.0, 300.0),
            faces=[FaceRecord(object(), Bounds(30.0, 0.0, 300.0, 42.0, 0.0, 300.0), False)],
        )

        analysis = _analyze_shell_open_boundary_fallback(
            (base_end, first, near_duplicate_side, separate),
            base_cut_edges=(base_end,),
            base_pierce_count=1,
            axis="Z",
            length_mm=1000.0,
            tolerance=0.01,
        )

        self.assertEqual(analysis.pierce_count, 3)
        self.assertEqual(analysis.cut_edges, (base_end, first, near_duplicate_side, separate))
        self.assertEqual(first.cut_component_id, near_duplicate_side.cut_component_id)
        self.assertNotEqual(first.cut_component_id, separate.cut_component_id)

    def test_shell_open_boundary_fallback_accepts_stitched_two_face_edges(self) -> None:
        first_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 100.0, 10.0, 0.0, 100.0),
            is_outer_longitudinal=False,
        )
        second_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 100.0, 10.0, 4.0, 100.0),
            is_outer_longitudinal=False,
        )
        stitched_edge = EdgeRecord(
            edge=object(),
            length_mm=10.0,
            bounds=Bounds(0.0, 0.0, 100.0, 10.0, 0.0, 100.0),
            start_point=(0.0, 0.0, 100.0),
            end_point=(10.0, 0.0, 100.0),
            faces=[first_face, second_face],
        )

        analysis = _analyze_shell_open_boundary_fallback(
            (stitched_edge,),
            base_cut_edges=(),
            base_pierce_count=0,
            axis="Z",
            length_mm=1000.0,
            tolerance=0.01,
        )

        self.assertEqual(analysis.cut_edges, (stitched_edge,))
        self.assertEqual(analysis.pierce_count, 1)
        self.assertEqual(stitched_edge.edge_type, CUT_FEATURE)

    def test_shell_open_boundary_fallback_ignores_tiny_thickness_fragments(self) -> None:
        face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 20.0, 20.0, 0.0),
            is_outer_longitudinal=False,
        )
        base_edge = EdgeRecord(
            edge=object(),
            length_mm=20.0,
            bounds=Bounds(0.0, 0.0, 0.0, 20.0, 0.0, 0.0),
            faces=[face],
            edge_type=CUT_FEATURE,
            cut_component_id=1,
        )
        normal_edges = tuple(
            EdgeRecord(
                edge=object(),
                length_mm=length,
                bounds=Bounds(offset, 0.0, 100.0, offset + length, 0.0, 100.0),
                start_point=(offset, 0.0, 100.0),
                end_point=(offset + length, 0.0, 100.0),
                faces=[face],
            )
            for offset, length in ((100.0, 33.0), (200.0, 10.5), (300.0, 12.3))
        )
        tiny_edges = tuple(
            EdgeRecord(
                edge=object(),
                length_mm=1.5,
                bounds=Bounds(offset, 0.0, 100.0, offset + 1.5, 0.0, 100.0),
                start_point=(offset, 0.0, 100.0),
                end_point=(offset + 1.5, 0.0, 100.0),
                faces=[face],
            )
            for offset in (400.0, 410.0, 420.0)
        )

        analysis = _analyze_shell_open_boundary_fallback(
            normal_edges + tiny_edges,
            base_cut_edges=(base_edge,),
            base_pierce_count=1,
            axis="Z",
            length_mm=500.0,
            tolerance=0.1,
        )

        self.assertEqual(analysis.pierce_count, 5)
        self.assertEqual(len(analysis.cut_edges), 7)
        self.assertEqual(tiny_edges[0].cut_component_id, tiny_edges[1].cut_component_id)

    def test_cut_face_analysis_ignores_tiny_single_edge_thickness_fragments(self) -> None:
        outer_face = FaceRecord(
            face=object(),
            bounds=Bounds(0.0, 0.0, 0.0, 20.0, 0.0, 500.0),
            is_outer_longitudinal=True,
        )

        def record_for_edge(offset: float, length: float) -> ThicknessFaceRecord:
            face = FaceRecord(
                face=object(),
                bounds=Bounds(offset, 0.0, 100.0, offset + length, 1.5, 100.0),
                is_outer_longitudinal=False,
            )
            edge = EdgeRecord(
                edge=object(),
                length_mm=length,
                bounds=Bounds(offset, 0.0, 100.0, offset + length, 0.0, 100.0),
                start_point=(offset, 0.0, 100.0),
                end_point=(offset + length, 0.0, 100.0),
                faces=[face, outer_face],
            )
            return ThicknessFaceRecord(
                face=face,
                area_mm2=length * 1.5,
                thickness_mm=1.5,
                cut_length_mm=length,
                edges=(edge,),
            )

        records = tuple(
            record_for_edge(offset, length)
            for offset, length in (
                (100.0, 33.0),
                (200.0, 10.5),
                (300.0, 12.3),
                (400.0, 9.0),
                (500.0, 1.5),
                (510.0, 1.5),
                (520.0, 1.5),
            )
        )

        analysis = _analyze_cut_faces(
            records,
            axis="Z",
            length_mm=500.0,
            global_bounds=Bounds(0.0, 0.0, 0.0, 600.0, 20.0, 500.0),
            tolerance=0.1,
        )

        self.assertEqual(analysis.pierce_count, 4)
        self.assertEqual(len(analysis.cut_edges), 4)
        self.assertEqual(len(analysis.cut_faces), 4)

    def test_complex_profile_contour_fallback_uses_dominant_and_opposite_end(self) -> None:
        dominant_a = EdgeRecord(
            edge=object(),
            length_mm=180.0,
            bounds=Bounds(0.0, 0.0, -250.0, 0.0, 0.0, -100.0),
            edge_type=UNCERTAIN,
        )
        dominant_b = EdgeRecord(
            edge=object(),
            length_mm=140.0,
            bounds=Bounds(0.0, 0.0, -100.0, 20.0, 0.0, -100.0),
            edge_type=CUT_FEATURE,
        )
        duplicate = EdgeRecord(
            edge=object(),
            length_mm=260.0,
            bounds=Bounds(2.0, 0.0, -250.0, 2.0, 0.0, -100.0),
            edge_type=UNCERTAIN,
        )
        end_a = EdgeRecord(
            edge=object(),
            length_mm=20.0,
            bounds=Bounds(0.0, 0.0, 250.0, 20.0, 0.0, 250.0),
            edge_type=UNCERTAIN,
        )
        end_b = EdgeRecord(
            edge=object(),
            length_mm=15.0,
            bounds=Bounds(20.0, 0.0, 250.0, 25.0, 0.0, 250.0),
            edge_type=CUT_END,
        )

        analysis = _analyze_complex_profile_contour_fallback(
            (dominant_a, dominant_b, duplicate, end_a, end_b),
            base_cut_length_mm=120.0,
            axis="Z",
            length_mm=500.0,
            global_bounds=Bounds(0.0, 0.0, -250.0, 40.0, 20.0, 250.0),
            tolerance=0.1,
        )

        self.assertEqual(analysis.pierce_count, 2)
        self.assertEqual(analysis.cut_edges, (dominant_a, dominant_b, end_a, end_b))
        self.assertEqual(sum(edge.length_mm for edge in analysis.cut_edges), 355.0)
        self.assertEqual(dominant_a.cut_component_id, 1)
        self.assertEqual(end_a.cut_component_id, 2)
        self.assertEqual(end_a.edge_type, CUT_END)
        self.assertEqual(duplicate.cut_component_id, 0)

    def test_profile_tube_prefers_cut_edge_components_when_outer_skin_is_clear(self) -> None:
        self.assertTrue(
            _prefer_cut_edge_components_for_cut_faces(
                cut_face_edge_component_count=12,
                cut_face_pierce_count=1,
                outer_face_count=20,
            )
        )
        self.assertTrue(
            _prefer_cut_edge_components_for_cut_faces(
                cut_face_edge_component_count=7,
                cut_face_pierce_count=7,
                outer_face_count=8,
            )
        )
        self.assertTrue(
            _prefer_cut_edge_components_for_cut_faces(
                cut_face_edge_component_count=3,
                cut_face_pierce_count=1,
                outer_face_count=11,
            )
        )
        self.assertFalse(
            _prefer_cut_edge_components_for_cut_faces(
                cut_face_edge_component_count=27,
                cut_face_pierce_count=27,
                outer_face_count=5,
            )
        )

    def test_round_bbox_compact_mixed_features_are_limited_to_short_dense_tubes(self) -> None:
        mixed_edges = tuple(EdgeRecord(object(), 10.0) for _index in range(60))
        outer_edges = (*mixed_edges, *(EdgeRecord(object(), 2.0) for _index in range(120)))

        self.assertTrue(
            _round_bbox_should_use_compact_mixed_features(
                outer_only_feature_edges=outer_edges,
                mixed_feature_edges=mixed_edges,
                outer_only_length=840.0,
                mixed_length=600.0,
                end_length=120.0,
                outer_radius=25.0,
                length_mm=200.0,
            )
        )
        self.assertFalse(
            _round_bbox_should_use_compact_mixed_features(
                outer_only_feature_edges=outer_edges,
                mixed_feature_edges=mixed_edges,
                outer_only_length=840.0,
                mixed_length=600.0,
                end_length=120.0,
                outer_radius=25.0,
                length_mm=1000.0,
            )
        )

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

    def test_cut_edge_components_merge_coplanar_iges_fragments(self) -> None:
        first_fragment = EdgeRecord(
            edge=object(),
            length_mm=9.36,
            bounds=Bounds(0.0, 20.0, 100.0, 0.0, 29.3, 100.1),
            edge_type=CUT_FEATURE,
        )
        second_fragment = EdgeRecord(
            edge=object(),
            length_mm=9.34,
            bounds=Bounds(0.0, 20.1, 102.9, 0.0, 28.9, 105.8),
            edge_type=CUT_FEATURE,
        )
        third_fragment = EdgeRecord(
            edge=object(),
            length_mm=3.15,
            bounds=Bounds(0.0, 19.4, 108.0, 0.0, 21.5, 110.3),
            edge_type=CUT_FEATURE,
        )
        separate_cut = EdgeRecord(
            edge=object(),
            length_mm=46.0,
            bounds=Bounds(0.0, 0.0, 240.0, 0.0, 20.0, 243.0),
            edge_type=CUT_FEATURE,
        )

        self.assertEqual(
            _count_cut_edge_components(
                (first_fragment, second_fragment, third_fragment, separate_cut),
                axis="Z",
                global_bounds=Bounds(0.0, -50.0, 0.0, 100.0, 50.0, 1000.0),
                tolerance=0.1,
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
