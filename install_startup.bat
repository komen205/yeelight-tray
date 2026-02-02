@echo off
:: Yeelight Tray - Add to Windows Startup
:: Run this script as Administrator for best results

echo Adding Yeelight Tray to Windows Startup...

:: Get the script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Create VBS launcher (runs without console window)
echo Set WshShell = CreateObject("WScript.Shell") > "%SCRIPT_DIR%\launch_yeelight.vbs"
echo WshShell.Run "pythonw ""%SCRIPT_DIR%\yeelight_tray.pyw""", 0, False >> "%SCRIPT_DIR%\launch_yeelight.vbs"

:: Create shortcut in Startup folder
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_FOLDER%\Yeelight Tray.lnk"

:: Use PowerShell to create shortcut
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%SCRIPT_DIR%\launch_yeelight.vbs'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'Yeelight System Tray Controller'; $s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo SUCCESS! Yeelight Tray will now start automatically with Windows.
    echo.
    echo Shortcut created at:
    echo %SHORTCUT%
) else (
    echo.
    echo ERROR: Could not create startup shortcut.
    echo Please run this script as Administrator.
)

echo.
pause

