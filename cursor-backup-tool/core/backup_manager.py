import os
import shutil
import tarfile
import subprocess
import time
from datetime import datetime
from dataclasses import dataclass, field

from core.settings import get_saved_cursor_exe_path, set_saved_cursor_exe_path


@dataclass
class BackupEntry:
    path: str
    name: str
    timestamp: datetime
    size_mb: float = 0.0


class BackupError(Exception):
    pass


def get_cursor_user_dir() -> str:
    appdata = os.environ.get("APPDATA", "")
    path = os.path.join(appdata, "Cursor", "User")
    if not os.path.isdir(path):
        raise BackupError(f"Cursor User 目录未找到: {path}")
    return path


def is_cursor_running() -> bool:
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Cursor.exe"],
            encoding="utf-8", errors="replace",
        )
        return "Cursor.exe" in output
    except subprocess.CalledProcessError:
        return False


def detect_cursor_executable() -> str | None:
    """在常见安装目录中自动查找 Cursor.exe。"""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if not localappdata:
        return None
    for parts in (("Programs", "cursor", "Cursor.exe"), ("Programs", "Cursor", "Cursor.exe")):
        path = os.path.join(localappdata, *parts)
        if os.path.isfile(path):
            return path
    return None


def get_cursor_executable() -> str | None:
    """优先使用用户配置的路径，否则尝试自动检测。"""
    saved = get_saved_cursor_exe_path()
    if saved:
        return saved
    return detect_cursor_executable()


def validate_cursor_executable(path: str) -> str:
    normalized = os.path.normpath(path.strip())
    if not normalized:
        raise BackupError("请选择 Cursor.exe 路径")
    if os.path.basename(normalized).lower() != "cursor.exe":
        raise BackupError("请选择名为 Cursor.exe 的可执行文件")
    if not os.path.isfile(normalized):
        raise BackupError(f"文件不存在: {normalized}")
    return normalized


def save_cursor_executable(path: str) -> str:
    normalized = validate_cursor_executable(path)
    set_saved_cursor_exe_path(normalized)
    return normalized


def close_cursor(wait_timeout: float = 60.0) -> None:
    """关闭所有 Cursor 进程，先尝试正常退出，超时后强制结束。"""
    if not is_cursor_running():
        return

    subprocess.run(
        ["taskkill", "/IM", "Cursor.exe"],
        capture_output=True,
        check=False,
    )

    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        if not is_cursor_running():
            return
        time.sleep(0.5)

    subprocess.run(
        ["taskkill", "/F", "/IM", "Cursor.exe"],
        capture_output=True,
        check=False,
    )
    time.sleep(1)
    if is_cursor_running():
        raise BackupError("无法在限定时间内关闭 Cursor，请手动关闭后重试")


def launch_cursor() -> None:
    exe = get_cursor_executable()
    if not exe:
        raise BackupError(
            "找不到 Cursor 可执行文件。请在配置中浏览选择 Cursor.exe，"
            "或点击「自动检测」。"
        )
    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [exe],
        cwd=os.path.dirname(exe),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _ensure_backup_dir(backup_dir: str) -> None:
    os.makedirs(backup_dir, exist_ok=True)


def _generate_backup_name() -> str:
    return datetime.now().strftime("cursor_backup_%Y-%m-%d_%H-%M-%S")


def create_backup(backup_dir: str) -> BackupEntry:
    close_cursor()

    _ensure_backup_dir(backup_dir)
    name = _generate_backup_name()
    archive_path = os.path.join(backup_dir, f"{name}.tar.gz")

    cursor_user = get_cursor_user_dir()
    shutil.make_archive(
        base_name=os.path.join(backup_dir, name),
        format="gztar",
        root_dir=os.path.dirname(cursor_user),
        base_dir=os.path.basename(cursor_user),
    )

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    return BackupEntry(
        path=archive_path,
        name=name,
        timestamp=datetime.now(),
        size_mb=round(size_mb, 2),
    )


def restore_backup(backup_path: str) -> None:
    close_cursor()

    if not os.path.isfile(backup_path):
        raise BackupError(f"备份文件不存在: {backup_path}")

    cursor_user = get_cursor_user_dir()
    parent = os.path.dirname(cursor_user)

    if os.path.isdir(cursor_user):
        shutil.rmtree(cursor_user)

    with tarfile.open(backup_path, "r:gz") as tf:
        tf.extractall(path=parent, filter="data")

    launch_cursor()


def list_backups(backup_dir: str) -> list[BackupEntry]:
    if not os.path.isdir(backup_dir):
        return []

    entries = []
    for fname in os.listdir(backup_dir):
        if not fname.endswith(".tar.gz"):
            continue
        fpath = os.path.join(backup_dir, fname)
        if not os.path.isfile(fpath):
            continue

        name = fname.replace(".tar.gz", "")
        try:
            ts_part = name.replace("cursor_backup_", "")
            timestamp = datetime.strptime(ts_part, "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            timestamp = datetime.fromtimestamp(os.path.getmtime(fpath))

        size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2)
        entries.append(BackupEntry(path=fpath, name=name, timestamp=timestamp, size_mb=size_mb))

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


def delete_backup(backup_path: str) -> None:
    if os.path.isfile(backup_path):
        os.remove(backup_path)