"""The engine must stay a standalone package: no web, no database, no importers, no file access."""
import ast
import pathlib

ENGINE = pathlib.Path(__file__).parent.parent / "engine"
ALLOWED = {"__future__", "dataclasses", "enum", "math", "typing", "numpy", "re"}


def test_engine_imports_only_the_standard_library_and_numpy():
    for path in ENGINE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [] if node.level else [(node.module or "").split(".")[0]]
            else:
                continue
            for n in names:
                assert n in ALLOWED, f"{path.name} imports {n}"


def test_engine_does_no_file_or_network_access():
    for path in ENGINE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"open", "exec", "eval", "__import__"}, f"{path.name} calls {node.func.id}()"


def test_engine_has_no_module_level_random_state():
    for path in ENGINE.glob("*.py"):
        text = path.read_text()
        assert "import random" not in text and "np.random.seed" not in text
