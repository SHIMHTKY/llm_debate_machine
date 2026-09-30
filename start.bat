@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

set "START_PYTHON="
if defined DEBATE_STUDIO_PYTHON (
    set "START_PYTHON=%DEBATE_STUDIO_PYTHON%"
    goto run
)

call :try_python "%CD%\.venv\Scripts\python.exe"
call :try_python "%CD%\venv\Scripts\python.exe"
if defined CONDA_PREFIX call :try_python "%CONDA_PREFIX%\python.exe"
for %%B in ("%LOCALAPPDATA%\miniforge3" "%USERPROFILE%\miniforge3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3") do call :try_python "%%~B\envs\why_lldbm\python.exe"
for /f "delims=" %%P in ('where python 2^>nul') do call :try_python "%%P"

if not defined START_PYTHON (
    echo No Python 3.10+ environment with the project dependencies was found.
    echo Install requirements.txt in your environment, then try again.
    echo Or set DEBATE_STUDIO_PYTHON to the full path of its python.exe.
    goto failed
)

:run
if not exist "%START_PYTHON%" (
    echo Python executable not found: "%START_PYTHON%"
    goto failed
)
"%START_PYTHON%" "scripts\start.py" %*
set "START_RESULT=%ERRORLEVEL%"
popd
if not "%START_RESULT%"=="0" pause
exit /b %START_RESULT%

:try_python
if defined START_PYTHON exit /b 0
if not exist "%~1" exit /b 0
if /i "%~1"=="%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" exit /b 0
"%~1" "scripts\start.py" --check >nul 2>&1
if not errorlevel 1 set "START_PYTHON=%~1"
exit /b 0

:failed
popd
pause
exit /b 1
