# TubeCutCalculator Project Notes

This file is the project-shaped summary of the working dialogs. It keeps the
important context that should survive between Codex sessions without copying the
entire chat history.

## Current Product

TubeCutCalculator is a desktop application for estimating tube laser cutting and
DXF sheet work. The current documented version is `v0.5.5`.

Main capabilities:

- Import STEP / STP / IGES / IGS tube models through OpenCascade.
- Import DXF sheet parts.
- Drag and drop files and folders.
- Show 3D and 2D previews.
- Calculate tube cut length, pierces, quantity, price, and tube purchase.
- Export Excel and PDF documents.
- Save and open project JSON.
- Write `debug_edges.csv` and `debug_faces.csv` for geometry diagnostics.
- Build a Windows EXE locally and through GitHub Actions.

## Important Decisions

- Tube cutting length is calculated from 3D geometry, not from the 2D unfold
  frame.
- The outer border of a tube unfold is not a cut.
- Longitudinal tube edges are not cuts.
- Profile lines and plane/radius helper lines are not cuts.
- Only `CUT_END` and `CUT_FEATURE` edges/contours are included in calculated
  tube cut length.
- Pierces are counted by connected cut contours, not by individual edges.
- Each tube end is one pierce.
- On slanted surface-only tubes, 3D highlighting uses the tube's local oriented
  frame and shows physical outer cut contours. The numeric cut path can be a
  wall/centerline estimate, so it is not reconstructed by summing displayed
  outer perimeters.
- If automatic wall thickness is uncertain, the user can enter thickness
  manually in the calculation table.
- For customer-supplied tube, material/tube purchase cost is excluded from part
  price.
- Local macOS packaging files are development-only unless the user asks to
  publish them.

## Geometry Core Notes

- Shell open-boundary supplementation is only valid for shapes without a
  solid. Solid STEP tubes must use their connected outer cut contours without
  adding stitched or inner shell edges to the cut length.

Primary modules:

- `cad/analyzer.py`: top-level geometry analysis result and profile refinement.
- `cad/edge_classifier.py`: B-Rep/surface edge classification and fallback
  contour grouping.
- `cad/importer.py`: STEP/IGES import, including surface-only IGES handling.
- `cad/debug_edges.py`: writes per-edge diagnostics.
- `cad/debug_faces.py`: writes per-face diagnostics.
- `ui/viewer_3d.py`: 3D display and calculated cut overlay.
- `ui/main_window.py`: file queue, table, analysis actions, export actions.

Rules that have repeatedly mattered:

- For profile tubes with rounded corners, wall thickness should be based on flat
  wall regions, not corner radii.
- For round tubes, diameter and thickness should be based on reliable outer and
  inner cylindrical/radius evidence. Some IGES files are BSpline-only and need
  fallback detection.
- Surface-only IGES files often contain no reliable `solid` and sometimes no
  clean `shell`. They require fallback analysis and visible warnings.
- Heavy IGES files can be slow because OpenCascade import/healing has to rebuild
  topology from surfaces.
- Inventor can sew some IGES surface files quickly; OpenCascade behavior is not
  always identical.

## Recent Surface-Only IGES Fix

Commit `af6e5c0` fixed two issues found on the `ТА 001.006.ХХХ ...` IGES tube
set:

- Slanted surface-only profile tubes now refine their profile from local
  section faces, so they are recognized as `15x15x1.5` instead of as a generic
  volume or an incorrect bounding-box section.
- Tiny single-edge thickness fragments from shell fallback are grouped/filtered
  so they do not become separate pierces.

Reference results after the fix:

| File | Expected pierces | Current result |
| --- | ---: | ---: |
| `ТА 001.006.ХХХ Вертикальная стойка.IGS` | 10 | 10 |
| `ТА 001.006.ХХХ Укосина левая верхняя.IGS` | 4 | 4 |
| `ТА 001.006.ХХХ Укосина левая нижняя.IGS` | 4 | 4 |
| `ТА 001.006.ХХХ Укосина правая верхняя.IGS` | 4 | 4 |
| `ТА 001.006.ХХХ Укосина правая нижняя.IGS` | 4 | 4 |
| `ТА 001.006.ХХХ Центральная вставка.IGS` | 2 | 2 |

Solid STEP references after disabling shell supplementation for solid shapes:

| File | Pierces | Cut length |
| --- | ---: | ---: |
| `Труба 20x20x1,5 L=1196,9-1.stp` | 2 | 181.388 mm |
| `Труба 20x20x1,5 L=1183,5-1.stp` | 4 | 290.007 mm |

## Pergola R4 Roof References

The `100x100x4` slanted surface-only IGES files exposed two related issues:
missing broad-face cut overlays and duplicate tiny shell fragments. The current
logic keeps numeric calculation records separate from the physical outer
contours used for 3D highlighting.

Validated references:

| File | Pierces | Cut length | Highlight validation |
| --- | ---: | ---: | --- |
| `С1_поз.5_100х100х4.IGS` | 39 | 2437.417 mm | all broad-face slots visible |
| `С1_поз.3_100х100х4.IGS` | 49 | 2178.167 mm | broad-face slot row visible |

Longitudinal tube edges remain excluded. For files where a reliable oriented
frame cannot be inferred, the viewer falls back to the calculated edge set.

## Known Diagnostic Files

When geometry is wrong, ask for:

- the original STEP/IGES/DXF file;
- `debug_edges.csv`;
- `debug_faces.csv`;
- a screenshot of the calculation table or diagnostics panel;
- expected cut length and expected pierce count;
- profile type, nominal size, wall thickness, and part length if known.

The CSV files are usually written next to the source CAD file when
`debug_edges.csv` is enabled in the UI.

## Build And Release Notes

Windows:

- Main build script: `build_exe.bat`.
- GitHub Actions workflow: `.github/workflows/build-windows.yml`.
- Packaged EXE must pass `--self-test-imports`.
- The packaged build must include `app_build.py` identity.
- GitHub releases publish only the standard Windows ZIP.
- The standard ZIP contains only `TubeCutCalculator.exe`.
- The GitHub Actions artifact also contains only that ZIP to avoid storing
  duplicate copies of the same executable.

macOS:

- Local macOS app builds may exist in the working tree.
- Do not commit `TubeCutCalculator-macos.spec`, `build_app_macos.sh`, or
  related `.gitignore` changes unless the user explicitly asks to publish macOS
  packaging.

## Pricing And Purchase Logic

Pricing depends on:

- material selected for each row;
- thickness;
- cut length;
- pierce count;
- quantity;
- whether the tube is customer-supplied;
- matching price rules from settings.

Tube purchase logic depends on:

- tube size;
- wall thickness;
- material;
- stock length;
- unusable chuck/remnant length;
- useful stock length after chuck/remnant subtraction;
- quantity of parts.

## UI Notes

Important UI requirements from dialogs:

- The right parameter panel must be scrollable.
- The main window must not open larger than the screen.
- The 3D viewer should support seeing which calculated edges entered the cut
  calculation.
- The old 3D checkboxes were simplified to focus on cut lines and pierces.
- Material and manual thickness changes in the calculation table should
  recalculate only the affected row.

## Dialog-To-Project Workflow

When a future dialog produces durable project knowledge, add it here in one of
these sections:

- `Important Decisions` for settled behavior.
- `Geometry Core Notes` for calculation rules.
- `Reference results` for test models and expected values.
- `Known Diagnostic Files` for what to request during bug reports.
- `Build And Release Notes` for packaging and GitHub Actions behavior.
- `Open Questions` for unresolved design choices.

Avoid copying raw chat messages. Save decisions, facts, file names, expected
values, commands, and links.

## Open Questions

- Whether to add a manual import scale override for suspicious IGES files with
  incorrect internal units.
- Whether to add Inventor-assisted conversion as an optional workflow on
  Windows machines with Inventor installed.
- Whether to convert more surface-only IGES cases into solids before analysis,
  or continue improving surface fallback logic.
- How far to develop DXF true-shape nesting before returning focus to tube
  calculation accuracy.
