@echo off
setlocal
set "MIXED_BOT_ROOT=%~dp0.."
set "MIXED_BOT_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%MIXED_BOT_PYTHON%" (
    echo The project .venv is missing. Follow the local runtime setup first.
    exit /b 1
)
pushd "%MIXED_BOT_ROOT%"
if errorlevel 1 exit /b 1
"%MIXED_BOT_PYTHON%" "%~dp0mixed_case_bot.py" %*
set "MIXED_BOT_EXIT=%ERRORLEVEL%"
popd
exit /b %MIXED_BOT_EXIT%
