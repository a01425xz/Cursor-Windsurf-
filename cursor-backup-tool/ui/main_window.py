import os
import threading

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QStatusBar, QFileDialog, QGroupBox,
    QAbstractItemView, QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QObject

from core.backup_manager import (
    create_backup, restore_backup, list_backups, delete_backup,
    is_cursor_running, get_cursor_user_dir, get_cursor_executable,
    detect_cursor_executable, save_cursor_executable,
    BackupEntry, BackupError,
)


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


def _run_in_thread(target, *args):
    signals = WorkerSignals()

    def _wrapper():
        try:
            result = target(*args)
            signals.finished.emit(result)
        except BackupError as e:
            signals.error.emit(str(e))
        except Exception as e:
            signals.error.emit(f"未知错误: {e}")

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()
    return signals


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cursor 备份恢复工具")
        self.resize(720, 560)
        self._backup_dir = os.path.join(os.path.expanduser("~"), "CursorBackups")
        self._setup_ui()
        self.refresh_backup_list()

    # ---------- UI setup ----------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- 顶部：Cursor 状态 + 备份目录 ---
        top_group = QGroupBox("配置")
        top_layout = QVBoxLayout(top_group)
        top_layout.setSpacing(8)

        self._status_label = QLabel("正在检测 Cursor 状态...")
        top_layout.addWidget(self._status_label)

        cursor_row = QHBoxLayout()
        cursor_row.addWidget(QLabel("Cursor 程序路径:"))
        self._cursor_exe_edit = QLineEdit()
        self._cursor_exe_edit.setPlaceholderText("选择 Cursor.exe（恢复备份后用于自动启动）...")
        self._cursor_exe_edit.editingFinished.connect(self._on_cursor_exe_edited)
        cursor_row.addWidget(self._cursor_exe_edit, 1)

        cursor_detect_btn = QPushButton("自动检测")
        cursor_detect_btn.setFixedWidth(72)
        cursor_detect_btn.clicked.connect(self._on_detect_cursor_exe)
        cursor_row.addWidget(cursor_detect_btn)

        cursor_browse_btn = QPushButton("浏览")
        cursor_browse_btn.setFixedWidth(60)
        cursor_browse_btn.clicked.connect(self._on_browse_cursor_exe)
        cursor_row.addWidget(cursor_browse_btn)
        top_layout.addLayout(cursor_row)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("备份保存目录:"))
        self._dir_edit = QLineEdit(self._backup_dir)
        self._dir_edit.setPlaceholderText("选择备份文件存放目录...")
        dir_row.addWidget(self._dir_edit, 1)

        browse_btn = QPushButton("浏览")
        browse_btn.setFixedWidth(60)
        browse_btn.clicked.connect(self._on_browse_dir)
        dir_row.addWidget(browse_btn)
        top_layout.addLayout(dir_row)

        root.addWidget(top_group)

        # --- 中部：备份列表 ---
        list_group = QGroupBox("备份列表")
        list_layout = QVBoxLayout(list_group)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["备份名称", "创建时间", "大小"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        list_layout.addWidget(self._table)
        root.addWidget(list_group, 1)

        # --- 底部：操作按钮 ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._backup_btn = QPushButton("创建备份")
        self._backup_btn.setMinimumHeight(36)
        self._backup_btn.clicked.connect(self._on_backup)
        btn_row.addWidget(self._backup_btn)

        self._restore_btn = QPushButton("恢复选中备份")
        self._restore_btn.setMinimumHeight(36)
        self._restore_btn.setEnabled(False)
        self._restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self._restore_btn)

        self._delete_btn = QPushButton("删除选中备份")
        self._delete_btn.setMinimumHeight(36)
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        btn_row.addStretch()

        self._refresh_btn = QPushButton("刷新列表")
        self._refresh_btn.setMinimumHeight(36)
        self._refresh_btn.clicked.connect(self.refresh_backup_list)
        btn_row.addWidget(self._refresh_btn)

        root.addLayout(btn_row)

        # --- 底部进度条 ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        root.addWidget(self._progress)

        # --- 状态栏 ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")

        self._load_cursor_exe_path()
        self._check_cursor_status()

    # ---------- status ----------

    def _check_cursor_status(self):
        try:
            running = is_cursor_running()
            user_dir = get_cursor_user_dir()
            if running:
                self._status_label.setText(f"Cursor 状态: 运行中  |  路径: {user_dir}")
                self._status_label.setStyleSheet("color: #e67e22; font-weight: bold;")
            else:
                self._status_label.setText(f"Cursor 状态: 未运行  |  路径: {user_dir}")
                self._status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        except BackupError as e:
            self._status_label.setText(f"Cursor 状态: {e}")
            self._status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _set_busy(self, busy: bool):
        self._progress.setVisible(busy)
        self._backup_btn.setEnabled(not busy)
        self._restore_btn.setEnabled(not busy and self._table.currentRow() >= 0)
        self._delete_btn.setEnabled(not busy and self._table.currentRow() >= 0)
        self._refresh_btn.setEnabled(not busy)

    # ---------- backup list ----------

    def refresh_backup_list(self):
        backup_dir = self._dir_edit.text().strip()
        if not backup_dir:
            return
        entries = list_backups(backup_dir)
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self._table.setItem(row, 0, QTableWidgetItem(entry.name))
            self._table.setItem(row, 1, QTableWidgetItem(
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            ))
            self._table.setItem(row, 2, QTableWidgetItem(f"{entry.size_mb} MB"))
        self._status_bar.showMessage(f"共 {len(entries)} 个备份")

    def _on_selection_changed(self):
        has_selection = self._table.currentRow() >= 0
        self._restore_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _get_selected_backup_path(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        name_item = self._table.item(row, 0)
        if name_item is None:
            return None
        backup_dir = self._dir_edit.text().strip()
        return os.path.join(backup_dir, f"{name_item.text()}.tar.gz")

    # ---------- actions ----------

    def _load_cursor_exe_path(self):
        exe = get_cursor_executable() or ""
        self._cursor_exe_edit.setText(exe)

    def _on_browse_cursor_exe(self):
        start_dir = self._cursor_exe_edit.text().strip()
        if not start_dir or not os.path.isdir(os.path.dirname(start_dir)):
            start_dir = os.environ.get("LOCALAPPDATA", "")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Cursor.exe",
            start_dir,
            "Cursor 可执行文件 (Cursor.exe);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            saved = save_cursor_executable(path)
            self._cursor_exe_edit.setText(saved)
            self._status_bar.showMessage("Cursor 路径已保存")
        except BackupError as e:
            QMessageBox.warning(self, "提示", str(e))

    def _on_detect_cursor_exe(self):
        path = detect_cursor_executable()
        if not path:
            QMessageBox.warning(
                self, "提示",
                "未在默认安装位置找到 Cursor.exe。\n"
                "请使用「浏览」手动选择 Cursor.exe。",
            )
            return
        saved = save_cursor_executable(path)
        self._cursor_exe_edit.setText(saved)
        self._status_bar.showMessage("已自动检测并保存 Cursor 路径")

    def _on_cursor_exe_edited(self):
        text = self._cursor_exe_edit.text().strip()
        if not text:
            return
        try:
            saved = save_cursor_executable(text)
            if saved != text:
                self._cursor_exe_edit.setText(saved)
        except BackupError as e:
            QMessageBox.warning(self, "提示", str(e))
            self._load_cursor_exe_path()

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择备份保存目录", self._dir_edit.text())
        if d:
            self._dir_edit.setText(d)
            self.refresh_backup_list()

    def _on_backup(self):
        self._check_cursor_status()

        backup_dir = self._dir_edit.text().strip()
        if not backup_dir:
            QMessageBox.warning(self, "提示", "请先选择备份保存目录。")
            return

        if is_cursor_running():
            reply = QMessageBox.question(
                self, "确认备份",
                "将自动关闭 Cursor 以创建备份（备份完成后不会自动启动 Cursor）。\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._set_busy(True)
        self._status_bar.showMessage("正在关闭 Cursor 并创建备份...")

        signals = _run_in_thread(create_backup, backup_dir)
        signals.finished.connect(self._on_backup_done)
        signals.error.connect(self._on_operation_error)

    def _on_backup_done(self, entry: BackupEntry):
        self._set_busy(False)
        self._check_cursor_status()
        self.refresh_backup_list()
        self._status_bar.showMessage(f"备份完成: {entry.name} ({entry.size_mb} MB)")
        QMessageBox.information(
            self, "备份完成",
            f"备份已保存:\n{entry.name}.tar.gz\n大小: {entry.size_mb} MB\n\n"
            "（如 Cursor 曾被关闭，请自行重新打开 Cursor。）"
        )

    def _on_restore(self):
        backup_path = self._get_selected_backup_path()
        if backup_path is None:
            return

        row = self._table.currentRow()
        name = self._table.item(row, 0).text()

        self._check_cursor_status()

        reply = QMessageBox.question(
            self, "确认恢复",
            f"将用以下备份覆盖当前 Cursor User 目录:\n\n{name}\n\n"
            "操作将自动关闭 Cursor，恢复完成后自动重新打开 Cursor。\n"
            "当前数据将被永久替换，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not get_cursor_executable():
            QMessageBox.warning(
                self, "提示",
                "恢复备份后会自动启动 Cursor，请先配置 Cursor.exe 路径\n"
                "（可使用「自动检测」或「浏览」）。",
            )
            return

        self._set_busy(True)
        self._status_bar.showMessage("正在关闭 Cursor、恢复备份并重新启动 Cursor...")

        signals = _run_in_thread(restore_backup, backup_path)
        signals.finished.connect(self._on_restore_done)
        signals.error.connect(self._on_operation_error)

    def _on_restore_done(self, _):
        self._set_busy(False)
        self._check_cursor_status()
        self._status_bar.showMessage("恢复完成，Cursor 已重新启动")
        QMessageBox.information(
            self, "恢复完成",
            "备份已成功恢复，Cursor 已自动重新启动。"
        )

    def _on_delete(self):
        backup_path = self._get_selected_backup_path()
        if backup_path is None:
            return

        row = self._table.currentRow()
        name = self._table.item(row, 0).text()

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除备份 \"{name}\" 吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        delete_backup(backup_path)
        self.refresh_backup_list()
        self._status_bar.showMessage(f"已删除: {name}")

    def _on_operation_error(self, msg: str):
        self._set_busy(False)
        self._check_cursor_status()
        self._status_bar.showMessage("操作失败")
        QMessageBox.critical(self, "错误", msg)