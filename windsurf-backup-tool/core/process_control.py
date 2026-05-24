from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WINDSURF_PROCESS_NAMES = (
    "Windsurf.exe",
    "windsurf.exe",
)


def close_windsurf(timeout_seconds: int = 12) -> None:
    """关闭正在运行的 Windsurf 进程。"""
    if sys.platform.startswith("win"):
        close_windsurf_on_windows(timeout_seconds)
        return

    for name in ("Windsurf", "windsurf"):
        subprocess.run(["pkill", "-f", name], capture_output=True, text=True, check=False)
    time.sleep(1)


def close_windsurf_on_windows(timeout_seconds: int) -> None:
    """在 Windows 上关闭 Windsurf。"""
    for process_name in WINDSURF_PROCESS_NAMES:
        subprocess.run(
            ["taskkill", "/IM", process_name, "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_windsurf_running_on_windows():
            return
        time.sleep(0.5)


def is_windsurf_running_on_windows() -> bool:
    """判断 Windows 上 Windsurf 是否仍在运行。"""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Windsurf.exe"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return "Windsurf.exe" in result.stdout


def launch_windsurf() -> bool:
    """启动 Windsurf，返回是否找到启动入口。"""
    candidates = find_windsurf_launch_candidates()
    for candidate in candidates:
        if candidate.exists():
            if sys.platform.startswith("win"):
                os.startfile(str(candidate))  # type: ignore[attr-defined]
            else:
                subprocess.Popen([str(candidate)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def find_windsurf_launch_candidates() -> list[Path]:
    """查找 Windsurf 常见安装位置。"""
    candidates: list[Path] = []
    for command in ("Windsurf", "windsurf"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))

    if sys.platform.startswith("win"):
        localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        candidates.extend(
            [
                localappdata / "Programs" / "Windsurf" / "Windsurf.exe",
                localappdata / "Windsurf" / "Windsurf.exe",
                program_files / "Windsurf" / "Windsurf.exe",
                program_files_x86 / "Windsurf" / "Windsurf.exe",
            ]
        )
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Windsurf.app/Contents/MacOS/Windsurf"))
    else:
        candidates.extend([Path("/usr/bin/windsurf"), Path("/usr/local/bin/windsurf")])

    return list(dict.fromkeys(candidates))