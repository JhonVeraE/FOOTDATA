@echo off
rem FOOTDATA: ejecucion desatendida desde la PC (respaldo de GitHub Actions).
rem Uso: footdata_run.cmd daily | weekly
setlocal EnableExtensions
set "MODE=%~1"
if /i not "%MODE%"=="daily" if /i not "%MODE%"=="weekly" (echo Uso: %~nx0 daily^|weekly & exit /b 2)
set "LOGDIR=%LOCALAPPDATA%\FOOTDATA\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd')"') do set "TODAY=%%d"
if /i not "%~2"=="__logged" (
  call "%~f0" %MODE% __logged >> "%LOGDIR%\%MODE%_%TODAY%.log" 2>&1
  exit /b %ERRORLEVEL%
)
echo ===== %DATE% %TIME% FOOTDATA %MODE% =====
cd /d "%~dp0..\.."
call "%~dp0footdata_env.cmd"
set "PY=python"
where python >nul 2>&1 || set "PY=py -3"

git fetch origin main || exit /b 1
rem Si GitHub Actions ya publico hoy, la PC no repite el trabajo.
for /f %%h in ('git log origin/main --since^="%TODAY% 00:00" --grep^="FOOTDATA auto %MODE% %TODAY%" --format^=%%h') do (
  echo Ya publicado hoy por GitHub Actions ^(%%h^). Nada que hacer.
  exit /b 0
)
git pull --rebase --autostash origin main || exit /b 1

%PY% run_pipeline.py --%MODE% || (echo ERROR en el pipeline & exit /b 1)
set "PYTHONPATH=src"
%PY% -m unittest discover -s tests || (echo Pruebas fallidas: no se publica & exit /b 1)

git add -A data web
git diff --cached --quiet && (echo Sin cambios & exit /b 0)
git commit -m "FOOTDATA auto %MODE% %TODAY% (PC)" || exit /b 1
for /l %%i in (1,1,3) do (
  git pull --rebase origin main && git push origin HEAD:main && (echo Publicado & exit /b 0)
  timeout /t 15 /nobreak >nul
)
echo No se pudo publicar
exit /b 1
