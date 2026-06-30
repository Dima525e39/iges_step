from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


STEP_TRANSLATOR_ID = "{90AF7F40-0C01-11D5-8E83-0010B541CD80}"
K_FILE_BROWSE_IO_MECHANISM = 13059


class InventorConversionError(RuntimeError):
    """Raised when Autodesk Inventor cannot convert a CAD file."""


@dataclass(frozen=True, slots=True)
class InventorConversionResult:
    source_path: Path
    step_path: Path
    warnings: tuple[str, ...] = ()


def convert_iges_to_step(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    visible: bool = False,
) -> InventorConversionResult:
    source = Path(source_path).expanduser().resolve()
    target_dir = Path(output_dir).expanduser().resolve()
    if source.suffix.casefold() not in {".iges", ".igs"}:
        raise InventorConversionError("Конвертация через Inventor доступна только для IGES / IGS.")
    if not source.exists():
        raise InventorConversionError(f"Файл не найден: {source}")
    if sys.platform != "win32":
        raise InventorConversionError("Autodesk Inventor COM доступен только в Windows.")

    target_dir.mkdir(parents=True, exist_ok=True)
    step_path = target_dir / f"{source.stem}_inventor.stp"

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise InventorConversionError(
            "pywin32 не установлен; конвертация через Inventor недоступна."
        ) from exc

    pythoncom.CoInitialize()
    document = None
    try:
        try:
            inventor = win32com.client.Dispatch("Inventor.Application")
        except Exception as exc:
            raise InventorConversionError(
                "Autodesk Inventor не найден или COM-сервер не запустился."
            ) from exc

        try:
            inventor.Visible = bool(visible)
        except Exception:
            pass

        try:
            document = inventor.Documents.Open(str(source), False)
        except Exception as exc:
            raise InventorConversionError(f"Inventor не смог открыть IGES: {source.name}") from exc

        try:
            document.SaveAs(str(step_path), True)
        except Exception:
            _save_step_with_translator(inventor, document, step_path)

        if not step_path.exists() or step_path.stat().st_size <= 0:
            raise InventorConversionError("Inventor не создал STEP-файл после конвертации.")
    finally:
        if document is not None:
            try:
                document.Close(True)
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    return InventorConversionResult(
        source_path=source,
        step_path=step_path,
        warnings=(
            "IGES предварительно конвертирован через Autodesk Inventor в STEP.",
        ),
    )


def _save_step_with_translator(inventor: object, document: object, step_path: Path) -> None:
    try:
        translator = inventor.ApplicationAddIns.ItemById(STEP_TRANSLATOR_ID)
        transient_objects = inventor.TransientObjects
        context = transient_objects.CreateTranslationContext()
        context.Type = K_FILE_BROWSE_IO_MECHANISM
        options = transient_objects.CreateNameValueMap()
        data_medium = transient_objects.CreateDataMedium()
        data_medium.FileName = str(step_path)
        translator.HasSaveCopyAsOptions(document, context, options)
        translator.SaveCopyAs(document, context, options, data_medium)
    except Exception as exc:
        raise InventorConversionError(
            "Inventor открыл IGES, но не смог сохранить STEP."
        ) from exc
