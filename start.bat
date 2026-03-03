@echo off
chcp 65001 >nul
echo.
echo =====================================================
echo   AFFILIATE BOT - Iniciando...
echo =====================================================
echo.

:: Verifica se o venv existe
if not exist "venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual nao encontrado.
    echo Execute setup.bat primeiro!
    pause
    exit /b 1
)

:: Ativa o venv
call venv\Scripts\activate.bat

:: Inicia o bot (com verificação ML)
echo Iniciando o bot...
echo Pressione Ctrl+C para parar.
echo.
python main.py

echo.
echo [Bot encerrado]
pause
