@echo off
setlocal

set PYTHONOPTIMIZE=0

echo Killing any running instance...
taskkill /f /im "Jira AI.exe" >nul 2>&1

echo [1/2] Checking flet version (downloads client if needed)...
for /f "delims=" %%i in ('python -c "import sys,os,sysconfig; candidates=[os.path.join(os.path.dirname(sys.executable),'Scripts','flet.exe'),os.path.join(sysconfig.get_path('scripts','nt_user'),'flet.exe')]; print(next((p for p in candidates if os.path.exists(p)),candidates[0]))"') do set FLET=%%i

if not exist "%FLET%" (
    echo ERROR: flet.exe not found at: %FLET%
    echo Run: pip install flet
    pause
    exit /b 1
)
"%FLET%" --version

echo.
echo [2/2] Running PyInstaller with Jira AI.spec...
python -m PyInstaller "Jira AI.spec" --noconfirm --distpath dist

if errorlevel 1 (
    echo.
    echo BUILD FAILED. See errors above.
) else (
    echo.
    echo BUILD SUCCEEDED. Output is in: dist\
)

endlocal
pause
