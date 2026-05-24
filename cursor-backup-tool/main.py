import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

ICON_FILENAME = "Cursor图标.ico"


def _icon_path() -> str | None:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        path = os.path.join(base, ICON_FILENAME)
        return path if os.path.isfile(path) else None
    parent = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    path = os.path.join(parent, ICON_FILENAME)
    return path if os.path.isfile(path) else None


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icon_path = _icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # 全局样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f6fa;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #dcdde1;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QPushButton {
            background-color: #0984e3;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
        }
        QPushButton:hover {
            background-color: #0773c5;
        }
        QPushButton:pressed {
            background-color: #065a9e;
        }
        QPushButton:disabled {
            background-color: #b2bec3;
        }
        QTableWidget {
            border: 1px solid #dcdde1;
            border-radius: 4px;
            gridline-color: #ecf0f1;
        }
        QTableWidget::item {
            padding: 6px;
        }
        QTableWidget::item:selected {
            background-color: #74b9ff;
            color: black;
        }
        QHeaderView::section {
            background-color: #dfe6e9;
            border: none;
            padding: 6px;
            font-weight: bold;
        }
        QLineEdit {
            border: 1px solid #dcdde1;
            border-radius: 4px;
            padding: 4px 8px;
        }
        QStatusBar {
            background-color: #dfe6e9;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()