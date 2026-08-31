import ast
import os


def _settings_fields(settings_source: str) -> dict[str, tuple[bool, bool]]:
    """Devuelve {nombre: (tiene_default, el_default_sirve)} de los campos de la clase Settings.

    Un default que "sirve" es cualquiera que no sea vacio: si es "" o 0 o None, la var
    sigue haciendo falta cuando main.py la valida como requerida.
    """
    fields = {}
    tree = ast.parse(settings_source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Settings":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                continue
            if stmt.value is None:
                fields[stmt.target.id] = (False, False)
                continue
            try:
                default = ast.literal_eval(stmt.value)
            except ValueError:
                default = object()  # una llamada tipo ZoneInfo(...), cuenta como default valido
            fields[stmt.target.id] = (True, bool(default))
    return fields


def _main_required_keys(main_source: str) -> set[str]:
    """Saca la lista required_keys de la funcion validate() de main.py."""
    tree = ast.parse(main_source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "required_keys" for t in node.targets):
            continue
        return {e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def required_settings(settings_source: str, main_source: str) -> list[str]:
    """Settings sin los que el bot no levanta: los que no tienen default en Settings
    mas los que main.py exige y tienen un default vacio."""
    fields = _settings_fields(settings_source)
    main_required = _main_required_keys(main_source)
    return [
        name for name, (has_default, default_works) in fields.items()
        if not has_default or (name in main_required and not default_works)
    ]


def defined_env_keys(env_path: str = ".env") -> set[str]:
    """Vars con valor no vacio, ya sea en el .env o en el entorno del proceso."""
    keys = {k.upper() for k, v in os.environ.items() if v.strip()}
    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return keys

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        if value.strip().strip("\"'"):
            keys.add(key.upper())
    return keys


def missing_settings(settings_source: str, main_source: str, env_path: str = ".env") -> list[str]:
    """Cuales de los settings requeridos por ese codigo faltan en el .env de esta maquina."""
    defined = defined_env_keys(env_path)
    return [name for name in required_settings(settings_source, main_source) if name.upper() not in defined]
