@echo off
rem Cree l'environnement Python de 36Frame (a lancer une seule fois).
cd /d "%~dp0"
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
pause

