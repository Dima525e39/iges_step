from __future__ import annotations

from pathlib import Path


def local_paths_from_mime_data(mime_data: object) -> list[str]:
    if not hasattr(mime_data, "hasUrls") or not mime_data.hasUrls():
        return []

    paths: list[str] = []
    for url in mime_data.urls():
        if url.isLocalFile():
            paths.append(str(Path(url.toLocalFile())))
    return paths
