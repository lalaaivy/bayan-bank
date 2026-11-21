
@echo off
setlocal

cd /d "%~dp0"

if not exist "logs" mkdir "logs"

set "LOG_FILE=%~dp0logs\overdue_check.log"

echo. >> "%LOG_FILE%"
echo ========================================= >> "%LOG_FILE%"
echo Bayan Bank - Overdue Installment Checker >> "%LOG_FILE%"
echo Started: %date% %time% >> "%LOG_FILE%"
echo ========================================= >> "%LOG_FILE%"

if not exist "venv\Scripts\python.exe" goto missing_venv

venv\Scripts\python.exe manage.py check_overdue >> "%LOG_FILE%" 2>&1

set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" goto success

echo ERROR: Overdue checking failed. >> "%LOG_FILE%"
goto finish

:missing_venv
echo ERROR: Virtual environment Python was not found. >> "%LOG_FILE%"
echo Expected: %~dp0venv\Scripts\python.exe >> "%LOG_FILE%"
set "EXIT_CODE=1"
goto finish

:success
echo Overdue checking completed successfully. >> "%LOG_FILE%"
set "EXIT_CODE=0"

:finish
echo Finished: %date% %time% >> "%LOG_FILE%"
echo ========================================= >> "%LOG_FILE%"

endlocal & exit /b %EXIT_CODE%
