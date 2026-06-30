from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path


CALCULATION_MODULES = (
    "cad.supported_formats",
    "cad.shape_summary",
    "cad.profile_detector",
    "cad.debug_faces",
    "cad.debug_edges",
    "cad.step_text_analyzer",
    "cad.dxf_reader",
    "cad.inventor_converter",
    "cad.importer",
    "cad.edge_classifier",
    "cad.pierce_counter",
    "cad.cut_length_calculator",
    "cad.analyzer",
    "cad.unfolder",
    "core.specification_importer",
    "pricing.price_selector",
    "pricing.material_cost",
    "purchase.tube_grouping",
    "purchase.tube_purchase_calculator",
    "ui.import_worker",
)


@dataclass(frozen=True, slots=True)
class ReloadResult:
    source_root: Path
    modules: tuple[str, ...]
    skipped: tuple[str, ...] = ()


def reload_calculation_core(source_root: str | Path) -> ReloadResult:
    root = Path(source_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Папка исходников не найдена: {root}")

    _prepend_sys_path(root)
    _prepend_package_paths(root)
    importlib.invalidate_caches()

    reloaded: list[str] = []
    skipped: list[str] = []
    for module_name in CALCULATION_MODULES:
        if not _module_source_exists(root, module_name):
            skipped.append(module_name)
            continue
        module = sys.modules.get(module_name)
        if module is None:
            importlib.import_module(module_name)
        else:
            importlib.reload(module)
        reloaded.append(module_name)

    return ReloadResult(
        source_root=root,
        modules=tuple(reloaded),
        skipped=tuple(skipped),
    )


def _prepend_sys_path(root: Path) -> None:
    root_text = str(root)
    sys.path[:] = [path for path in sys.path if path != root_text]
    sys.path.insert(0, root_text)


def _prepend_package_paths(root: Path) -> None:
    for package_name in ("cad", "core", "pricing", "purchase", "ui"):
        package_dir = root / package_name
        if not package_dir.is_dir():
            continue
        package = sys.modules.get(package_name)
        if package is None or not hasattr(package, "__path__"):
            continue
        package_path = str(package_dir)
        paths = list(package.__path__)  # type: ignore[attr-defined]
        package.__path__ = [package_path, *(path for path in paths if path != package_path)]  # type: ignore[attr-defined]


def _module_source_exists(root: Path, module_name: str) -> bool:
    parts = module_name.split(".")
    module_file = root.joinpath(*parts).with_suffix(".py")
    package_init = root.joinpath(*parts, "__init__.py")
    return module_file.exists() or package_init.exists()
