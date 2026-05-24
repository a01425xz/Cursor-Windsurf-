from __future__ import annotations

import os
import sys
from pathlib import Path

CHAT_KEYWORDS = ("chat", "conversation", "history", "ai", "copilot", "windsurf", "codeium")

ROOT_ARCHIVE_DIR = "__windsurf_state_roots__"

CHAT_STATE_ROOTS = (
    "User",
    "IndexedDB",
    "Local Storage",
    "Session Storage",
    "WebStorage",
    "Service Worker",
    "Network",
    "Shared Dictionary",
    "Preferences",
    "Local State",
    "DIPS",
    "SharedStorage",
)

RELATED_STATE_ROOT_ALIASES = (
    "appdata_roaming_windsurf",
    "appdata_roaming_dot_windsurf",
    "appdata_roaming_dot_xinghuowindsurf",
    "appdata_roaming_codeium",
    "localappdata_windsurf",
    "localappdata_lower_windsurf",
    "localappdata_codeium",
    "home_dot_codeium",
    "home_dot_windsurf",
)


def detect_windsurf_config_dir() -> Path:
    """自动检测当前系统的 Windsurf 配置目录。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Windsurf"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Windsurf"
        return Path.home() / "AppData" / "Roaming" / "Windsurf"
    return Path.home() / ".config" / "Windsurf"


def default_backup_dir() -> Path:
    """返回默认备份保存目录。"""
    return Path.home() / "Documents" / "WindsurfBackups"


def normalize_path(path: str | Path) -> Path:
    """展开用户目录并返回绝对路径。"""
    return Path(path).expanduser().resolve()


def get_settings_path(config_dir: str | Path) -> Path:
    """获取用户设置文件路径。"""
    return normalize_path(config_dir) / "User" / "settings.json"


def get_workspace_storage_path(config_dir: str | Path) -> Path:
    """获取工作区配置目录路径。"""
    return normalize_path(config_dir) / "User" / "workspaceStorage"


def is_chat_related(path: Path) -> bool:
    """判断路径名称是否可能与 AI 对话历史相关。"""
    lowered = path.name.lower()
    return any(keyword in lowered for keyword in CHAT_KEYWORDS)


def find_chat_related_paths(config_dir: str | Path) -> list[Path]:
    """检测 AI 对话历史相关目录并补充展示命中的线索路径。"""
    config_path = normalize_path(config_dir)
    user_dir = config_path / "User"
    if not user_dir.exists():
        return []

    roots = get_chat_backup_roots(config_path)
    found: set[Path] = set()

    for root in roots:
        if not root.exists():
            continue
        found.add(root)
        try:
            for item in root.rglob("*"):
                if is_chat_related(item):
                    found.add(item)
        except (PermissionError, OSError):
            continue

    return sorted(found, key=lambda item: str(item).lower())


def get_chat_backup_roots(config_dir: str | Path) -> list[Path]:
    """返回需要完整备份的 AI 对话和运行态状态根路径。"""
    config_path = normalize_path(config_dir)
    roots = [config_path / name for name in CHAT_STATE_ROOTS]
    return [root for root in roots if root.exists()]


def candidate_related_state_roots(config_dir: str | Path) -> list[tuple[str, Path]]:
    """返回 Windsurf/Codeium 可能使用的跨目录状态根。"""
    config_path = normalize_path(config_dir)
    appdata = Path(os.environ.get("APPDATA", config_path.parent))
    localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates = [
        ("appdata_roaming_windsurf", config_path),
        ("appdata_roaming_dot_windsurf", appdata / ".windsurf"),
        ("appdata_roaming_dot_xinghuowindsurf", appdata / ".xinghuowindsurf"),
        ("appdata_roaming_codeium", appdata / "Codeium"),
        ("localappdata_windsurf", localappdata / "Windsurf"),
        ("localappdata_lower_windsurf", localappdata / "windsurf"),
        ("localappdata_codeium", localappdata / "Codeium"),
        ("home_dot_codeium", Path.home() / ".codeium"),
        ("home_dot_windsurf", Path.home() / ".windsurf"),
    ]
    return [(alias, normalize_path(path)) for alias, path in candidates if path.exists()]


def collect_snapshot_sources(config_dir: str | Path) -> list[tuple[str, Path]]:
    """收集完整状态快照来源。"""
    return [(f"{ROOT_ARCHIVE_DIR}/{alias}", path) for alias, path in candidate_related_state_roots(config_dir)]


def collect_backup_sources(
    config_dir: str | Path,
    include_settings: bool,
    include_chats: bool,
    include_workspace: bool,
) -> list[tuple[str, Path]]:
    """根据用户选择收集需要进入备份包的资源。"""
    config_path = normalize_path(config_dir)
    sources: list[tuple[str, Path]] = []

    if include_settings:
        settings_path = get_settings_path(config_path)
        if settings_path.exists():
            sources.append(("User/settings.json", settings_path))

    if include_chats:
        sources.extend(collect_snapshot_sources(config_path))

    if include_workspace:
        workspace_path = get_workspace_storage_path(config_path)
        if workspace_path.exists():
            sources.append(("User/workspaceStorage", workspace_path))

    return deduplicate_sources(sources)


def deduplicate_sources(sources: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    """去除重复或已被父目录覆盖的备份资源。"""
    normalized = sorted(
        ((arc.rstrip("/"), path) for arc, path in sources),
        key=lambda item: (len(item[0]), item[0].lower()),
    )
    result: list[tuple[str, Path]] = []

    for arcname, path in normalized:
        covered = False
        for existing_arcname, _ in result:
            if arcname == existing_arcname or arcname.startswith(existing_arcname.rstrip("/") + "/"):
                covered = True
                break
        if not covered:
            result.append((arcname, path))

    return result