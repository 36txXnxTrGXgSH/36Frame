@echo off
rem Lance 36Frame. Glissez une image sur ce fichier pour l'ouvrir directement.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" lancer.pyw %*

