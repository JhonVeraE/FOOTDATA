@echo off
rem Localiza git y python aunque no esten en el PATH (Git for Windows, GitHub Desktop, Python de usuario).
where git >nul 2>&1 && goto :python
for %%G in ("%ProgramFiles%\Git\cmd" "%ProgramFiles(x86)%\Git\cmd" "%LOCALAPPDATA%\Programs\Git\cmd" "%USERPROFILE%\scoop\shims") do (
  if exist "%%~G\git.exe" (set "PATH=%%~G;%PATH%" & goto :python)
)
for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
  if exist "%%~D\resources\app\git\cmd\git.exe" set "PATH=%%~D\resources\app\git\cmd;%PATH%"
)
:python
where python >nul 2>&1 && goto :done
where py >nul 2>&1 && goto :done
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if exist "%%~D\python.exe" set "PATH=%%~D;%%~D\Scripts;%PATH%"
)
:done
exit /b 0
