@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion EnableExtensions
cd /d "%~dp0"
set "LOGFILE=build_log.txt"
echo Build started at %DATE% %TIME% > "%LOGFILE%"

set "PY_CMD="
where py >nul 2>nul && py --version >nul 2>nul && set "PY_CMD=py"
if not defined PY_CMD (
    where python >nul 2>nul && python --version >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo [ERROR] Python not found
    echo [ERROR] Python not found >> "%LOGFILE%"
    pause
    exit /b 1
)

echo === [1/4] Python: %PY_CMD% ===
%PY_CMD% --version
echo [OK] %PY_CMD% >> "%LOGFILE%"

echo === [2/4] Install deps ===
%PY_CMD% -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
%PY_CMD% -m pip install -r requirements.txt >> "%LOGFILE%" 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)
echo [OK] deps >> "%LOGFILE%"

echo === [3/4] Clean ===
if exist "build" rmdir /s /q "build" 2>nul
if exist "dist"  rmdir /s /q "dist" 2>nul
if exist "GLLauncher.spec" del /q "GLLauncher.spec" 2>nul

echo === [4/4] Build ===
echo [%TIME%] PyInstaller start >> "%LOGFILE%"
cmd /c "%PY_CMD% -m PyInstaller --noconfirm steam_lister.spec" >> "%LOGFILE%" 2>&1
set "PI_EXIT=!errorlevel!"
echo [%TIME%] PyInstaller exit=!PI_EXIT! >> "%LOGFILE%"
if !PI_EXIT! neq 0 (
    echo [ERROR] PyInstaller failed (!PI_EXIT!)
    echo See: %LOGFILE%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done! dist\GLLauncher.exe
echo ============================================================
echo.
echo  Log: %LOGFILE%
pause
endlocal
