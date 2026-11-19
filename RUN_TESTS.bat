@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m unittest discover -s tests -v
) else (
  python -m unittest discover -s tests -v
)
pause
