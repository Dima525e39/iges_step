from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from core.file_job import FileJob, STATUS_IMPORTED
from export.excel_exporter import export_excel_workbook
from export.json_project import load_project, save_project
from pricing.price_selector import calculate_job_price
from purchase.tube_purchase_calculator import calculate_tube_purchase


class PricingPurchaseProjectTests(unittest.TestCase):
    def test_price_selector_applies_contract_markup_and_rule(self) -> None:
        settings = {
            "contractors": [
                {
                    "id": "romashka",
                    "name": "ООО Ромашка",
                    "markup_percent": 10.0,
                    "currency": "руб.",
                    "is_default": True,
                }
            ],
            "pricing": {
                "markup_percent": 5.0,
                "rules": [
                    {
                        "contractor": "ООО Ромашка",
                        "material": "Сталь",
                        "thickness_mm": 1.5,
                        "price_per_meter": 100.0,
                        "price_per_pierce": 20.0,
                        "minimum_price": 0.0,
                        "setup_price": 50.0,
                        "complexity_factor": 1.0,
                        "active": True,
                        "is_default": True,
                    }
                ],
            },
        }

        result = calculate_job_price(
            settings,
            contractor="ООО Ромашка",
            material="Сталь",
            thickness_mm=1.5,
            cut_length_mm=1000.0,
            pierce_count=2,
        )

        self.assertEqual(result.selection.source, "точное правило")
        self.assertAlmostEqual(result.total, 219.45)

    def test_purchase_groups_different_tube_sizes_separately(self) -> None:
        first = FileJob(Path("a.step"), status=STATUS_IMPORTED)
        first.material = "Сталь"
        first.tube_type = "профильная труба"
        first.tube_size = "25.0×25.0×1.5"
        first.wall_thickness_mm = "1.5 мм"
        first.tube_length_mm = "3000.0 мм"
        second = FileJob(Path("b.step"), status=STATUS_IMPORTED)
        second.material = "Сталь"
        second.tube_type = "профильная труба"
        second.tube_size = "40.0×20.0×1.5"
        second.wall_thickness_mm = "1.5 мм"
        second.tube_length_mm = "3000.0 мм"

        rows = calculate_tube_purchase(
            [first, second],
            {
                "materials": [
                    {
                        "id": "steel",
                        "name": "Сталь",
                        "standard_stock_length_mm": 6000.0,
                        "is_default": True,
                    }
                ],
                "purchase": {"standard_stock_length_mm": 6000.0, "stock_allowance_percent": 0.0},
            },
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual({row.tube_size for row in rows}, {first.tube_size, second.tube_size})

    def test_purchase_uses_job_quantity(self) -> None:
        job = FileJob(Path("a.step"), status=STATUS_IMPORTED)
        job.material = "Сталь"
        job.tube_type = "профильная труба"
        job.tube_size = "25.0×25.0×1.5"
        job.wall_thickness_mm = "1.5 мм"
        job.tube_length_mm = "1000.0 мм"
        job.quantity = 3

        rows = calculate_tube_purchase(
            [job],
            {
                "materials": [
                    {
                        "id": "steel",
                        "name": "Сталь",
                        "standard_stock_length_mm": 6000.0,
                        "is_default": True,
                    }
                ],
                "purchase": {"standard_stock_length_mm": 6000.0, "stock_allowance_percent": 0.0},
            },
        )

        self.assertEqual(rows[0].detail_count, 3)
        self.assertEqual(rows[0].detail_length_mm, 3000.0)

    def test_file_job_table_row_keeps_thickness_separate(self) -> None:
        job = FileJob(Path("tube.step"), status=STATUS_IMPORTED)
        job.tube_size = "Ø35.0"
        job.wall_thickness_mm = "2.5 мм"
        job.tube_length_mm = "1000.0 мм"
        job.cut_length_mm = "407.2 мм"
        job.pierce_count = "3"
        job.quantity = 2
        job.price = "1200.00"

        self.assertEqual(
            job.to_table_row(),
            [
                "tube.step",
                "Ø35.0",
                "2.5 мм",
                "1000.0 мм",
                "407.2 мм",
                "3",
                "2",
                "1200.00 руб.",
            ],
        )

    def test_excel_export_contains_isometry_images(self) -> None:
        job = FileJob(Path("tube.step"), status=STATUS_IMPORTED)
        job.tube_size = "Ø35.0"
        job.wall_thickness_mm = "2.5 мм"
        job.tube_length_mm = "1000.0 мм"
        job.cut_length_mm = "407.2 мм"
        job.pierce_count = "3"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calculation.xlsx"
            export_excel_workbook([job], [], {}, path)
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertTrue(any(name.startswith("xl/media/") for name in names))
        self.assertIn("xl/drawings/drawing1.xml", names)
        self.assertIn("xl/worksheets/_rels/sheet1.xml.rels", names)
        self.assertIn("Толщина", sheet)
        self.assertIn("drawing", sheet)

    def test_excel_export_uses_supplied_real_isometry_image(self) -> None:
        job = FileJob(Path("real.step"), status=STATUS_IMPORTED)
        real_image = _tiny_png()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calculation.xlsx"
            export_excel_workbook(
                [job],
                [],
                {},
                path,
                isometry_images={job.normalized_path: real_image},
            )
            with zipfile.ZipFile(path) as archive:
                media_names = [name for name in archive.namelist() if name.startswith("xl/media/")]
                image = archive.read(media_names[0])

        self.assertGreater(len(image), 0)

    def test_project_saves_job_isometry_path(self) -> None:
        job = FileJob(Path("part.step"), status=STATUS_IMPORTED)
        job.isometry_image_path = "cache/part.png"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project([job], path, settings={})
            jobs, _loaded_settings = load_project(path)

        self.assertEqual(jobs[0].isometry_image_path, "cache/part.png")

    def test_project_saves_jobs_and_settings(self) -> None:
        job = FileJob(Path("part.step"), status=STATUS_IMPORTED)
        job.tube_size = "25.0×25.0×1.5"
        settings = {"ui": {"theme": "dark"}}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project([job], path, settings=settings)
            jobs, loaded_settings = load_project(path)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].tube_size, "25.0×25.0×1.5")
        self.assertEqual(loaded_settings["ui"]["theme"], "dark")


def _tiny_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
    )


if __name__ == "__main__":
    unittest.main()
