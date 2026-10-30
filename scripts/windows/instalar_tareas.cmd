@echo off
rem Registra las tareas programadas de FOOTDATA en Windows (una sola vez).
rem Diario 06:30 y jueves 10:30 (hora de la PC). GitHub Actions corre antes
rem (05:00 y jueves 10:00 Lima); si ya publico, la PC no repite el trabajo.
setlocal
set "HERE=%~dp0"
schtasks /Create /F /TN "FOOTDATA\Diario" /SC DAILY /ST 06:30 /TR "\"%HERE%footdata_daily.cmd\"" || goto :error
schtasks /Create /F /TN "FOOTDATA\Semanal" /SC WEEKLY /D THU /ST 10:30 /TR "\"%HERE%footdata_weekly.cmd\"" || goto :error
echo Tareas registradas. Registros en %LOCALAPPDATA%\FOOTDATA\logs
schtasks /Query /TN "FOOTDATA\Diario"
schtasks /Query /TN "FOOTDATA\Semanal"
exit /b 0
:error
echo No se pudieron registrar las tareas.
exit /b 1
