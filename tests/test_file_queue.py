from __future__ import annotations

import sys
import types
import unittest

from cad.analyzer import GeometryAnalysisResult, analyze_shape
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


if __name__ == "__main__":
    unittest.main()
