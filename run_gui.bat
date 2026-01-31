@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if %errorlevel%==0 (
  set "PYTHON_CMD=py -3.10"
) else (
  where python >nul 2>&1
  if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Python not found. Install Python 3.10+ and try again.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYTHON_CMD% -m venv .venv
  if %errorlevel% neq 0 exit /b 1
)

set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PIP=.venv\Scripts\pip.exe"

echo Installing dependencies...
%VENV_PIP% install -e ".[gui]"
if %errorlevel% neq 0 exit /b 1

echo Starting GUI...
%VENV_PY% -m name_splitter.app.cli --gui
