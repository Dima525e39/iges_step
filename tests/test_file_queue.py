from __future__ import annotations

import unittest

from cad.importer import CadImportError, CadImporter
from cad.supported_formats import collect_supported_files, is_supported_cad_file
from core.file_queue import FileQueue


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


if __name__ == "__main__":
    unittest.main()
