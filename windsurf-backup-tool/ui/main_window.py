from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.backup_engine import BackupWorker, RestoreWorker, format_size, start_worker
from core.path_finder import (
    candidate_related_state_roots,
    default_backup_dir,
    detect_windsurf_config_dir,
    find_chat_related_paths,
)


class MainWindow(QMainWindow):
    """Windsurf IDE 配置备份工具主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("WindsurfBackupTool", "WindsurfBackupTool")
        self.active_jobs = []
        self.icon_path = Path(__file__).resolve().parents[1] / "Windsurf图标.ico"

        self.setWindowTitle("Windsurf 配置备份工具")
        self.resize(1120, 760)
        self.setMinimumSize(980, 680)
        if self.icon_path.exists():
            self.setWindowIcon(QIcon(str(self.icon_path)))

        self.build_ui()
        self.apply_styles()
        self.load_settings()
        self.refresh_chat_paths()
        self.refresh_backup_history()
        self.statusBar().showMessage("就绪")

    def build_ui(self) -> None:
        """创建主界面布局。"""
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(28, 24, 28, 22)
        root_layout.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(18)

        title_area = QVBoxLayout()
        title_area.setSpacing(8)
        title = QLabel("Windsurf Cloud Backup")
        title.setObjectName("title")
        subtitle = QLabel("一键备份设置与 AI 对话快照。默认安全、流程清晰、反馈直观，适合高频使用场景。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.status_label = QLabel("当前状态：就绪")
        self.status_label.setObjectName("statusPill")
        self.status_label.setProperty("state", "idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumWidth(180)

        hero_layout.addLayout(title_area, stretch=1)
        hero_layout.addWidget(self.status_label)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)

        left_column = QVBoxLayout()
        left_column.setSpacing(14)

        path_card = self.create_card("路径")
        path_layout = QGridLayout(path_card)
        path_layout.setContentsMargins(18, 50, 18, 18)
        path_layout.setHorizontalSpacing(10)
        path_layout.setVerticalSpacing(12)

        self.config_dir_edit = QLineEdit()
        self.config_dir_button = QPushButton("选择")
        self.config_dir_button.setObjectName("secondaryButton")
        self.config_dir_button.clicked.connect(self.choose_config_dir)

        self.backup_dir_edit = QLineEdit()
        self.backup_dir_button = QPushButton("选择")
        self.backup_dir_button.setObjectName("secondaryButton")
        self.backup_dir_button.clicked.connect(self.choose_backup_dir)

        path_layout.addWidget(self.create_field_label("Windsurf 配置目录"), 0, 0, 1, 2)
        path_layout.addWidget(self.config_dir_edit, 1, 0)
        path_layout.addWidget(self.config_dir_button, 1, 1)
        path_layout.addWidget(self.create_field_label("备份保存位置"), 2, 0, 1, 2)
        path_layout.addWidget(self.backup_dir_edit, 3, 0)
        path_layout.addWidget(self.backup_dir_button, 3, 1)

        option_card = self.create_card("备份内容")
        option_layout = QVBoxLayout(option_card)
        option_layout.setContentsMargins(18, 50, 18, 18)
        option_layout.setSpacing(12)
        self.settings_checkbox = QCheckBox("用户设置")
        self.settings_checkbox.setToolTip("User/settings.json")
        self.chats_checkbox = QCheckBox("AI 对话历史：完整状态快照")
        self.chats_checkbox.setToolTip("包含 Windsurf / Codeium 相关状态根，用于恢复聊天记录。")
        self.workspace_checkbox = QCheckBox("工作区配置")
        self.workspace_checkbox.setToolTip("User/workspaceStorage/")
        option_layout.addWidget(self.settings_checkbox)
        option_layout.addWidget(self.chats_checkbox)
        option_layout.addWidget(self.workspace_checkbox)

        action_card = self.create_card("操作")
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(18, 50, 18, 18)
        action_layout.setSpacing(12)
        self.backup_button = QPushButton("立即备份")
        self.backup_button.setObjectName("primaryButton")
        self.restore_button = QPushButton("恢复选中备份")
        self.restore_button.setObjectName("primaryButton")
        self.delete_button = QPushButton("删除选中备份")
        self.delete_button.setObjectName("dangerButton")
        self.backup_button.clicked.connect(self.backup_now)
        self.restore_button.clicked.connect(self.restore_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        action_layout.addWidget(self.backup_button)
        action_layout.addWidget(self.restore_button)
        action_layout.addWidget(self.delete_button)

        left_column.addWidget(path_card)
        left_column.addWidget(option_card)
        left_column.addWidget(action_card)
        left_column.addStretch()

        right_column = QVBoxLayout()
        right_column.setSpacing(14)

        chat_card = self.create_card("状态快照范围")
        chat_layout = QVBoxLayout(chat_card)
        chat_layout.setContentsMargins(18, 50, 18, 18)
        chat_layout.setSpacing(10)
        hint = QLabel("这些路径会参与 AI 对话快照。恢复时会保留当前登录状态，不再自动生成 _pre_restore 备份。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.chat_paths_text = QPlainTextEdit()
        self.chat_paths_text.setReadOnly(True)
        self.chat_paths_text.setMaximumHeight(150)
        self.refresh_chat_button = QPushButton("重新检测")
        self.refresh_chat_button.setObjectName("secondaryButton")
        self.refresh_chat_button.clicked.connect(self.refresh_chat_paths)
        chat_footer = QHBoxLayout()
        chat_footer.addStretch()
        chat_footer.addWidget(self.refresh_chat_button)
        chat_layout.addWidget(hint)
        chat_layout.addWidget(self.chat_paths_text)
        chat_layout.addLayout(chat_footer)

        history_card = self.create_card("备份历史")
        history_layout = QVBoxLayout(history_card)
        history_layout.setContentsMargins(18, 50, 18, 18)
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["备份文件", "创建时间", "大小"])
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(False)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        history_layout.addWidget(self.history_table)

        right_column.addWidget(chat_card)
        right_column.addWidget(history_card, stretch=1)

        content_layout.addLayout(left_column, stretch=3)
        content_layout.addLayout(right_column, stretch=5)

        root_layout.addWidget(hero)
        root_layout.addLayout(content_layout, stretch=1)
        self.setCentralWidget(central)

    def create_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        label = QLabel(title, card)
        label.setObjectName("cardTitle")
        label.move(18, 16)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return card

    def create_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #eef6ff;
                color: #1e293b;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                font-size: 14px;
            }
            #hero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #f0f9ff);
                border: 1px solid #c7e8ff;
                border-radius: 24px;
            }
            #title {
                color: #0f172a;
                font-size: 30px;
                font-weight: 800;
                letter-spacing: 0.4px;
            }
            #subtitle, #hint {
                color: #475569;
                line-height: 1.45;
            }
            #statusPill {
                color: #075985;
                background: #e0f2fe;
                border: 1px solid #7dd3fc;
                border-radius: 16px;
                padding: 10px 14px;
                font-weight: 700;
            }
            #statusPill[state="busy"] {
                color: #92400e;
                background: #fef3c7;
                border: 1px solid #fbbf24;
            }
            #statusPill[state="error"] {
                color: #991b1b;
                background: #fee2e2;
                border: 1px solid #fca5a5;
            }
            #card {
                background: #ffffff;
                border: 1px solid #dbeafe;
                border-radius: 20px;
            }
            #cardTitle {
                color: #0f172a;
                font-size: 16px;
                font-weight: 800;
                background: transparent;
            }
            #fieldLabel {
                color: #0369a1;
                font-size: 12px;
                font-weight: 700;
            }
            QLineEdit, QPlainTextEdit {
                color: #0f172a;
                background: #f8fbff;
                border: 1px solid #bfdbfe;
                border-radius: 12px;
                selection-background-color: #7dd3fc;
            }
            QLineEdit {
                min-height: 24px;
                padding: 8px 12px;
            }
            QPlainTextEdit {
                padding: 10px 12px;
            }
            QLineEdit:focus, QPlainTextEdit:focus {
                border: 1px solid #38bdf8;
                background: #ffffff;
            }
            QPlainTextEdit {
                font-family: Consolas, "Microsoft YaHei UI", monospace;
                font-size: 12px;
            }
            QCheckBox {
                color: #1e3a8a;
                spacing: 10px;
                padding: 8px 4px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 6px;
                border: 1px solid #93c5fd;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #67e8f9, stop:1 #60a5fa);
                border: 1px solid #38bdf8;
            }
            QPushButton {
                min-height: 40px;
                border-radius: 12px;
                padding: 0 16px;
                font-weight: 800;
                border: 1px solid transparent;
            }
            #primaryButton {
                color: #ffffff;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #38bdf8, stop:1 #60a5fa);
            }
            #primaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0ea5e9, stop:1 #3b82f6);
            }
            #secondaryButton {
                color: #0c4a6e;
                background: #f0f9ff;
                border: 1px solid #bae6fd;
            }
            #secondaryButton:hover {
                background: #e0f2fe;
            }
            #dangerButton {
                color: #b91c1c;
                background: #fff1f2;
                border: 1px solid #fecdd3;
            }
            #dangerButton:hover {
                background: #ffe4e6;
                color: #991b1b;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
            }
            QTableWidget {
                color: #0f172a;
                background: #ffffff;
                border: 1px solid #dbeafe;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                selection-background-color: #bfdbfe;
                selection-color: #0f172a;
            }
            QHeaderView::section {
                color: #075985;
                background: #f0f9ff;
                border: none;
                border-bottom: 1px solid #dbeafe;
                padding: 10px;
                font-weight: 800;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eef2ff;
            }
            QStatusBar {
                color: #475569;
                background: #eef6ff;
                border-top: 1px solid #dbeafe;
            }
            QMessageBox {
                background: #ffffff;
            }
            """
        )

    def load_settings(self) -> None:
        """从 QSettings 读取用户上次选择。"""
        self.config_dir_edit.setText(
            self.settings.value("config_dir", str(detect_windsurf_config_dir()), type=str)
        )
        self.backup_dir_edit.setText(
            self.settings.value("backup_dir", str(default_backup_dir()), type=str)
        )
        self.settings_checkbox.setChecked(self.settings.value("include_settings", True, type=bool))
        self.chats_checkbox.setChecked(self.settings.value("include_chats", True, type=bool))
        self.workspace_checkbox.setChecked(self.settings.value("include_workspace", True, type=bool))

    def save_settings(self) -> None:
        """保存用户当前选择到 QSettings。"""
        self.settings.setValue("config_dir", self.config_dir_edit.text())
        self.settings.setValue("backup_dir", self.backup_dir_edit.text())
        self.settings.setValue("include_settings", self.settings_checkbox.isChecked())
        self.settings.setValue("include_chats", self.chats_checkbox.isChecked())
        self.settings.setValue("include_workspace", self.workspace_checkbox.isChecked())

    def choose_config_dir(self) -> None:
        """手动选择 Windsurf 配置目录。"""
        directory = QFileDialog.getExistingDirectory(self, "选择 Windsurf 配置目录", self.config_dir_edit.text())
        if directory:
            self.config_dir_edit.setText(directory)
            self.save_settings()
            self.refresh_chat_paths()

    def choose_backup_dir(self) -> None:
        """手动选择备份保存目录。"""
        directory = QFileDialog.getExistingDirectory(self, "选择备份保存位置", self.backup_dir_edit.text())
        if directory:
            self.backup_dir_edit.setText(directory)
            self.save_settings()
            self.refresh_backup_history()

    def refresh_chat_paths(self) -> None:
        """刷新界面中的 AI 对话相关路径列表。"""
        config_dir = self.config_dir_edit.text().strip()
        if not config_dir:
            self.chat_paths_text.setPlainText("未设置 Windsurf 配置目录。")
            return

        paths = find_chat_related_paths(config_dir)
        snapshot_roots = [path for _, path in candidate_related_state_roots(config_dir)]
        visible_paths = list(dict.fromkeys([*snapshot_roots, *paths]))
        if not visible_paths:
            self.chat_paths_text.setPlainText("未检测到对话相关路径。")
            return

        self.chat_paths_text.setPlainText("\n".join(str(path) for path in visible_paths))

    def refresh_backup_history(self) -> None:
        """刷新备份历史表格。"""
        backup_dir = Path(self.backup_dir_edit.text()).expanduser()
        backup_dir.mkdir(parents=True, exist_ok=True)
        archives = sorted(backup_dir.glob("windsurf_backup_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)

        self.history_table.setRowCount(0)
        for archive in archives:
            row = self.history_table.rowCount()
            stat = archive.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            self.history_table.insertRow(row)
            name_item = QTableWidgetItem(archive.name)
            name_item.setData(Qt.ItemDataRole.UserRole, str(archive))
            self.history_table.setItem(row, 0, name_item)
            self.history_table.setItem(row, 1, QTableWidgetItem(modified))
            self.history_table.setItem(row, 2, QTableWidgetItem(format_size(stat.st_size)))

    def selected_archive_path(self) -> str | None:
        """获取备份历史中当前选中的 zip 路径。"""
        selected = self.history_table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.history_table.item(selected[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_busy(self, busy: bool) -> None:
        """切换操作按钮启用状态。"""
        self.backup_button.setEnabled(not busy)
        self.restore_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)
        self.config_dir_button.setEnabled(not busy)
        self.backup_dir_button.setEnabled(not busy)
        self.refresh_chat_button.setEnabled(not busy)
        self.status_label.setProperty("state", "busy" if busy else "idle")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def update_status(self, message: str) -> None:
        self.statusBar().showMessage(message)
        self.status_label.setText(f"当前状态：{message}")
        state = "idle"
        if "失败" in message:
            state = "error"
        elif any(keyword in message for keyword in ["正在", "扫描", "打包", "写入", "恢复"]):
            state = "busy"
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def start_background_job(self, worker) -> None:
        """启动后台任务并保持引用，避免打包后任务被提前回收。"""
        thread = start_worker(worker)
        job = {"thread": thread, "worker": worker}
        self.active_jobs.append(job)

        def cleanup() -> None:
            if job in self.active_jobs:
                self.active_jobs.remove(job)

        thread.finished.connect(cleanup)

    def backup_now(self) -> None:
        """启动立即备份任务。"""
        self.save_settings()
        if not any(
            [
                self.settings_checkbox.isChecked(),
                self.chats_checkbox.isChecked(),
                self.workspace_checkbox.isChecked(),
            ]
        ):
            QMessageBox.warning(self, "无法备份", "请至少选择一项备份内容。")
            return

        worker = BackupWorker(
            self.config_dir_edit.text(),
            self.backup_dir_edit.text(),
            self.settings_checkbox.isChecked(),
            self.chats_checkbox.isChecked(),
            self.workspace_checkbox.isChecked(),
        )
        worker.progress.connect(self.update_status)
        worker.finished.connect(self.on_backup_finished)
        worker.failed.connect(self.on_worker_failed)
        self.set_busy(True)
        self.update_status("正在备份...")
        self.start_background_job(worker)

    def restore_selected(self) -> None:
        """确认后启动恢复选中备份任务。"""
        archive_path = self.selected_archive_path()
        if not archive_path:
            QMessageBox.information(self, "请选择备份", "请先在备份历史中选择一个备份文件。")
            return

        reply = QMessageBox.question(
            self,
            "确认恢复",
            "恢复会覆盖当前 Windsurf 配置和聊天状态。\n\n工具会先自动关闭 Windsurf，恢复成功后自动重新打开。\n恢复时会尽量保留当前登录状态，但不会自动创建 _pre_restore 安全备份。\n\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.save_settings()
        worker = RestoreWorker(archive_path, self.config_dir_edit.text())
        worker.progress.connect(self.update_status)
        worker.finished.connect(self.on_restore_finished)
        worker.failed.connect(self.on_worker_failed)
        self.set_busy(True)
        self.update_status("正在恢复...")
        self.start_background_job(worker)

    def delete_selected(self) -> None:
        """删除备份历史中选中的 zip 文件。"""
        archive_path = self.selected_archive_path()
        if not archive_path:
            QMessageBox.information(self, "请选择备份", "请先在备份历史中选择一个备份文件。")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除这个备份文件吗？\n{archive_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            Path(archive_path).unlink()
            self.refresh_backup_history()
            self.update_status("备份文件已删除")
        except OSError as exc:
            QMessageBox.critical(self, "删除失败", f"无法删除备份文件：{exc}")

    def on_backup_finished(self, archive_path: str) -> None:
        """处理备份完成结果。"""
        self.set_busy(False)
        self.refresh_backup_history()
        self.update_status("备份完成")
        QMessageBox.information(self, "备份完成", f"已创建备份：\n{archive_path}")

    def on_restore_finished(self, archive_path: str) -> None:
        """处理恢复完成结果。"""
        self.set_busy(False)
        self.refresh_backup_history()
        self.refresh_chat_paths()
        self.update_status("恢复完成")
        QMessageBox.information(self, "恢复完成", f"已恢复备份：\n{archive_path}")

    def on_worker_failed(self, message: str) -> None:
        """处理后台任务失败结果。"""
        self.set_busy(False)
        self.update_status("操作失败")
        QMessageBox.critical(self, "操作失败", message)

    def closeEvent(self, event) -> None:  # noqa: N802
        """窗口关闭前保存用户设置。"""
        self.save_settings()
        super().closeEvent(event)