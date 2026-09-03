@echo off
chcp 936 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo 未找到 Python！请先安装 Python 3 并勾选“Add to PATH”。
  echo.
  pause
  exit /b 1
)
echo ============================================
echo   汉字字帖 A4 生成器  正在启动...
echo ============================================
echo.
python app.py
if errorlevel 1 (
  echo.
  echo 启动失败！请检查依赖是否安装：
  echo   pip install -r requirements.txt
  echo.
  pause
)
