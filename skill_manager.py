"""Загрузка / проверка / хранение навыков (самомодификация бота)."""
import ast
import importlib.util
import json
import re
from pathlib import Path
from dataclasses import dataclass

from config import SKILLS_DIR, MANIFEST

DANGEROUS_SUBSTR = [
    "os.system", "subprocess", "socket", "__import__",
    "shutil.rmtree", "eval(", "exec(", "open(",
    "BOT_TOKEN", "YANDEX_API_KEY",
]

@dataclass
class Skill:
    name: str
    description: str
    triggers: list
    module: object
    path: Path


def safe_check(code: str) -> tuple[bool, str]:
    """Статическая проверка кода перед исполнением."""
    for bad in DANGEROUS_SUBSTR:
        if bad in code:
            # open( разрешаем только на чтение? проще запретить полностью в навыках
            return False, f"запрещённая конструкция: {bad}"
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"синтаксическая ошибка: {e}"

    has_handle = False
    has_name = has_trig = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    if t.id == "SKILL_NAME":
                        has_name = True
                    if t.id == "TRIGGERS":
                        has_trig = True
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "handle":
            has_handle = isinstance(node, ast.AsyncFunctionDef)

    if not has_name:
        return False, "нет SKILL_NAME"
    if not has_trig:
        return False, "нет TRIGGERS"
    if not has_handle:
        return False, "handle() должна быть async def handle(message, bot)"

    # проверка импортов
    allowed = {"re", "random", "datetime", "json", "math", "aiogram"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in allowed and root != "aiogram":
                    return False, f"запрещённый импорт: {a.name}"
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root and root not in allowed:
                return False, f"запрещённый импорт from: {node.module}"
        if isinstance(node, ast.While):
            return False, "while запрещён в навыках (риск зависания)"
    return True, "ok"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"skills.{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"не могу загрузить {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def load_all_skills() -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    else:
        manifest = {}

    for py in SKILLS_DIR.glob("*.py"):
        if py.name.startswith("_") or py.name.startswith("__"):
            continue
        name = py.stem
        try:
            mod = _load_module(name, py)
            skills[name] = Skill(
                name=getattr(mod, "SKILL_NAME", name),
                description=getattr(mod, "SKILL_DESCRIPTION", ""),
                triggers=list(getattr(mod, "TRIGGERS", [])),
                module=mod,
                path=py,
            )
        except Exception as e:
            print(f"[skills] не загрузился {py.name}: {e}")
    return skills


def save_skill(name: str, code: str) -> Path:
    name = re.sub(r"[^a-z0-9_]", "", name.lower()) or "skill"
    path = SKILLS_DIR / f"{name}.py"
    path.write_text(code, encoding="utf-8")
    # обновить манифест
    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    manifest[name] = {"file": f"{name}.py"}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def delete_skill(name: str) -> bool:
    path = SKILLS_DIR / f"{name}.py"
    if path.exists():
        path.unlink()
        return True
    return False
