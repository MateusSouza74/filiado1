@echo off
chcp 65001 >nul
echo.
echo =====================================================
echo   AFFILIATE BOT - Rodando Testes
echo =====================================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERRO] Execute setup.bat primeiro!
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

python -m pytest tests/ -v

echo.
pause
