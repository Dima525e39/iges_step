from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.file_job import FileJob


def _wheel_zoom_factor(delta_y: int) -> float:
    if delta_y == 0:
        return 1.0
    return 1.25 ** (delta_y / 120.0)


def _event_xy(event: object) -> tuple[int, int]:
    position_getter = getattr(event, "position", None)
    if position_getter is not None:
        position = position_getter()
    else:
        position = event.pos()
    return int(position.x()), int(position.y())


def _wheel_delta_y(event: object) -> int:
    angle_delta = event.angleDelta()
    delta_y = angle_delta.y()
    if delta_y != 0:
        return delta_y

    pixel_delta_getter = getattr(event, "pixelDelta", None)
    if pixel_delta_getter is None:
        return 0
    return pixel_delta_getter().y()


def _zoom_drag_delta(zoom_factor: float) -> int:
    if zoom_factor > 1.0:
        return max(1, int(round((zoom_factor - 1.0) * 100.0)))
    if zoom_factor < 1.0:
        return min(-1, -int(round(((1.0 / zoom_factor) - 1.0) * 100.0)))
    return 0


class Viewer3D(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._canvas = None
        self._display = None

        self.label = QLabel("Модель не загружена")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        self.layers_panel = QWidget()
        self.layers_panel.setObjectName("LayersPanel")
        layers_layout = QHBoxLayout(self.layers_panel)
        layers_layout.setContentsMargins(6, 4, 6, 4)
        self.cut_lines_layer = QCheckBox("Линии реза")
        self.cut_lines_layer.setChecked(True)
        self.pierces_layer = QCheckBox("Врезки")
        self.pierces_layer.setChecked(True)
        self.ends_layer = QCheckBox("Торцы")
        self.ends_layer.setChecked(True)
        self.ignored_layer = QCheckBox("Игнорированные")
        self.plane_radius_layer = QCheckBox("Плоскость/радиус")
        self.uncertain_layer = QCheckBox("Спорные")
        self.dimensions_layer = QCheckBox("Размеры")
        self.cut_only_layer = QCheckBox("Только линии реза")
        for checkbox in (
            self.cut_lines_layer,
            self.pierces_layer,
            self.ends_layer,
            self.ignored_layer,
            self.plane_radius_layer,
            self.uncertain_layer,
            self.dimensions_layer,
            self.cut_only_layer,
        ):
            layers_layout.addWidget(checkbox)
        layers_layout.addStretch(1)
        self.cut_only_layer.toggled.connect(self._toggle_cut_only_mode)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.layers_panel)
        self._layout.addWidget(self.label)

    def show_job(self, job: FileJob | None) -> None:
        if job is None:
            self.show_message("Модель не загружена")
            return
        self.show_message(f"{job.name}\nИмпортируйте файл, чтобы открыть 3D-просмотр.")

    def show_shape(self, shape: object, title: str = "") -> None:
        if not self._ensure_occ_canvas():
            return

        try:
            self._display.EraseAll()
            self._display.DisplayShape(shape, update=True)
            self._disable_selection_mode()
            self.label.hide()
            self._canvas.show()
            # The canvas is created lazily and may not have its final size yet
            # when the first shape is displayed, so a single FitAll() here would
            # frame the model against a tiny viewport and render it minuscule.
            # Fit immediately and again after the layout settles.
            self._fit_view()
            QTimer.singleShot(0, self._fit_view)
            QTimer.singleShot(120, self._fit_view)
        except Exception as exc:
            name = f"{title}\n" if title else ""
            self.show_message(f"{name}Не удалось показать 3D-модель:\n{exc}")

    def _fit_view(self) -> None:
        if self._display is None or self._canvas is None or not self._canvas.isVisible():
            return
        try:
            self._display.FitAll()
            view = getattr(self._display, "View", None)
            if view is not None and hasattr(view, "ZFitAll"):
                view.ZFitAll()
        except Exception:
            pass

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        # Re-frame the model when the viewer is resized (e.g. the window is
        # maximised) so it always fills the available space.
        if self._canvas is not None and self._canvas.isVisible():
            QTimer.singleShot(0, self._fit_view)

    def show_message(self, message: str) -> None:
        if self._canvas is not None:
            self._canvas.hide()
        self.label.setText(message)
        self.label.show()

    def _ensure_occ_canvas(self) -> bool:
        if self._canvas is not None and self._display is not None:
            return True

        try:
            from OCC.Display.backend import load_backend

            load_backend("pyside6")
            from OCC.Display.qtDisplay import qtViewer3d

            class TubeCutViewer3d(qtViewer3d):
                def wheelEvent(self, event: object) -> None:
                    delta_y = _wheel_delta_y(event)
                    zoom_factor = _wheel_zoom_factor(delta_y)
                    if zoom_factor == 1.0:
                        event.accept()
                        return

                    x, y = _event_xy(event)
                    if self._zoom_at_cursor(x, y, zoom_factor):
                        event.accept()
                        return

                    self._display.ZoomFactor(zoom_factor)
                    event.accept()

                def mouseReleaseEvent(self, event: object) -> None:
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._select_area = False
                        self._drawbox = False
                        self._clear_selection_highlight()
                        self.cursor = "arrow"
                        event.accept()
                        return

                    super().mouseReleaseEvent(event)

                def mouseMoveEvent(self, event: object) -> None:
                    super().mouseMoveEvent(event)
                    if not event.buttons():
                        self._clear_selection_highlight()

                def _zoom_at_cursor(self, x: int, y: int, zoom_factor: float) -> bool:
                    view = getattr(self._display, "View", None)
                    if view is None:
                        return False

                    try:
                        if hasattr(view, "StartZoomAtPoint") and hasattr(view, "ZoomAtPoint"):
                            drag_delta = _zoom_drag_delta(zoom_factor)
                            view.StartZoomAtPoint(x, y)
                            view.ZoomAtPoint(x, y, x, y + drag_delta)
                            return True
                        if hasattr(view, "Place"):
                            view.Place(x, y, zoom_factor)
                            return True
                    except Exception:
                        return False

                    return False

                def _clear_selection_highlight(self) -> None:
                    context = getattr(self._display, "Context", None)
                    if context is not None:
                        for method_name in ("ClearSelected", "ClearDetected"):
                            method = getattr(context, method_name, None)
                            if method is None:
                                continue
                            try:
                                method(True)
                            except Exception:
                                pass
                    if hasattr(self._display, "selected_shapes"):
                        self._display.selected_shapes = []

            self._canvas = TubeCutViewer3d(self)
            self._canvas.InitDriver()
            self._display = self._canvas._display
            self._layout.addWidget(self._canvas, stretch=1)
            return True
        except Exception as exc:
            self.show_message(
                "3D-просмотрщик недоступен.\n"
                "Установите окружение из environment.yml и pythonocc-core.\n"
                f"{exc}"
            )
            return False

    def _disable_selection_mode(self) -> None:
        context = getattr(self._display, "Context", None)
        if context is None:
            return

        try:
            context.Deactivate()
        except Exception:
            pass

    def _toggle_cut_only_mode(self, enabled: bool) -> None:
        for checkbox in (
            self.pierces_layer,
            self.ends_layer,
            self.ignored_layer,
            self.plane_radius_layer,
            self.uncertain_layer,
            self.dimensions_layer,
        ):
            checkbox.setEnabled(not enabled)
