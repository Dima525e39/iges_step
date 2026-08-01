# AGENTS.md

## Project

TubeCutCalculator is a PySide6 desktop application for calculating laser cutting
work on tube parts and DXF sheet parts. The main production target is a Windows
EXE built from this repository. macOS builds are useful for local development
and testing.

## Working Rules For Codex

- Read the existing code before changing geometry logic.
- Keep changes scoped to the requested behavior.
- Do not count the 2D unfold boundary as tube cutting length.
- Tube cut length must come from 3D geometry analysis, not from the visual 2D
  unfold frame.
- Tube pierces are counted by connected cut contours, not by raw edge count.
- Each tube end is one pierce.
- For surface-only IGES files, use fallback logic carefully and keep diagnostic
  warnings visible.
- Do not silently commit unrelated local files. In this repository, local
  macOS packaging files may exist and must not be published unless requested.

## Geometry Rules

- Count only real cut contours: `CUT_END` and `CUT_FEATURE`.
- Ignore longitudinal tube edges, profile construction lines, plane/radius
  helper lines, unfold frame lines, and auxiliary visual lines.
- For profile tubes, determine wall thickness from flat walls where possible.
- For round tubes, prefer reliable outer/inner radius detection; use fallback
  only when the model does not expose a clean cylinder.
- For surface-only IGES, small single-edge thickness fragments must not become
  separate pierces. If several tiny shell fragments are part of one missing
  contour, group them as one contour.

## Validation

Useful checks before publishing:

```bash
python3 -m py_compile cad/analyzer.py cad/edge_classifier.py tests/test_file_queue.py
python3 -m unittest discover -q
conda run -n tubecut-occ python main.py --self-test-imports --self-test-output /tmp/tubecut-selftest.txt
```

For Windows release validation, GitHub Actions must pass the packaged EXE
self-test. The EXE self-test should show a real build commit and a known
calculation core.

## GitHub Publishing

- Publish to `main` only when the user asks to publish.
- Stage only intended files.
- Avoid `git add -A` when the worktree contains unrelated local changes.
- After pushing, check the GitHub Actions run and share the run link.

## Neo4j Graph Store

When a task may benefit from prior context, use the `neo4j` MCP server as a
project graph store.

At the start of relevant tasks:

- Check available Neo4j context with `get-schema` and read-only Cypher queries.
- Search for related projects, decisions, files, goals, tasks, and facts before
  making assumptions.

When persisting context:

- Store durable facts, decisions, project relationships, files, goals, and open
  questions.
- Do not store secrets, passwords, API keys, private tokens, or irrelevant chat
  noise.
- Prefer labels such as `Project`, `Thread`, `Goal`, `Decision`, `Fact`,
  `File`, `Task`.
- Prefer relationships such as `MENTIONS`, `DECIDED`, `DEPENDS_ON`,
  `PRODUCED`, `RELATES_TO`.

