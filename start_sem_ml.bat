@echo off
chcp 65001 >nul
echo.
echo =====================================================
echo   AFFILIATE BOT - Iniciando (sem verificacao ML)
echo =====================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERRO] Execute setup.bat primeiro!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo Iniciando sem verificacao de login ML...
echo Pressione Ctrl+C para parar.
echo.
python main.py --no-ml-check

echo.
echo [Bot encerrado]
pause
