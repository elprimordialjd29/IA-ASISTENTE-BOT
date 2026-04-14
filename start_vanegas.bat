@echo off
title VANEGAS - Asistente Personal Autónomo
cd /d "%~dp0"

echo.
echo  ================================================
echo    VANEGAS - Asistente Personal Autonomo
echo    Powered by Claude Opus 4.6
echo  ================================================
echo.

:: Verificar que Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no está instalado o no está en el PATH
    pause
    exit /b 1
)

:: Verificar que el .env existe
if not exist ".env" (
    echo No se encontró el archivo .env
    echo Ejecutando configuración inicial...
    python setup_vanegas.py
    pause
    exit /b 0
)

:: Verificar dependencias
if not exist "venv\Scripts\activate.bat" (
    echo Creando entorno virtual...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Instalando dependencias...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: Iniciar VANEGAS
echo Iniciando VANEGAS...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo VANEGAS terminó con error.
    pause
)
