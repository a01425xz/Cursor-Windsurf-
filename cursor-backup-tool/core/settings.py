import json
import os

_CONFIG_DIR_NAME = "CursorBackupTool"
_CONFIG_FILENAME = "config.json"


def _config_path() -> str:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(appdata, _CONFIG_DIR_NAME, _CONFIG_FILENAME)


def load_settings() -> dict:
    path = _config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict) -> None:
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_saved_cursor_exe_path() -> str | None:
    path = load_settings().get("cursor_exe_path", "").strip()
    if path and os.path.isfile(path):
        return path
    return None


def set_saved_cursor_exe_path(path: str) -> None:
    settings = load_settings()
    settings["cursor_exe_path"] = path
    save_settings(settings)
