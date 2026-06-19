# TubeCutCalculator

TubeCutCalculator — Windows-программа для подготовки расчета лазерного трубореза по CAD-файлам труб. Целевая задача проекта: импорт STEP/STP/IGES/IGS, 3D-просмотр, 2D-развертка, расчет длины реза, количества врезок и стоимости обработки.

Текущая версия: **v0.1.0**.

## Что работает в v0.1.0

- Главное окно PySide6 с версией программы в заголовке.
- Кнопки добавления файла и папки.
- Drag-and-drop на главное окно, drop-зону и таблицу файлов.
- Добавление одного файла, нескольких файлов или папки.
- Рекурсивный поиск CAD-файлов в папке.
- Фильтр форматов `.step`, `.stp`, `.iges`, `.igs`.
- Пропуск дубликатов.
- Предупреждения по неподдерживаемым файлам.
- Очередь заданий с колонками: имя, путь, статус, тип трубы, длина, толщина, длина реза, врезки, стоимость, ошибка.
- Заготовки модулей `cad`, `pricing`, `export`, `settings`.
- Сохранение очереди проекта в JSON.
- `build_exe.bat` для сборки `dist/TubeCutCalculator.exe` на Windows.
- GitHub Actions workflow для сборки EXE при теге версии.

Геометрия, импорт через OpenCascade, 3D-просмотр CAD-модели, 2D-развертка и расчет реза в v0.1.0 намеренно не реализованы.

## Поддерживаемые форматы

- STEP / `.step`
- STP / `.stp`
- IGES / `.iges`
- IGS / `.igs`

## Установка зависимостей

Требуется Python 3.13.

```bat
py -3.13 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Запуск из исходников

```bat
call .venv\Scripts\activate.bat
python main.py
```

## Сборка EXE

На Windows запустите:

```bat
build_exe.bat
```

Результат:

- `dist/TubeCutCalculator.exe`
- `dist/version.txt`

В v0.1.0 сборка использует PyInstaller и PySide6. `pythonocc-core` пока не включен в зависимости, чтобы каркас интерфейса собирался стабильно. OpenCascade будет подключен на этапе v0.2.0, вместе с отдельной настройкой DLL/hidden imports для Windows-сборки.

## GitHub Releases

В проекте есть workflow `.github/workflows/build-windows.yml`. При создании тега вида `v0.1.0` workflow собирает EXE на Windows runner, загружает артефакт и прикладывает его к GitHub Release.

```bat
git tag v0.1.0
git push origin v0.1.0
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
requirements.txt
version.txt
README.md
```

## Дорожная карта

- v0.1.0 — интерфейс, drag-and-drop, очередь файлов.
- v0.2.0 — импорт STEP/IGES и 3D-просмотр.
- v0.3.0 — базовый анализ геометрии, включая профильные трубы со скругленными углами.
- v0.4.0 — расчет длины реза и количества врезок.
- v0.5.0 — визуальная проверка и 2D-развертка.
- v0.6.0 — цены и экспорт CSV/PDF/JSON.
