from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from core.file_job import FileJob, STATUS_IMPORTED
from export.excel_exporter import export_excel_workbook
from export.json_project import load_project, save_project
from export.report_html import commercial_offer_html
from pricing.material_cost import calculate_tube_material_cost
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

    def test_material_cost_is_zero_for_customer_tube(self) -> None:
        result = calculate_tube_material_cost(
            {
                "materials": [
                    {"id": "steel", "name": "Сталь", "tube_price_per_meter": 1000.0}
                ]
            },
            material="Сталь",
            tube_length_mm=1000.0,
            quantity=2,
            customer_tube=True,
        )

        self.assertEqual(result.total, 0.0)

    def test_material_cost_uses_material_price_and_purchase_allowances(self) -> None:
        result = calculate_tube_material_cost(
            {
                "materials": [
                    {
                        "id": "steel",
                        "name": "Сталь",
                        "standard_stock_length_mm": 6000.0,
                        "tube_price_per_meter": 1000.0,
                    }
                ],
                "purchase": {
                    "stock_allowance_percent": 10.0,
                    "include_part_gap": False,
                    "chuck_remainder_mm": 0.0,
                },
            },
            material="Сталь",
            tube_length_mm=1000.0,
            quantity=2,
            customer_tube=False,
        )

        self.assertAlmostEqual(result.unit, 1100.0)
        self.assertAlmostEqual(result.total, 2200.0)

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

    def test_purchase_uses_chuck_remainder_as_unusable_stock_length(self) -> None:
        first = FileJob(Path("a.step"), status=STATUS_IMPORTED)
        first.material = "Сталь"
        first.tube_type = "профильная труба"
        first.tube_size = "60.0×60.0"
        first.wall_thickness_mm = "4.0 мм"
        first.tube_length_mm = "3000.0 мм"
        first.quantity = 2

        rows = calculate_tube_purchase(
            [first],
            {
                "materials": [
                    {
                        "id": "steel",
                        "name": "Сталь",
                        "standard_stock_length_mm": 6000.0,
                        "is_default": True,
                    }
                ],
                "purchase": {
                    "standard_stock_length_mm": 6000.0,
                    "chuck_remainder_mm": 300.0,
                    "stock_allowance_percent": 0.0,
                    "include_part_gap": False,
                    "end_trim_allowance_mm": 0.0,
                },
            },
        )

        self.assertEqual(rows[0].stock_count, 2)
        self.assertEqual(rows[0].purchase_length_mm, 12000.0)
        self.assertIn("полезная длина хлыста 5700.0 мм", rows[0].warnings)

    def test_purchase_packs_parts_by_detail_lengths(self) -> None:
        first = FileJob(Path("a.step"), status=STATUS_IMPORTED)
        first.material = "Сталь"
        first.tube_type = "профильная труба"
        first.tube_size = "60.0×60.0"
        first.wall_thickness_mm = "4.0 мм"
        first.tube_length_mm = "3500.0 мм"
        first.quantity = 3

        rows = calculate_tube_purchase(
            [first],
            {
                "materials": [
                    {
                        "id": "steel",
                        "name": "Сталь",
                        "standard_stock_length_mm": 6000.0,
                        "is_default": True,
                    }
                ],
                "purchase": {
                    "standard_stock_length_mm": 6000.0,
                    "chuck_remainder_mm": 0.0,
                    "stock_allowance_percent": 0.0,
                    "include_part_gap": False,
                    "end_trim_allowance_mm": 0.0,
                },
            },
        )

        self.assertEqual(rows[0].stock_count, 3)

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
                "Сталь",
                "Ø35.0",
                "2.5 мм",
                "1000.0 мм",
                "407.2 мм",
                "3",
                "2",
                "1200.00 руб.",
            ],
        )

    def test_excel_export_adds_totals_row_without_isometry(self) -> None:
        job = FileJob(Path("tube.step"), status=STATUS_IMPORTED)
        job.tube_size = "Ø35.0"
        job.wall_thickness_mm = "2.5 мм"
        job.tube_length_mm = "1000.0 мм"
        job.cut_length_mm = "407.2 мм"
        job.pierce_count = "3"
        job.quantity = 2
        job.price = "1200.00"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calculation.xlsx"
            export_excel_workbook([job], [], {}, path)
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

        self.assertFalse(any(name.startswith("xl/media/") for name in names))
        self.assertNotIn("Изометрия", sheet)
        self.assertIn("Итого", sheet)
        self.assertIn("814.4 мм", sheet)
        self.assertIn("1200.00 руб.", sheet)

    def test_purchase_groups_same_tube_by_material(self) -> None:
        first = FileJob(Path("steel.step"), status=STATUS_IMPORTED)
        first.material = "Сталь"
        first.tube_type = "Круглая труба"
        first.tube_size = "Ø35.0"
        first.wall_thickness_mm = "2.5 мм"
        first.tube_length_mm = "1000.0 мм"

        second = FileJob(Path("inox.step"), status=STATUS_IMPORTED)
        second.material = "Нержавейка"
        second.tube_type = first.tube_type
        second.tube_size = first.tube_size
        second.wall_thickness_mm = first.wall_thickness_mm
        second.tube_length_mm = first.tube_length_mm

        rows = calculate_tube_purchase(
            [first, second],
            {
                "materials": [
                    {"id": "steel", "name": "Сталь", "is_default": True},
                    {"id": "inox", "name": "Нержавейка"},
                ],
                "purchase": {"standard_stock_length_mm": 6000.0},
            },
        )

        self.assertEqual({row.material for row in rows}, {"Сталь", "Нержавейка"})

    def test_invoice_html_uses_requisites_and_hides_disabled_logo(self) -> None:
        job = FileJob(Path("tube.step"), status=STATUS_IMPORTED)
        job.cut_length_mm = "1000.0 мм"
        job.pierce_count = "2"
        job.quantity = 2
        job.price = "500.00"
        settings = {
            "logo": {"path": "/tmp/logo.png", "enabled": False},
            "contractors": [
                {
                    "id": "buyer",
                    "name": "ООО Покупатель",
                    "inn": "7700000000",
                    "kpp": "770001001",
                    "address": "Москва",
                    "is_default": True,
                }
            ],
            "commercial_offer": {
                "document_title": "Счет на оплату",
                "number": "42",
                "date": "2026-06-25",
                "supplier_name": "ИП Поставщик",
                "supplier_inn": "660000000000",
                "supplier_bank": "Банк",
                "supplier_bik": "123456789",
                "supplier_account": "40700000000000000000",
                "supplier_corr_account": "30100000000000000000",
                "basis": "Договор поставки",
                "vat_mode": "included",
                "vat_rate": 20.0,
                "unit": "шт",
            },
        }

        html = commercial_offer_html([job], [], settings)

        self.assertIn("Счет на оплату № 42", html)
        self.assertIn("ООО Покупатель", html)
        self.assertIn("770001001", html)
        self.assertIn("В том числе НДС (20%)", html)
        self.assertNotIn("<img", html)

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

if __name__ == "__main__":
    unittest.main()
