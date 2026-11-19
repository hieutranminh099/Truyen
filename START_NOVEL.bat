@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m novelengine serve
) else (
  python -m novelengine serve
)
echo.
echo Novel Engine has stopped. Read any error above.
pause
