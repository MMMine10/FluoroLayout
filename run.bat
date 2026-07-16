@echo off
setlocal EnableExtensions
title ImmunoFigure Maker
cd /d "%~dp0"

rem Prefer Codex's working Python runtime. A broken Microsoft Store "py" alias
rem is common on Windows, so it must not be checked first.
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PY%" goto run_codex

where python.exe >nul 2>nul
if not errorlevel 1 goto run_python

where py.exe >nul 2>nul
if not errorlevel 1 goto run_py

echo.
echo [ERROR] No usable Python runtime was found.
echo Install Python 3.10 or newer, then run this file again.
echo.
pause
exit /b 1

:run_codex
echo Starting ImmunoFigure Maker...
"%CODEX_PY%" web_app.py %*
goto check_result

:run_python
python.exe -c "import PIL,numpy" >nul 2>nul
if errorlevel 1 goto missing_packages
echo Starting ImmunoFigure Maker...
python.exe web_app.py %*
goto check_result

:run_py
py.exe -3 -c "import PIL,numpy" >nul 2>nul
if errorlevel 1 goto missing_packages
echo Starting ImmunoFigure Maker...
py.exe -3 web_app.py %*
goto check_result

:missing_packages
echo.
echo [ERROR] Python was found, but Pillow or NumPy is missing.
echo Run: python -m pip install Pillow numpy
echo.
pause
exit /b 1

:check_result
set "APP_ERROR=%ERRORLEVEL%"
if "%APP_ERROR%"=="0" exit /b 0
echo.
echo [ERROR] ImmunoFigure Maker stopped with code %APP_ERROR%.
echo Please copy the error text above if you need help.
echo.
pause
exit /b %APP_ERROR%
