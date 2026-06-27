from __future__ import annotations

APP_NAME = "TubeCutCalculator"
APP_VERSION = "v0.5.4"
APP_DESCRIPTION = (
    "Калькулятор лазерной резки труб и листовых деталей: STEP/IGES/DXF, "
    "расчет реза, nesting, цены, закупка, Excel/PDF и печать."
)

try:
    from app_build import APP_BUILD_COMMIT, APP_BUILD_DATE, CALC_CORE_REVISION
except Exception:
    APP_BUILD_COMMIT = "unknown"
    APP_BUILD_DATE = "unknown"
    CALC_CORE_REVISION = "unknown"


def build_label() -> str:
    if APP_BUILD_COMMIT in {"", "local", "unknown"}:
        return APP_VERSION
    return f"{APP_VERSION} {APP_BUILD_COMMIT[:7]}"
