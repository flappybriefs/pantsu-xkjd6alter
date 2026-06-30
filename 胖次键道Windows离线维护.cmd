@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0tools\pantsu_windows_maintenance.py"
  pause
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0tools\pantsu_windows_maintenance.py"
  pause
  exit /b %errorlevel%
)

echo 没有找到 Python。
echo 请先安装 Python 3，或者从 Microsoft Store / python.org 安装。
echo 安装后重新双击本文件。
pause
