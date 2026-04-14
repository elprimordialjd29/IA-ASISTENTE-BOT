@echo off
title VANEGAS - Instalación
cd /d "%~dp0"

echo.
echo  ================================================
echo    VANEGAS - Instalación de Dependencias
echo  ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.9+ requerido. Descárgalo en python.org
    pause
    exit /b 1
)

echo Creando entorno virtual...
python -m venv venv

echo Activando entorno virtual...
call venv\Scripts\activate.bat

echo Instalando dependencias...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo  ================================================
echo    Instalación completada exitosamente!
echo  ================================================
echo.
echo  Ahora configura VANEGAS:
echo    1. Copia .env.example como .env
echo    2. Edita .env con tus credenciales, O
echo    3. Ejecuta: python setup_vanegas.py
echo.
pause
