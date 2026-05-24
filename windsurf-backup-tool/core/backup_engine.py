from __future__ import annotations

import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.path_finder import (
    RELATED_STATE_ROOT_ALIASES,
    ROOT_ARCHIVE_DIR,
    candidate_related_state_roots,
    collect_backup_sources,
    normalize_path,
)
from core.process_control import close_windsurf, launch_windsurf

SKIP_BACKUP_PARTS = {
    "logs",
    "Cache",
    "CachedData",
    "Code Cache",
    "GPUCache",
    "DawnCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "Crashpad",
    "CachedExtensionVSIXs",
    "CachedProfilesData",
    "blob_storage",
}

AUTH_PRESERVE_RELATIVE_PATHS = {
    "appdata_roaming_windsurf": (
        Path("Local State"),
        Path("Preferences"),
        Path("Local Storage"),
        Path("Session Storage"),
        Path("Network"),
        Path("machineid"),
        Path("User") / "globalStorage" / "state.vscdb",
        Path("User") / "globalStorage" / "state.vscdb.backup",
        Path("User") / "globalStorage" / "storage.json",
        Path("User") / "globalStorage" / "argv.json",
    ),
    "appdata_roaming_dot_xinghuowindsurf": (
        Path("shared-data"),
    ),
    "home_dot_codeium": (
        Path("windsurf") / "installation_id",
        Path("windsurf") / "user_settings.pb",
        Path("windsurf") / "native_storage_migrations.lock",
    ),
}


class BackupError(Exception):
    """备份和恢复流程中的可读错误。"""


def format_size(size: int) -> str:
    """将字节数转换为界面友好的大小文本。"""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def directory_size(path: Path) -> int:
    """计算文件或目录的总大小。"""
    if path.is_file():
        return 0 if should_skip_backup_path(path) else path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not should_skip_backup_path(item):
                total += item.stat().st_size
        except (OSError, PermissionError):
            continue
    return total


def sources_size(sources: list[tuple[str, Path]]) -> int:
    """计算所有备份资源的估算大小。"""
    return sum(directory_size(path) for _, path in sources if path.exists())


def ensure_enough_space(target_dir: Path, required_size: int) -> None:
    """检查备份目录可用空间是否大于内容大小的两倍。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target_dir)
    minimum = required_size * 2
    if usage.free < minimum:
        raise BackupError(
            f"备份目录磁盘空间不足。需要至少 {format_size(minimum)}，当前可用 {format_size(usage.free)}。"
        )


def should_skip_backup_path(path: Path) -> bool:
    """判断是否跳过明显缓存和日志路径。"""
    return any(part in SKIP_BACKUP_PARTS for part in path.parts)


def add_path_to_zip(
    zip_file: zipfile.ZipFile,
    source: Path,
    arcname: str,
    progress_callback: Callable[[str], None] | None = None,
) -> int:
    """将文件或目录写入 zip 包并返回写入文件数量。"""
    written = 0
    if source.is_file():
        if should_skip_backup_path(source):
            return 0
        if progress_callback:
            progress_callback(f"正在写入：{arcname}")
        zip_file.write(source, arcname)
        return 1

    for item in source.rglob("*"):
        try:
            if item.is_file() and not should_skip_backup_path(item):
                relative = item.relative_to(source).as_posix()
                target_name = f"{arcname.rstrip('/')}/{relative}"
                if progress_callback and written % 25 == 0:
                    progress_callback(f"正在写入：{target_name}")
                zip_file.write(item, target_name)
                written += 1
        except (OSError, PermissionError) as exc:
            raise BackupError(f"读取文件失败：{item}\n{exc}") from exc
    return written


def create_backup_archive(
    config_dir: str | Path,
    backup_dir: str | Path,
    include_settings: bool,
    include_chats: bool,
    include_workspace: bool,
    suffix: str = "",
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    """创建 Windsurf 配置备份 zip。"""
    config_path = normalize_path(config_dir)
    backup_path = normalize_path(backup_dir)

    if not config_path.exists():
        raise BackupError(f"Windsurf 配置目录不存在：{config_path}")

    if progress_callback:
        progress_callback("正在扫描要备份的配置内容...")
    sources = collect_backup_sources(config_path, include_settings, include_chats, include_workspace)
    if not sources:
        raise BackupError("未找到可备份的内容，请检查配置目录或备份选项。")

    if progress_callback:
        progress_callback(f"已找到 {len(sources)} 项内容，正在估算大小...")
    total_size = sources_size(sources)
    ensure_enough_space(backup_path, total_size)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = backup_path / f"windsurf_backup_{timestamp}{suffix}.zip"

    try:
        file_count = 0
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for index, (arcname, source) in enumerate(sources, start=1):
                if progress_callback:
                    progress_callback(f"正在打包第 {index}/{len(sources)} 项：{arcname}")
                file_count += add_path_to_zip(zip_file, source, arcname, progress_callback)
        if progress_callback:
            progress_callback(f"已写入 {file_count} 个文件，正在完成备份...")
    except PermissionError as exc:
        raise BackupError("权限不足，无法读取配置文件或写入备份文件。") from exc
    except OSError as exc:
        raise BackupError(f"创建备份失败：{exc}") from exc

    return archive_path


def safe_extract_archive(archive_path: Path, target_dir: Path) -> None:
    """安全解压 zip，避免异常路径写出临时目录。"""
    target_root = target_dir.resolve()
    with zipfile.ZipFile(archive_path, "r") as zip_file:
        for member in zip_file.infolist():
            destination = (target_root / member.filename).resolve()
            if target_root != destination and target_root not in destination.parents:
                raise BackupError("备份包包含不安全路径，已停止恢复。")
        zip_file.extractall(target_root)


def restore_path(source: Path, destination: Path) -> None:
    """替换恢复一个文件或目录。"""
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        shutil.copy2(source, destination)


def preserve_current_auth_state(config_dir: Path, preserve_dir: Path) -> list[tuple[Path, Path]]:
    """保存当前有效登录态，稍后覆盖回恢复后的快照。"""
    preserved: list[tuple[Path, Path]] = []
    root_targets = dict(candidate_related_state_roots(config_dir))

    for alias, relative_paths in AUTH_PRESERVE_RELATIVE_PATHS.items():
        root = root_targets.get(alias)
        if root is None:
            continue
        for relative_path in relative_paths:
            source = root / relative_path
            if not source.exists():
                continue
            backup_target = preserve_dir / alias / relative_path
            restore_target = root / relative_path
            restore_path(source, backup_target)
            preserved.append((backup_target, restore_target))

    return preserved


def restore_preserved_auth_state(preserved: list[tuple[Path, Path]]) -> None:
    """把恢复前的有效登录态放回当前状态目录。"""
    for source, destination in preserved:
        if source.exists():
            restore_path(source, destination)


def copy_restored_files(temp_dir: Path, config_dir: Path) -> None:
    """将临时目录中的备份内容替换回 Windsurf 配置目录。"""
    snapshot_dir = temp_dir / ROOT_ARCHIVE_DIR

    if snapshot_dir.exists():
        root_targets = dict(candidate_related_state_roots(config_dir))
        for alias in RELATED_STATE_ROOT_ALIASES:
            source = snapshot_dir / alias
            if not source.exists():
                continue
            destination = root_targets.get(alias)
            if destination is None:
                continue
            restore_path(source, destination)

    for item in temp_dir.iterdir():
        if item.name in {ROOT_ARCHIVE_DIR, "__current_auth_state__"}:
            continue
        destination = config_dir / item.name
        restore_path(item, destination)


def restore_backup_archive(
    archive_path: str | Path,
    config_dir: str | Path,
) -> Path:
    """恢复选中的备份，并尽量保留当前有效登录态。"""
    archive = normalize_path(archive_path)
    config_path = normalize_path(config_dir)

    if not archive.exists():
        raise BackupError(f"选中的备份文件不存在：{archive}")
    if not zipfile.is_zipfile(archive):
        raise BackupError("选中的文件不是有效的 zip 备份。")

    try:
        with tempfile.TemporaryDirectory(prefix="windsurf_restore_") as temp_name:
            temp_dir = Path(temp_name)
            auth_preserve_dir = temp_dir / "__current_auth_state__"
            preserved_auth = preserve_current_auth_state(config_path, auth_preserve_dir)
            safe_extract_archive(archive, temp_dir)
            copy_restored_files(temp_dir, config_path)
            restore_preserved_auth_state(preserved_auth)
    except PermissionError as exc:
        raise BackupError("权限不足，无法恢复配置文件。") from exc
    except OSError as exc:
        raise BackupError(f"恢复失败：{exc}") from exc

    return archive


class BackupWorker(QObject):
    """在后台线程执行备份任务。"""

    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        config_dir: str,
        backup_dir: str,
        include_settings: bool,
        include_chats: bool,
        include_workspace: bool,
    ) -> None:
        super().__init__()
        self.config_dir = config_dir
        self.backup_dir = backup_dir
        self.include_settings = include_settings
        self.include_chats = include_chats
        self.include_workspace = include_workspace

    @Slot()
    def run(self) -> None:
        """执行备份并发送结果信号。"""
        try:
            self.progress.emit("正在关闭 Windsurf...")
            close_windsurf()
            self.progress.emit("正在检查备份内容和磁盘空间...")
            archive = create_backup_archive(
                self.config_dir,
                self.backup_dir,
                self.include_settings,
                self.include_chats,
                self.include_workspace,
                progress_callback=self.progress.emit,
            )
            self.finished.emit(str(archive))
        except Exception as exc:
            self.failed.emit(str(exc))


class RestoreWorker(QObject):
    """在后台线程执行恢复任务。"""

    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, archive_path: str, config_dir: str) -> None:
        super().__init__()
        self.archive_path = archive_path
        self.config_dir = config_dir

    @Slot()
    def run(self) -> None:
        """执行恢复并发送结果信号。"""
        try:
            self.progress.emit("正在关闭 Windsurf...")
            close_windsurf()
            self.progress.emit("正在恢复配置并保留当前登录状态...")
            restored = restore_backup_archive(self.archive_path, self.config_dir)
            self.progress.emit("正在启动 Windsurf...")
            launch_windsurf()
            self.finished.emit(str(restored))
        except Exception as exc:
            self.failed.emit(str(exc))


def start_worker(worker: QObject) -> QThread:
    """启动后台工作对象并返回线程引用。"""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)  # type: ignore[attr-defined]
    worker.failed.connect(thread.quit)  # type: ignore[attr-defined]
    worker.finished.connect(worker.deleteLater)  # type: ignore[attr-defined]
    worker.failed.connect(worker.deleteLater)  # type: ignore[attr-defined]
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread