@echo off
title photo-to-post
echo.
echo  ========================================
echo   photo-to-post - Iniciando servidor...
echo  ========================================
echo.

:: Abrir navegador después de 2 segundos
start "" cmd /c "timeout /t 2 >nul && start http://localhost:5001"

:: Iniciar servidor Flask
cd /d D:\photo-to-post
D:\photo-to-post\venv\Scripts\python.exe -m flask --app web.app run --port 5001

pause
