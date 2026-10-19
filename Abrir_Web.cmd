@echo off
cd /d "%~dp0"
py -3 open_web.py
if errorlevel 1 (
  echo No se pudo abrir la web. Comprueba que Python este instalado.
  pause
)
