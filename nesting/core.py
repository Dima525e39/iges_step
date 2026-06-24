from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from cad.sheet_analyzer import SheetAnalysisResult, SheetContour, SheetPoint

ProgressCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


class NestingCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NestingPart:
    name: str
    width_mm: float
    height_mm: float
    contours: tuple[SheetContour, ...]
    quantity: int = 1

    @classmethod
    def from_sheet_analysis(
        cls,
        *,
        name: str,
        analysis: SheetAnalysisResult,
        quantity: int = 1,
    ) -> "NestingPart":
        return cls(
            name=name,
            width_mm=analysis.width_mm,
            height_mm=analysis.height_mm,
            contours=analysis.contours,
            quantity=max(1, int(quantity)),
        )


@dataclass(frozen=True, slots=True)
class NestingPlacement:
    part: NestingPart
    sheet_index: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotation_deg: float


@dataclass(frozen=True, slots=True)
class NestingSheet:
    index: int
    width_mm: float
    height_mm: float
    placements: tuple[NestingPlacement, ...]

    @property
    def used_area_mm2(self) -> float:
        return sum(abs(_polygon_area(_placement_outer_polygon(item))) for item in self.placements)

    @property
    def efficiency(self) -> float:
        total = self.width_mm * self.height_mm
        if total <= 0.0:
            return 0.0
        return self.used_area_mm2 / total


@dataclass(frozen=True, slots=True)
class NestingLayout:
    sheet_width_mm: float
    sheet_height_mm: float
    spacing_mm: float
    sheets: tuple[NestingSheet, ...]
    warnings: tuple[str, ...] = ()

    @property
    def placements(self) -> tuple[NestingPlacement, ...]:
        return tuple(item for sheet in self.sheets for item in sheet.placements)

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)


@dataclass(slots=True)
class _Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


@dataclass(slots=True)
class _PartInstance:
    part: NestingPart
    index: int

    @property
    def sort_key(self) -> tuple[float, float, float, str, int]:
        area = self.part.width_mm * self.part.height_mm
        longest = max(self.part.width_mm, self.part.height_mm)
        shortest = min(self.part.width_mm, self.part.height_mm)
        return (-area, -longest, -shortest, self.part.name, self.index)


class MaxRectsNestingEngine:
    """Rectangle nesting around true contours, suitable as a first smart core.

    The engine packs each contour by its 2D bounding rectangle and preserves the
    original vectors for preview/export. It uses a MaxRects free-space list with
    best short-side fit and bottom-left tie breakers.
    """

    def nest(
        self,
        parts: tuple[NestingPart, ...] | list[NestingPart],
        *,
        sheet_width_mm: float,
        sheet_height_mm: float,
        spacing_mm: float = 3.0,
        allow_rotation: bool = True,
        rotation_step_degrees: float = 90.0,
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> NestingLayout:
        warnings: list[str] = []
        sheet_width = max(1.0, float(sheet_width_mm))
        sheet_height = max(1.0, float(sheet_height_mm))
        spacing = max(0.0, float(spacing_mm))
        instances = sorted(_expand_parts(parts), key=lambda item: item.sort_key)
        free_by_sheet: list[list[_Rect]] = [[_Rect(0.0, 0.0, sheet_width, sheet_height)]]
        placements_by_sheet: list[list[NestingPlacement]] = [[]]

        for index, instance in enumerate(instances, start=1):
            _check_cancelled(should_cancel)
            _emit_progress(
                progress_callback,
                f"Размещение {index}/{len(instances)}: {instance.part.name}",
            )
            placed = False
            for sheet_index, free_rectangles in enumerate(free_by_sheet):
                placement, used_rect = _find_best_position(
                    instance.part,
                    free_rectangles,
                    sheet_index=sheet_index,
                    spacing_mm=spacing,
                    allow_rotation=allow_rotation,
                    rotation_step_degrees=rotation_step_degrees,
                )
                if placement is None or used_rect is None:
                    continue
                placements_by_sheet[sheet_index].append(placement)
                free_by_sheet[sheet_index] = _split_free_rectangles(
                    free_rectangles,
                    used_rect,
                )
                placed = True
                break

            if placed:
                continue

            free_rectangles = [_Rect(0.0, 0.0, sheet_width, sheet_height)]
            sheet_index = len(free_by_sheet)
            placement, used_rect = _find_best_position(
                instance.part,
                free_rectangles,
                sheet_index=sheet_index,
                spacing_mm=spacing,
                allow_rotation=allow_rotation,
                rotation_step_degrees=rotation_step_degrees,
            )
            if placement is None or used_rect is None:
                warnings.append(
                    f"Деталь {instance.part.name} не помещается на лист "
                    f"{sheet_width:.1f} x {sheet_height:.1f} мм."
                )
                continue
            free_by_sheet.append(
                _split_free_rectangles(
                    free_rectangles,
                    used_rect,
                )
            )
            placements_by_sheet.append([placement])

        sheets = tuple(
            NestingSheet(
                index=index,
                width_mm=sheet_width,
                height_mm=sheet_height,
                placements=tuple(placements),
            )
            for index, placements in enumerate(placements_by_sheet)
            if placements
        )
        return NestingLayout(
            sheet_width_mm=sheet_width,
            sheet_height_mm=sheet_height,
            spacing_mm=spacing,
            sheets=sheets,
            warnings=tuple(warnings),
        )


class TrueShapeNestingEngine:
    """Bottom-left true-shape nesting with polygon collision checks.

    This is the first production-facing step beyond rectangle-only packing:
    candidates are still generated from bounding boxes, but acceptance is based
    on the transformed outer contours, segment intersections, containment, and
    segment-to-segment spacing.
    """

    def nest(
        self,
        parts: tuple[NestingPart, ...] | list[NestingPart],
        *,
        sheet_width_mm: float,
        sheet_height_mm: float,
        spacing_mm: float = 3.0,
        allow_rotation: bool = True,
        rotation_step_degrees: float = 90.0,
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> NestingLayout:
        warnings: list[str] = []
        sheet_width = max(1.0, float(sheet_width_mm))
        sheet_height = max(1.0, float(sheet_height_mm))
        spacing = max(0.0, float(spacing_mm))
        instances = sorted(_expand_parts(parts), key=lambda item: item.sort_key)
        placements_by_sheet: list[list[NestingPlacement]] = [[]]

        for index, instance in enumerate(instances, start=1):
            _check_cancelled(should_cancel)
            _emit_progress(
                progress_callback,
                f"True-shape {index}/{len(instances)}: {instance.part.name}",
            )
            placement = _find_true_shape_position(
                instance.part,
                placements_by_sheet,
                sheet_width_mm=sheet_width,
                sheet_height_mm=sheet_height,
                spacing_mm=spacing,
                allow_rotation=allow_rotation,
                rotation_step_degrees=rotation_step_degrees,
                should_cancel=should_cancel,
            )
            if placement is None:
                sheet_index = len(placements_by_sheet)
                placement = _find_true_shape_position_on_sheet(
                    instance.part,
                    (),
                    sheet_index=sheet_index,
                    sheet_width_mm=sheet_width,
                    sheet_height_mm=sheet_height,
                    spacing_mm=spacing,
                    allow_rotation=allow_rotation,
                    rotation_step_degrees=rotation_step_degrees,
                    should_cancel=should_cancel,
                )
                if placement is None:
                    warnings.append(
                        f"Деталь {instance.part.name} не помещается на лист "
                        f"{sheet_width:.1f} x {sheet_height:.1f} мм."
                    )
                    continue
                placements_by_sheet.append([placement])
                continue
            placements_by_sheet[placement.sheet_index].append(placement)

        sheets = tuple(
            NestingSheet(
                index=index,
                width_mm=sheet_width,
                height_mm=sheet_height,
                placements=tuple(placements),
            )
            for index, placements in enumerate(placements_by_sheet)
            if placements
        )
        return NestingLayout(
            sheet_width_mm=sheet_width,
            sheet_height_mm=sheet_height,
            spacing_mm=spacing,
            sheets=sheets,
            warnings=tuple(warnings),
        )


def transformed_contours(placement: NestingPlacement) -> tuple[SheetContour, ...]:
    contours: list[SheetContour] = []
    for contour in placement.part.contours:
        points = tuple(_transform_point(point, placement) for point in contour.points)
        contours.append(
            SheetContour(
                points=points,
                length_mm=contour.length_mm,
                component_id=contour.component_id,
                is_outer=contour.is_outer,
            )
        )
    return tuple(contours)


def _expand_parts(parts: tuple[NestingPart, ...] | list[NestingPart]) -> tuple[_PartInstance, ...]:
    instances: list[_PartInstance] = []
    for part in parts:
        for index in range(max(1, int(part.quantity))):
            instances.append(_PartInstance(part=part, index=index))
    return tuple(instances)


def _find_best_position(
    part: NestingPart,
    free_rectangles: list[_Rect],
    *,
    sheet_index: int,
    spacing_mm: float,
    allow_rotation: bool,
    rotation_step_degrees: float,
) -> tuple[NestingPlacement | None, _Rect | None]:
    options = _rotation_options(
        part,
        allow_rotation=allow_rotation,
        step_degrees=rotation_step_degrees,
    )

    best: tuple[tuple[float, float, float, float], NestingPlacement, _Rect] | None = None
    for rotation, width, height in options:
        packed_width = width + spacing_mm
        packed_height = height + spacing_mm
        for free in free_rectangles:
            if packed_width > free.width + 0.001 or packed_height > free.height + 0.001:
                continue
            placement_x = free.x + spacing_mm / 2.0
            placement_y = free.y + spacing_mm / 2.0
            used = _Rect(free.x, free.y, packed_width, packed_height)
            short_side = min(free.width - packed_width, free.height - packed_height)
            long_side = max(free.width - packed_width, free.height - packed_height)
            score = (short_side, long_side, placement_y, placement_x)
            placement = NestingPlacement(
                part=part,
                sheet_index=sheet_index,
                x_mm=placement_x,
                y_mm=placement_y,
                width_mm=width,
                height_mm=height,
                rotation_deg=rotation,
            )
            if best is None or score < best[0]:
                best = (score, placement, used)
    if best is None:
        return None, None
    return best[1], best[2]


def _find_true_shape_position(
    part: NestingPart,
    placements_by_sheet: list[list[NestingPlacement]],
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
    spacing_mm: float,
    allow_rotation: bool,
    rotation_step_degrees: float,
    should_cancel: CancelCallback | None = None,
) -> NestingPlacement | None:
    for sheet_index, placements in enumerate(placements_by_sheet):
        _check_cancelled(should_cancel)
        placement = _find_true_shape_position_on_sheet(
            part,
            tuple(placements),
            sheet_index=sheet_index,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            spacing_mm=spacing_mm,
            allow_rotation=allow_rotation,
            rotation_step_degrees=rotation_step_degrees,
            should_cancel=should_cancel,
        )
        if placement is not None:
            return placement
    return None


def _find_true_shape_position_on_sheet(
    part: NestingPart,
    existing_placements: tuple[NestingPlacement, ...],
    *,
    sheet_index: int,
    sheet_width_mm: float,
    sheet_height_mm: float,
    spacing_mm: float,
    allow_rotation: bool,
    rotation_step_degrees: float,
    should_cancel: CancelCallback | None = None,
) -> NestingPlacement | None:
    options = _rotation_options(
        part,
        allow_rotation=allow_rotation,
        step_degrees=rotation_step_degrees,
        full_turn=True,
    )
    best: tuple[tuple[float, float, float, float], NestingPlacement] | None = None
    existing_polygons = tuple(_placement_outer_polygon(item) for item in existing_placements)

    for rotation, width, height in options:
        _check_cancelled(should_cancel)
        if width > sheet_width_mm + 0.001 or height > sheet_height_mm + 0.001:
            continue
        for x, y in _true_shape_candidate_positions(
            existing_placements,
            existing_polygons,
            width=width,
            height=height,
            sheet_width_mm=sheet_width_mm,
            sheet_height_mm=sheet_height_mm,
            spacing_mm=spacing_mm,
        ):
            _check_cancelled(should_cancel)
            placement = NestingPlacement(
                part=part,
                sheet_index=sheet_index,
                x_mm=x,
                y_mm=y,
                width_mm=width,
                height_mm=height,
                rotation_deg=rotation,
            )
            if not _placement_inside_sheet(
                placement,
                sheet_width_mm=sheet_width_mm,
                sheet_height_mm=sheet_height_mm,
            ):
                continue
            polygon = _placement_outer_polygon(placement)
            if any(
                _polygons_conflict(
                    polygon,
                    existing,
                    spacing_mm=spacing_mm,
                    should_cancel=should_cancel,
                )
                for existing in existing_polygons
            ):
                continue
            score = (
                y,
                x,
                _bbox_waste(width, height, polygon),
                abs(rotation),
            )
            if best is None or score < best[0]:
                best = (score, placement)

    return best[1] if best is not None else None


def _emit_progress(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _check_cancelled(callback: CancelCallback | None) -> None:
    if callback is not None and callback():
        raise NestingCancelled("Nesting calculation was cancelled.")


def _true_shape_candidate_positions(
    existing_placements: tuple[NestingPlacement, ...],
    existing_polygons: tuple[tuple[SheetPoint, ...], ...],
    *,
    width: float,
    height: float,
    sheet_width_mm: float,
    sheet_height_mm: float,
    spacing_mm: float,
) -> tuple[tuple[float, float], ...]:
    x_values = {0.0}
    y_values = {0.0}
    for placement, polygon in zip(existing_placements, existing_polygons, strict=True):
        x_values.update(
            (
                placement.x_mm,
                placement.x_mm + placement.width_mm + spacing_mm,
                placement.x_mm - width - spacing_mm,
            )
        )
        y_values.update(
            (
                placement.y_mm,
                placement.y_mm + placement.height_mm + spacing_mm,
                placement.y_mm - height - spacing_mm,
            )
        )
        for point in polygon:
            x_values.update((point.x_mm, point.x_mm - width, point.x_mm + spacing_mm))
            y_values.update((point.y_mm, point.y_mm - height, point.y_mm + spacing_mm))

    candidates: set[tuple[int, int]] = set()
    result: list[tuple[float, float]] = []
    for y in sorted(y_values):
        for x in sorted(x_values):
            if x < -0.001 or y < -0.001:
                continue
            if x + width > sheet_width_mm + 0.001 or y + height > sheet_height_mm + 0.001:
                continue
            key = (round(x * 1000), round(y * 1000))
            if key in candidates:
                continue
            candidates.add(key)
            result.append((max(0.0, x), max(0.0, y)))
    return tuple(result)


def _split_free_rectangles(
    free_rectangles: list[_Rect],
    used: _Rect,
) -> list[_Rect]:
    result: list[_Rect] = []
    for free in free_rectangles:
        if not _intersects(free, used):
            result.append(free)
            continue
        if used.x > free.x:
            result.append(_Rect(free.x, free.y, used.x - free.x, free.height))
        if used.right < free.right:
            result.append(_Rect(used.right, free.y, free.right - used.right, free.height))
        if used.y > free.y:
            result.append(_Rect(free.x, free.y, free.width, used.y - free.y))
        if used.bottom < free.bottom:
            result.append(_Rect(free.x, used.bottom, free.width, free.bottom - used.bottom))
    return _prune_free_rectangles(
        [rect for rect in result if rect.width > 0.001 and rect.height > 0.001]
    )


def _prune_free_rectangles(rectangles: list[_Rect]) -> list[_Rect]:
    pruned: list[_Rect] = []
    for index, rect in enumerate(rectangles):
        if any(
            index != other_index and _contains(other, rect)
            for other_index, other in enumerate(rectangles)
        ):
            continue
        pruned.append(rect)
    pruned.sort(key=lambda item: (item.y, item.x, item.area))
    return pruned


def _intersects(first: _Rect, second: _Rect) -> bool:
    return not (
        second.x >= first.right
        or second.right <= first.x
        or second.y >= first.bottom
        or second.bottom <= first.y
    )


def _contains(outer: _Rect, inner: _Rect) -> bool:
    return (
        inner.x >= outer.x - 0.001
        and inner.y >= outer.y - 0.001
        and inner.right <= outer.right + 0.001
        and inner.bottom <= outer.bottom + 0.001
    )


def _transform_point(point: SheetPoint, placement: NestingPlacement) -> SheetPoint:
    if abs(placement.rotation_deg) > 0.001:
        bounds = _rotated_bounds(
            placement.part.width_mm,
            placement.part.height_mm,
            placement.rotation_deg,
        )
        radians = math.radians(placement.rotation_deg)
        cos_angle = math.cos(radians)
        sin_angle = math.sin(radians)
        rotated_x = point.x_mm * cos_angle - point.y_mm * sin_angle
        rotated_y = point.x_mm * sin_angle + point.y_mm * cos_angle
        return SheetPoint(
            x_mm=placement.x_mm + rotated_x - bounds.x,
            y_mm=placement.y_mm + rotated_y - bounds.y,
        )
    return SheetPoint(
        x_mm=placement.x_mm + point.x_mm,
        y_mm=placement.y_mm + point.y_mm,
    )


def _rotation_options(
    part: NestingPart,
    *,
    allow_rotation: bool,
    step_degrees: float,
    full_turn: bool = False,
) -> tuple[tuple[float, float, float], ...]:
    if not allow_rotation:
        return ((0.0, part.width_mm, part.height_mm),)

    step = max(1.0, min(180.0, float(step_degrees or 90.0)))
    angle_limit = 360.0 if full_turn else 180.0
    angles: list[float] = []
    angle = 0.0
    while angle < angle_limit - 0.001:
        angles.append(round(angle, 6))
        angle += step
    if not any(abs(angle - 90.0) <= 0.001 for angle in angles):
        angles.append(90.0)

    options: list[tuple[float, float, float]] = []
    seen: set[tuple[int, int]] = set()
    for angle in sorted(angles):
        bounds = _rotated_bounds(part.width_mm, part.height_mm, angle)
        key = (round(bounds.width * 1000), round(bounds.height * 1000))
        if not full_turn and key in seen:
            continue
        seen.add(key)
        options.append((angle, bounds.width, bounds.height))
    return tuple(options)


def _rotated_bounds(width: float, height: float, rotation_deg: float) -> _Rect:
    radians = math.radians(rotation_deg)
    cos_angle = math.cos(radians)
    sin_angle = math.sin(radians)
    points = (
        (0.0, 0.0),
        (width, 0.0),
        (width, height),
        (0.0, height),
    )
    rotated = tuple(
        (x * cos_angle - y * sin_angle, x * sin_angle + y * cos_angle)
        for x, y in points
    )
    min_x = min(x for x, _ in rotated)
    min_y = min(y for _, y in rotated)
    max_x = max(x for x, _ in rotated)
    max_y = max(y for _, y in rotated)
    return _Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def _placement_inside_sheet(
    placement: NestingPlacement,
    *,
    sheet_width_mm: float,
    sheet_height_mm: float,
) -> bool:
    polygon = _placement_outer_polygon(placement)
    return all(
        -0.001 <= point.x_mm <= sheet_width_mm + 0.001
        and -0.001 <= point.y_mm <= sheet_height_mm + 0.001
        for point in polygon
    )


def _placement_outer_polygon(placement: NestingPlacement) -> tuple[SheetPoint, ...]:
    contour = _outer_contour(placement.part)
    points = tuple(_transform_point(point, placement) for point in contour.points)
    return _closed_polygon(points)


def _outer_contour(part: NestingPart) -> SheetContour:
    outer = [contour for contour in part.contours if contour.is_outer and len(contour.points) >= 3]
    if not outer:
        outer = [contour for contour in part.contours if len(contour.points) >= 3]
    if outer:
        return max(outer, key=lambda contour: abs(_polygon_area(contour.points)))
    return SheetContour(
        points=(
            SheetPoint(0.0, 0.0),
            SheetPoint(part.width_mm, 0.0),
            SheetPoint(part.width_mm, part.height_mm),
            SheetPoint(0.0, part.height_mm),
            SheetPoint(0.0, 0.0),
        ),
        length_mm=2.0 * (part.width_mm + part.height_mm),
        component_id=0,
        is_outer=True,
    )


def _closed_polygon(points: tuple[SheetPoint, ...]) -> tuple[SheetPoint, ...]:
    if len(points) < 2:
        return points
    first = points[0]
    last = points[-1]
    if _point_distance(first, last) <= 0.001:
        return points
    return (*points, first)


def _polygons_conflict(
    first: tuple[SheetPoint, ...],
    second: tuple[SheetPoint, ...],
    *,
    spacing_mm: float,
    should_cancel: CancelCallback | None = None,
) -> bool:
    if not _rectangles_close(_polygon_bounds(first), _polygon_bounds(second), spacing_mm):
        return False

    first_segments = tuple(zip(first, first[1:], strict=False))
    second_segments = tuple(zip(second, second[1:], strict=False))
    for first_start, first_end in first_segments:
        _check_cancelled(should_cancel)
        for second_start, second_end in second_segments:
            _check_cancelled(should_cancel)
            if _segments_intersect(first_start, first_end, second_start, second_end):
                return True
            if spacing_mm > 0.0 and _segment_distance(
                first_start,
                first_end,
                second_start,
                second_end,
            ) < spacing_mm - 0.001:
                return True

    if first and _point_in_polygon(first[0], second):
        return True
    if second and _point_in_polygon(second[0], first):
        return True
    return False


def _bbox_waste(width: float, height: float, polygon: tuple[SheetPoint, ...]) -> float:
    return max(0.0, width * height - abs(_polygon_area(polygon)))


def _polygon_bounds(points: tuple[SheetPoint, ...]) -> _Rect:
    min_x = min(point.x_mm for point in points)
    min_y = min(point.y_mm for point in points)
    max_x = max(point.x_mm for point in points)
    max_y = max(point.y_mm for point in points)
    return _Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def _rectangles_close(first: _Rect, second: _Rect, spacing_mm: float) -> bool:
    spacing = max(0.0, spacing_mm)
    return not (
        first.right + spacing <= second.x
        or second.right + spacing <= first.x
        or first.bottom + spacing <= second.y
        or second.bottom + spacing <= first.y
    )


def _polygon_area(points: tuple[SheetPoint, ...]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for start, end in zip(points, points[1:], strict=False):
        area += start.x_mm * end.y_mm - end.x_mm * start.y_mm
    return area / 2.0


def _segments_intersect(
    a: SheetPoint,
    b: SheetPoint,
    c: SheetPoint,
    d: SheetPoint,
) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if o1 * o2 < -0.000001 and o3 * o4 < -0.000001:
        return True
    return (
        abs(o1) <= 0.000001 and _point_on_segment(c, a, b)
        or abs(o2) <= 0.000001 and _point_on_segment(d, a, b)
        or abs(o3) <= 0.000001 and _point_on_segment(a, c, d)
        or abs(o4) <= 0.000001 and _point_on_segment(b, c, d)
    )


def _orientation(a: SheetPoint, b: SheetPoint, c: SheetPoint) -> float:
    return (b.x_mm - a.x_mm) * (c.y_mm - a.y_mm) - (b.y_mm - a.y_mm) * (c.x_mm - a.x_mm)


def _point_on_segment(point: SheetPoint, start: SheetPoint, end: SheetPoint) -> bool:
    return (
        min(start.x_mm, end.x_mm) - 0.001 <= point.x_mm <= max(start.x_mm, end.x_mm) + 0.001
        and min(start.y_mm, end.y_mm) - 0.001 <= point.y_mm <= max(start.y_mm, end.y_mm) + 0.001
    )


def _point_in_polygon(point: SheetPoint, polygon: tuple[SheetPoint, ...]) -> bool:
    inside = False
    for start, end in zip(polygon, polygon[1:], strict=False):
        if _point_on_segment(point, start, end):
            return True
        crosses = (start.y_mm > point.y_mm) != (end.y_mm > point.y_mm)
        if not crosses:
            continue
        x_at_y = (end.x_mm - start.x_mm) * (point.y_mm - start.y_mm) / (
            end.y_mm - start.y_mm
        ) + start.x_mm
        if point.x_mm < x_at_y:
            inside = not inside
    return inside


def _segment_distance(
    a: SheetPoint,
    b: SheetPoint,
    c: SheetPoint,
    d: SheetPoint,
) -> float:
    return min(
        _point_to_segment_distance(a, c, d),
        _point_to_segment_distance(b, c, d),
        _point_to_segment_distance(c, a, b),
        _point_to_segment_distance(d, a, b),
    )


def _point_to_segment_distance(point: SheetPoint, start: SheetPoint, end: SheetPoint) -> float:
    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.000001:
        return _point_distance(point, start)
    t = ((point.x_mm - start.x_mm) * dx + (point.y_mm - start.y_mm) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    projection = SheetPoint(start.x_mm + t * dx, start.y_mm + t * dy)
    return _point_distance(point, projection)


def _point_distance(first: SheetPoint, second: SheetPoint) -> float:
    return math.hypot(first.x_mm - second.x_mm, first.y_mm - second.y_mm)
