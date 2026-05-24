from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


# 程序入口：创建应用、设置图标并显示主窗口。
def main() -> int:
    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "Windsurf图标.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())