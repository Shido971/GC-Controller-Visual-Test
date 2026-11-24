@echo off
setlocal
cd /d "%~dp0"
title PhobGCC Tool - creation de l'exe

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python introuvable. Installe Python 3.10+ depuis python.org
  echo     en cochant "Add Python to PATH", puis relance ce script.
  pause
  exit /b 1
)

if not exist bin\VisualControllerTest.exe (
  echo [!] bin\VisualControllerTest.exe manquant : l'exe sera cree sans Visual Controller Test.
)

echo === Installation des dependances ===
python -m pip install --upgrade -r requirements.txt pyinstaller || goto :err

echo === Tests ===
python tests\test_core.py || goto :err

echo === Creation de l'exe ===
python -m PyInstaller --noconfirm --clean packaging\phobtool.spec || goto :err

echo.
echo OK : dist\PhobGCCTool\PhobGCCTool.exe
echo Tu peux copier tout le dossier dist\PhobGCCTool ou tu veux.
explorer dist\PhobGCCTool
pause
exit /b 0

:err
echo.
echo [!] Echec, voir les messages ci-dessus.
pause
exit /b 1
