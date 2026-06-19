from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
