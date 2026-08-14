' ============================================================
'  Silent autostart launcher for J.A.R.V.I.S.
'  Launches main.py with pythonw.exe so NO console window
'  appears when Windows starts the assistant at login.
'
'  Used by the HUD's STARTUP toggle (the Windows scheduled
'  task points at this file). Safe to delete or edit.
' ============================================================
Option Explicit

Dim fso, ws, base, q, py
Set fso = CreateObject("Scripting.FileSystemObject")
Set ws  = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
q = Chr(34)   ' double-quote, for safely quoting paths with spaces

' Make relative paths (conversation history, .env) resolve correctly.
ws.CurrentDirectory = base

' 1. Preferred: the project virtual environment's pythonw.exe.
' 2. Fallback: run.bat, launched with a hidden window.
' Every launch is error-guarded so a failure never pops a dialog at login.
On Error Resume Next
py = base & "ollama_assistant_env\Scripts\pythonw.exe"
If fso.FileExists(py) Then
    ws.Run q & py & q & " " & q & base & "main.py" & q, 0, False
Else
    ws.Run q & base & "run.bat" & q, 0, False
End If
If Err.Number <> 0 Then
    ' Preferred launcher failed - retry once with hidden run.bat.
    Err.Clear
    ws.Run q & base & "run.bat" & q, 0, False
End If
On Error GoTo 0
