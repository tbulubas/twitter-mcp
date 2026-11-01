# IntelliJ IDEA Setup

How to use the project's virtual environment in IntelliJ IDEA to run the
tests and the application. The steps refer to IntelliJ IDEA 2024+ on Windows;
on Linux/macOS replace `.venv\Scripts\python.exe` by `.venv/bin/python`.

## 1. Python plugin

*Settings → Plugins → Marketplace*: install **Python** (IntelliJ IDEA
Ultimate) or **Python Community Edition** (IntelliJ IDEA Community), then
restart the IDE.

## 2. Create the environment

In a terminal in the project root (also *View → Tool Windows → Terminal*):

```bash
make venv
```

This creates `.venv` with Python 3.12 and installs the project in editable
mode with all its dependencies (see [README](../README.md#development-environment)).

## 3. Register the interpreter

1. *File → Project Structure… → Platform Settings → SDKs → + → Add Python
   SDK from disk…*
2. Choose *Virtualenv Environment → Existing environment* and select
   `<project>\.venv\Scripts\python.exe`.
3. Optionally rename the SDK, e.g. `Python 3.12 (TwitterMcp)`.

Do not let IntelliJ create a new virtual environment or pick another
interpreter — the project's
`.venv` is managed by the Makefile.

## 4. Use it for the project

1. *Project Structure → Project → SDK*: select the new Python SDK.
2. *Project Structure → Modules → TwitterMcp → Dependencies → Module SDK*:
   *Project SDK*.

   If the module was created as a Java module and the Python SDK is not
   offered there, add a Python facet instead: *Project Structure → Facets →
   + → Python → TwitterMcp*, and select the Python SDK in the facet.
3. *Modules → TwitterMcp → Sources*: mark
   - `src` as **Sources**,
   - `tests` as **Tests**,
   - `.venv` as **Excluded** (usually already done).

## 5. Test runner

*Settings → Tools → Python Integrated Tools → Testing → Default test runner*:
**pytest**.

## 6. Run configurations

The project ships two shared run configurations in `.run/`. IntelliJ picks
them up automatically and lists them in the run configuration drop-down in
the toolbar:

| Configuration      | What it runs                                  |
|--------------------|-----------------------------------------------|
| `pytest all tests` | `pytest tests`                                |
| `twittermcp server` | `python -m twittermcp serve --http` → http://127.0.0.1:8600/mcp |

Both use the module SDK, i.e. the `.venv` interpreter, and the project root
as working directory. Another port: *Run → Edit Configurations… → twittermcp
server → Parameters*, e.g. `serve --http --port 8601`.

If the configurations do not appear, create them by hand:

- **Tests:** right-click the `tests` folder → *Run 'pytest in tests'*. A
  single test runs from the green arrow next to it in the editor.
- **Application:** *Run → Edit Configurations… → + → Python*; switch *script
  path* to **module**, enter `twittermcp` and parameters `serve --http`, *Working directory* to the project
  root, *Python interpreter* to the project SDK.

## 7. After dependency changes

When `pyproject.toml` changes, run `make venv` again; IntelliJ re-indexes
the interpreter automatically. To start from scratch, run `make recreate`.

---

© 2026 Taras Bulubas. All rights reserved. See [LICENSE](../LICENSE).
