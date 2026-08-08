@echo off
REM ============================================================
REM  Disable J.A.R.V.I.S. autostart.
REM  Removes whichever method is active - the scheduled task or
REM  the Startup-folder shortcut.
REM ============================================================

set "TASK=JARVIS Assistant"
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\JARVIS Assistant.lnk"

set "REMOVED=0"
schtasks /Delete /F /TN "%TASK%" >nul 2>&1
if %ERRORLEVEL% EQU 0 set "REMOVED=1"
if exist "%SHORTCUT%" (
    del "%SHORTCUT%" >nul 2>&1
    set "REMOVED=1"
)

if "%REMOVED%"=="1" (
    echo.
    echo  [OK] Autostart disabled. J.A.R.V.I.S. will no longer start at boot.
) else (
    echo.
    echo  Nothing to do - no autostart entry was found.
    echo  Autostart was not enabled, or was already removed.
)
echo.
pause
