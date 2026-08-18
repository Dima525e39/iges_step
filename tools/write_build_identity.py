from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


CALC_CORE_REVISION = "tube-kernel-v6"


def main() -> int:
    version = sys.argv[1] if len(sys.argv) > 1 else "v0.6.0"
    commit = os.environ.get("BUILD_COMMIT", "").strip() or "manual-build"
    build_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    Path("app_build.py").write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                f"APP_BUILD_COMMIT = {commit!r}",
                f"APP_BUILD_DATE = {build_date!r}",
                f"CALC_CORE_REVISION = {CALC_CORE_REVISION!r}",
                "",
            )
        ),
        encoding="utf-8",
    )
    Path("version.txt").write_text(
        "\n".join(
            (
                f"TubeCutCalculator {version}",
                f"Build date: {build_date}",
                f"Build commit: {commit}",
                f"Calc core: {CALC_CORE_REVISION}",
                "Description: Clean-room tube geometry kernel with oriented 3D contour mapping.",
                "",
            )
        ),
        encoding="utf-8",
    )
    print(f"Build identity written: {commit} {CALC_CORE_REVISION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
