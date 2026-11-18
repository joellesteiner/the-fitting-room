@echo off
cd /d "%~dp0"
title The Fitting Room - Keep this window open
where py >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
echo Preparing The Fitting Room...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Running automated checks...
%PY% -m unittest discover -s tests -v
if errorlevel 1 goto failed
start "" "http://127.0.0.1:8799"
%PY% -u server.py
:failed
echo.
echo The server stopped. Read the error above. This window will remain open.
pause
