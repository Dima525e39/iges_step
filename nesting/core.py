from __future__ import annotations

from dataclasses import dataclass

from cad.sheet_analyzer import SheetAnalysisResult, SheetContour, SheetPoint


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
    rotation_deg: int


@dataclass(frozen=True, slots=True)
class NestingSheet:
    index: int
    width_mm: float
    height_mm: float
    placements: tuple[NestingPlacement, ...]

    @property
    def used_area_mm2(self) -> float:
        return sum(item.width_mm * item.height_mm for item in self.placements)

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
    ) -> NestingLayout:
        warnings: list[str] = []
        sheet_width = max(1.0, float(sheet_width_mm))
        sheet_height = max(1.0, float(sheet_height_mm))
        spacing = max(0.0, float(spacing_mm))
        instances = sorted(_expand_parts(parts), key=lambda item: item.sort_key)
        free_by_sheet: list[list[_Rect]] = [[_Rect(0.0, 0.0, sheet_width, sheet_height)]]
        placements_by_sheet: list[list[NestingPlacement]] = [[]]

        for instance in instances:
            placed = False
            for sheet_index, free_rectangles in enumerate(free_by_sheet):
                placement, used_rect = _find_best_position(
                    instance.part,
                    free_rectangles,
                    sheet_index=sheet_index,
                    spacing_mm=spacing,
                    allow_rotation=allow_rotation,
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
) -> tuple[NestingPlacement | None, _Rect | None]:
    options = [(0, part.width_mm, part.height_mm)]
    if allow_rotation and abs(part.width_mm - part.height_mm) > 0.001:
        options.append((90, part.height_mm, part.width_mm))

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
    if placement.rotation_deg == 90:
        return SheetPoint(
            x_mm=placement.x_mm + point.y_mm,
            y_mm=placement.y_mm + placement.part.width_mm - point.x_mm,
        )
    return SheetPoint(
        x_mm=placement.x_mm + point.x_mm,
        y_mm=placement.y_mm + point.y_mm,
    )
