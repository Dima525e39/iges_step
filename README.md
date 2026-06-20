# TubeCutCalculator

TubeCutCalculator — Windows-программа для подготовки расчета лазерного трубореза по CAD-файлам труб. Целевая задача проекта: импорт STEP/STP/IGES/IGS, 3D-просмотр, 2D-развертка, расчет длины реза, количества врезок и стоимости обработки.

Текущая версия: **v0.3.0**.

## Что работает в v0.3.0

- Главное окно PySide6 с drag-and-drop.
- Добавление отдельных файлов, нескольких файлов и папок.
- Рекурсивный поиск CAD-файлов в папке.
- Фильтр форматов `.step`, `.stp`, `.iges`, `.igs`.
- Очередь файлов с пропуском дубликатов.
- Импорт STEP/STP/IGES/IGS через OpenCascade / `pythonocc-core`.
- 3D-просмотр импортированной модели через `OCC.Display.qtDisplay.qtViewer3d`.
- Вертикальное растягивание области 3D/2D-просмотра относительно нижней таблицы файлов.
- Базовый анализ импортированной формы: ось длины, габариты сечения, solid/shell, количество граней и ребер.
- Временное DEV-окно `Geometry Debug Script`: запуск Python-скрипта по текущей модели без пересборки EXE.
- Сохранение очереди проекта в JSON.
- GitHub-ready структура проекта.
- `build_exe.bat` для сборки Windows EXE через conda + PyInstaller.
- GitHub Actions workflow для сборки EXE на Windows runner.

Расчет длины реза, количества врезок, толщины стенки, цены и 2D-развертка в v0.3.0 намеренно не реализованы. DEV-окно выполняет Python-код внутри программы и предназначено только для временной отладки анализа геометрии.

## Поддерживаемые форматы

- STEP / `.step`
- STP / `.stp`
- IGES / `.iges`
- IGS / `.igs`

## Установка зависимостей

Для v0.3.0 рекомендуется Miniforge или Anaconda, потому что `pythonocc-core` устанавливается из `conda-forge`.

```bat
conda env create -f environment.yml
conda activate TubeCutCalculator
```

Если окружение уже создано:

```bat
conda env update -n TubeCutCalculator -f environment.yml --prune
conda activate TubeCutCalculator
```

## Запуск из исходников

```bat
conda activate TubeCutCalculator
python main.py
```

## Сборка EXE

На Windows запустите:

```bat
build_exe.bat
```

Скрипт создаст или обновит conda-окружение `TubeCutCalculator`, затем соберет one-file EXE через `TubeCutCalculator.spec`.

Результат:

- `dist/TubeCutCalculator.exe`
- `dist/version.txt`

## GitHub Actions

Workflow `.github/workflows/build-windows.yml` собирает EXE на Windows runner при push в `main`, push в `feature/**` и при ручном запуске. После сборки workflow запускает smoke-test импортов внутри готового EXE. При создании тега вида `v0.3.0` EXE также прикладывается к GitHub Release.

```bat
git tag v0.3.0
git push origin v0.3.0
```

## Структура проекта

```text
main.py
app_info.py
ui/
cad/
pricing/
export/
settings/
core/
tests/
samples/
releases/
.github/workflows/
build_exe.bat
environment.yml
requirements.txt
TubeCutCalculator.spec
version.txt
README.md
```

## Дорожная карта

- v0.1.0 — интерфейс, drag-and-drop, очередь файлов.
- v0.2.0 — импорт STEP/IGES и 3D-просмотр.
- v0.2.1 — hotfix: подробные ошибки импорта, безопасное чтение CAD-файлов с не-ASCII путями, smoke-test импортов в EXE-сборке.
- v0.2.2 — hotfix: исправлен подсчет топологии после импорта (`TopExp_Explorer is not defined`).
- v0.2.3 — hotfix: приближение 3D-модели к курсору и отключение подсветки при клике по трубе.
- v0.3.0 — вертикальное растягивание области 3D/2D-просмотра, базовый анализ геометрии и временное DEV-окно для скриптов.
- v0.4.0 — уточнение анализа геометрии, включая профильные трубы со скругленными углами.
- v0.5.0 — расчет длины реза и количества врезок.
- v0.6.0 — визуальная проверка и 2D-развертка.
- v0.7.0 — цены и экспорт CSV/PDF/JSON.
