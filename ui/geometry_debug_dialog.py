from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cad.analyzer import GeometryAnalysisResult, analyze_shape

if TYPE_CHECKING:
    from core.file_job import FileJob
    from cad.shape_summary import ShapeSummary


DEFAULT_SCRIPT = """# Доступно: shape, job, summary, result, analyze_shape
print("Файл:", job.name if job else "<нет>")
print()
print(result.to_text())

# Пример: получить словарь для быстрой проверки полей
# print(result.as_dict())
"""


class GeometryDebugDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        job: FileJob | None,
        shape: object | None,
        summary: ShapeSummary | None,
        analysis: GeometryAnalysisResult | None,
    ) -> None:
        super().__init__(parent)
        self.job = job
        self.shape = shape
        self.summary = summary
        self.analysis = analysis

        self.setWindowTitle("DEV: Geometry Debug Script")
        self.resize(940, 680)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self._build_ui()
        self._refresh_context_label()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.context_label = QLabel()
        self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlainText(DEFAULT_SCRIPT)
        self.script_edit.setPlaceholderText("Вставьте Python-скрипт для анализа текущей формы")
        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("Здесь появится stdout, stderr или traceback")
        splitter.addWidget(self.script_edit)
        splitter.addWidget(self.output_edit)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([390, 230])
        layout.addWidget(splitter, stretch=1)

        actions = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.reset_button = QPushButton("Reset script")
        self.close_button = QPushButton("Close")
        actions.addWidget(self.run_button)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.run_button.clicked.connect(self.run_script)
        self.reset_button.clicked.connect(self.reset_script)
        self.close_button.clicked.connect(self.close)

    def set_context(
        self,
        *,
        job: FileJob | None,
        shape: object | None,
        summary: ShapeSummary | None,
        analysis: GeometryAnalysisResult | None,
    ) -> None:
        self.job = job
        self.shape = shape
        self.summary = summary
        self.analysis = analysis
        self._refresh_context_label()

    def reset_script(self) -> None:
        self.script_edit.setPlainText(DEFAULT_SCRIPT)

    def run_script(self) -> None:
        output = io.StringIO()
        namespace = self._script_namespace()
        try:
            with redirect_stdout(output), redirect_stderr(output):
                exec(self.script_edit.toPlainText(), namespace, namespace)
        except Exception:
            traceback.print_exc(file=output)

        text = output.getvalue().strip()
        if not text:
            text = "Скрипт выполнен без вывода."
        self.output_edit.setPlainText(text)

    def _script_namespace(self) -> dict[str, object]:
        result = self.analysis
        if result is None and (self.shape is not None or self.summary is not None):
            result = analyze_shape(self.shape, summary=self.summary)
        return {
            "shape": self.shape,
            "job": self.job,
            "summary": self.summary,
            "result": result,
            "analysis": result,
            "analyze_shape": analyze_shape,
        }

    def _refresh_context_label(self) -> None:
        file_name = self.job.name if self.job is not None else "<нет файла>"
        state = "модель загружена" if self.shape is not None else "модель не загружена"
        self.context_label.setText(
            f"DEV-инструмент: скрипт выполняется внутри программы. "
            f"Текущий файл: {file_name}; {state}."
        )
