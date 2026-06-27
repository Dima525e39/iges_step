from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

APP_NAME = "TubeCutCalculator"
APP_VERSION = "v0.5.5"
APP_DESCRIPTION = (
    "Калькулятор лазерной резки труб и листовых деталей: STEP/IGES/DXF, "
    "расчет реза, nesting, цены, закупка, Excel/PDF и печать."
)


def _load_app_build_identity() -> tuple[str, str, str]:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "app_build.py")
    candidates.append(Path(__file__).with_name("app_build.py"))
    executable = getattr(sys, "executable", "")
    if executable:
        candidates.append(Path(executable).with_name("app_build.py"))

    for path in candidates:
        if not path.exists():
            continue
        spec = importlib.util.spec_from_file_location("_tubecut_app_build", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return (
            str(getattr(module, "APP_BUILD_COMMIT")),
            str(getattr(module, "APP_BUILD_DATE")),
            str(getattr(module, "CALC_CORE_REVISION")),
        )
    raise RuntimeError("app_build.py identity file was not found")


try:
    from app_build import APP_BUILD_COMMIT, APP_BUILD_DATE, CALC_CORE_REVISION
except Exception:
    try:
        APP_BUILD_COMMIT, APP_BUILD_DATE, CALC_CORE_REVISION = _load_app_build_identity()
    except Exception:
        APP_BUILD_COMMIT = "unknown"
        APP_BUILD_DATE = "unknown"
        CALC_CORE_REVISION = "unknown"


def build_label() -> str:
    if APP_BUILD_COMMIT in {"", "local", "unknown"}:
        return APP_VERSION
    return f"{APP_VERSION} {APP_BUILD_COMMIT[:7]}"
