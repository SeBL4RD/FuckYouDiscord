@echo off
chcp 65001 > nul
setlocal

set SCRIPT_DIR=%~dp0
set PYTHON_DIR=%SCRIPT_DIR%python_embedded
set PYTHON=%PYTHON_DIR%\python.exe

:: ============================================================
:: SETUP PYTHON EMBARQUE (première fois uniquement)
:: ============================================================
if not exist "%PYTHON%" (
    echo.
    echo === PREMIER LANCEMENT : Installation de Python embarque ===
    echo.
    echo Telechargement de Python 3.11.8...
    curl -L -o "%SCRIPT_DIR%_python_tmp.zip" "https://www.python.org/ftp/python/3.11.8/python-3.11.8-embed-amd64.zip"
    if errorlevel 1 (
        echo ERREUR : telechargement Python echoue. Verifiez votre connexion.
        pause
        exit /b 1
    )

    mkdir "%PYTHON_DIR%"
    tar -xf "%SCRIPT_DIR%_python_tmp.zip" -C "%PYTHON_DIR%"
    del "%SCRIPT_DIR%_python_tmp.zip"

    echo Python installe.
    echo.
)

:: ============================================================
:: LANCEMENT
:: (FFmpeg est telecharge automatiquement par main.py si absent)
:: ============================================================
if "%~1"=="" (
    echo.
    echo  Usage : glissez-deposez une ou plusieurs videos sur ce fichier .bat
    echo  Les videos converties apparaitront dans le dossier "output"
    echo.
    pause
    exit /b 0
)

:: Passage de tous les fichiers droppes en arguments
"%PYTHON%" "%SCRIPT_DIR%main.py" %*
