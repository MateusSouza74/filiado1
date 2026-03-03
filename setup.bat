@echo off
chcp 65001 >nul
echo.
echo =====================================================
echo   AFFILIATE BOT - Setup do Ambiente
echo =====================================================
echo.

:: Verifica se Python está instalado
py --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python em https://www.python.org/downloads/
    echo Marque "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

echo [OK] Python encontrado:
py --version
echo.

:: Cria o ambiente virtual
echo [1/3] Criando ambiente virtual (venv)...
py -m venv venv
if errorlevel 1 (
    echo [ERRO] Falha ao criar venv.
    pause
    exit /b 1
)
echo [OK] venv criado.
echo.

:: Ativa o venv e instala dependências
echo [2/3] Instalando dependencias...
call venv\Scripts\activate.bat
py -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.
echo.

:: Cria pastas necessárias
echo [3/3] Criando estrutura de pastas...
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "ml_chrome_profile" mkdir ml_chrome_profile
echo [OK] Pastas criadas.
echo.

echo =====================================================
echo   Setup concluido com sucesso!
echo.
echo   Para iniciar o bot, execute:
echo     start.bat
echo.
echo   Para rodar os testes:
echo     test.bat
echo =====================================================
echo.
pause
