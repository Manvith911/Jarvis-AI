# ============================================================
#  enable_startup_task.ps1
#  Registers the "JARVIS Assistant" scheduled task that fires
#  at system startup and launches the HUD silently.
#
#  Configured so the HUD is ALWAYS there:
#    - Fires at boot, delayed 20 s (drivers/network ready)
#    - If the HUD crashes or exits unexpectedly, restarts it
#      every 1 minute, up to 3 attempts
#    - No execution-time limit (the HUD is a long-running app)
#    - Never starts a second instance if one is already running
#
#  Needs administrator rights (called from enable_autostart.bat).
# ============================================================
$ErrorActionPreference = 'Stop'

$taskName = 'JARVIS Assistant'
$vbs = Join-Path $PSScriptRoot 'autostart.vbs'
$pyw = Join-Path $PSScriptRoot 'ollama_assistant_env\Scripts\pythonw.exe'

if (-not (Test-Path -LiteralPath $vbs)) {
    Write-Host "ERROR: autostart.vbs is missing next to this script." -ForegroundColor Red
    Write-Host "Expected: $vbs"
    exit 1
}

# Action: track the HUD process itself so Task Scheduler can restart it
# on a crash. Point directly at pythonw.exe (GUI-subsystem, no console
# window) with main.py; a crash -> non-zero exit -> restart. Only when
# the venv is missing do we fall back to autostart.vbs, which launches
# pythonw detached (in that case the scheduler cannot see a crash).
if (Test-Path -LiteralPath $pyw) {
    $main = Join-Path $PSScriptRoot 'main.py'
    $action = New-ScheduledTaskAction `
        -Execute $pyw `
        -Argument ('"{0}"' -f $main) `
        -WorkingDirectory $PSScriptRoot
} else {
    # Fallback: wscript.exe "C:\...\autostart.vbs"  (silent pythonw launch)
    $action = New-ScheduledTaskAction `
        -Execute (Join-Path $env:windir 'System32\wscript.exe') `
        -Argument ('"{0}"' -f $vbs)
}

# Trigger: at startup, delayed 20 seconds
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = 'PT20S'

# Principal: the current user, interactive session, no elevation needed
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

# Settings: crash-restart + always-on
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "[OK] Scheduled task '$taskName' registered with crash-restart."
exit 0
