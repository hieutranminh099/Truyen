@echo off
setlocal
chcp 65001 >nul
echo This script must be run from an Administrator Windows terminal.
echo Only use Tailscale Serve PRIVATE, never Funnel.
echo Launch START_NOVEL.bat before running this script.
echo.
where tailscale >nul 2>nul
if errorlevel 1 (
  echo Install Tailscale for Windows first: https://tailscale.com/download
  pause
  exit /b 1
)
tailscale serve --bg 8765
tailscale serve status
pause
