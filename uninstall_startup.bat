@echo off
:: Yeelight Tray - Remove from Windows Startup

echo Removing Yeelight Tray from Windows Startup...

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_FOLDER%\Yeelight Tray.lnk"
set "SCRIPT_DIR=%~dp0"
set "VBS_FILE=%SCRIPT_DIR%launch_yeelight.vbs"

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo Removed startup shortcut.
) else (
    echo No startup shortcut found.
)

if exist "%VBS_FILE%" (
    del "%VBS_FILE%"
    echo Removed VBS launcher.
)

echo.
echo Yeelight Tray will no longer start with Windows.
echo.
pause

