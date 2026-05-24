# 打包 Cursor 备份工具为独立 exe
# 用法: 在 PowerShell 中执行 .\build.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ">>> 安装依赖..." -ForegroundColor Cyan
pip install -r requirements.txt pyinstaller

$DistDir = Split-Path $PSScriptRoot -Parent

Write-Host ">>> 开始打包..." -ForegroundColor Cyan
Write-Host "    输出目录: $DistDir" -ForegroundColor Gray
python -m PyInstaller --noconfirm --clean --distpath $DistDir build.spec

$exe = Join-Path $DistDir "Cursor备份工具.exe"
if (Test-Path $exe) {
    Write-Host ""
    Write-Host "打包成功!" -ForegroundColor Green
    Write-Host "可执行文件: $exe" -ForegroundColor Green
    Write-Host "双击即可运行，无需安装 Python。" -ForegroundColor Green
} else {
    Write-Host "打包失败，请检查上方错误信息。" -ForegroundColor Red
    exit 1
}
