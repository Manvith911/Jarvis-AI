@echo off
REM ============================================================
REM  Enable J.A.R.V.I.S. at Windows startup.
REM
REM  Preferred: a Task Scheduler task that fires at boot and
REM  launches the HUD (silently via autostart.vbs -> pythonw)
REM  as soon as your desktop is ready.
REM
REM  If Task Scheduler needs administrator rights you don't have,
REM  this script automatically falls back to a Startup-folder
REM  shortcut - same visible behavior (silent launch at logon).
REM
REM  Run this file ONCE (double-click it). It is safe - it only
REM  creates an autostart entry you can remove with
REM  disable_autostart.bat
REM ============================================================

set "TASK=JARVIS Assistant"
set "VBS=%~dp0autostart.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\JARVIS Assistant.lnk"

if not exist "%VBS%" (
    echo ERROR: autostart.vbs is missing next to this file.
    echo        Expected: %VBS%
    pause
    exit /b 1
)

if not exist "%~dp0enable_startup_task.ps1" (
    echo ERROR: enable_startup_task.ps1 is missing next to this file.
    echo        Expected: %~dp0enable_startup_task.ps1
    pause
    exit /b 1
)

REM Clear any old autostart entries first, so it never launches twice.
if exist "%SHORTCUT%" del "%SHORTCUT%" >nul 2>&1
schtasks /Delete /F /TN "%TASK%" >nul 2>&1

REM --- Method 1 (preferred): scheduled task firing at boot -------------
REM stderr is silenced - the fallback message below explains any failure.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0enable_startup_task.ps1" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo.
    echo  [OK] Startup task created: "%TASK%"
    echo       J.A.R.V.I.S. will launch at boot, about 20 seconds in once
    echo       drivers and network are ready - right as your desktop
    echo       appears - silently, no console window.
    echo       If it ever crashes, it restarts automatically up to 3 times.
    echo.
    echo  To stop it, double-click  disable_autostart.bat
    goto :done
)

REM --- Check for a task left by a previous elevated run -----------------
REM Creating/deleting tasks needs admin, so a task from an earlier
REM administrator run survives the cleanup above. Keep it instead of
REM adding a shortcut, otherwise J.A.R.V.I.S. would launch twice at boot.
schtasks /Query /TN "%TASK%" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo.
    echo  [OK] Startup task already exists: "%TASK%" - keeping it.
    echo       J.A.R.V.I.S. will launch at boot via the scheduled task.
    echo.
    echo  To stop it, double-click  disable_autostart.bat
    goto :done
)

REM --- Method 2 (fallback): Startup folder, no admin needed ------------
echo  Could not create the scheduled task - this usually needs
echo  administrator rights. Falling back to the Startup folder,
echo  where J.A.R.V.I.S. will still start silently at logon.

if not exist "%STARTUP%" (
    echo ERROR: Could not find the Startup folder:
    echo        %STARTUP%
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = $env:windir + '\System32\wscript.exe';" ^
  "$s.Arguments = [char]34 + '%VBS%' + [char]34;" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.Description = 'J.A.R.V.I.S. AI Assistant - silent autostart';" ^
  "$s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo  [OK] Autostart ENABLED - Startup folder fallback.
    echo       J.A.R.V.I.S. will start silently when you log in.
    echo.
    echo  To stop it, double-click  disable_autostart.bat
    echo  To use Task Scheduler instead, run this file as Administrator.
) else (
    echo.
    echo  [!!] FAILED to create autostart - neither method worked.
    echo       Try right-clicking this file and choosing "Run as administrator".
)

:done
echo.
pause
