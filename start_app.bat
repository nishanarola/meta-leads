@echo off
echo ================================
echo    Enacle Leads App Starting...
echo ================================

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found! Downloading...
    curl -o python_installer.exe https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe
    echo Installing Python...
    python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
    del python_installer.exe
)

:: Install requirements
echo Installing requirements...
pip install -r requirements.txt -q

:: Setup secrets
python setup_secrets.py

:: Start app
cd /d "%~dp0"
python -m streamlit run sheet_groq.py
pause