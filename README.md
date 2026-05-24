# Cursor & Windsurf 备份工具

一个面向 **Cursor** 和 **Windsurf** 的桌面备份工具集，基于 **Python + PySide6** 构建。

## 项目结构

- `cursor-backup-tool/`  
  Cursor 备份图形工具源码
- `windsurf-backup-tool/`  
  Windsurf 备份图形工具源码
- `Cursor备份工具.exe`  
  已打包的 Cursor 可执行文件（根目录产物）

## 运行环境

- Python 3.10+
- Windows（当前打包与产物主要面向 Windows）

## 安装依赖

建议为两个工具分别使用独立环境安装依赖。

### Cursor 备份工具

```bash
cd cursor-backup-tool
pip install -r requirements.txt
```

### Windsurf 备份工具

```bash
cd windsurf-backup-tool
pip install -r requirements.txt
```

## 源码运行

### Cursor 备份工具

```bash
cd cursor-backup-tool
python main.py
```

### Windsurf 备份工具

```bash
cd windsurf-backup-tool
python main.py
```

## 打包说明

仓库中已包含打包所需的 spec/脚本和部分构建产物。

示例：

- Cursor 工具：`cursor-backup-tool/build.ps1`、`cursor-backup-tool/build.spec`
- Windsurf 工具：`windsurf-backup-tool/*.spec`

可使用 PyInstaller 配合对应 spec 文件进行打包。

## 界面预览

### Windsurf 备份工具

![Windsurf 界面预览](./Windsurf界面图.png)

- 提供配置路径与备份目录选择
- 支持一键备份、恢复、删除备份
- 展示状态快照范围与备份历史

### Cursor 备份工具

![Cursor 界面预览](./Cursor界面图.png)

- 自动检测 Cursor 程序与用户配置路径
- 支持创建备份、恢复备份、删除备份
- 支持备份列表刷新与容量展示

## 说明

- 当前仓库包含部分生成产物（如 `build/`、`dist/`、`.pyc`）。
- 如果你希望仓库更干净，可后续补充 `.gitignore` 并清理生成产物。