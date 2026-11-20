@echo off
rem Gera dist\ConversorFTEX.exe (precisa de Python com: pip install -r requirements.txt pyinstaller)
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ConversorFTEX ^
  --icon assets\icone.ico ^
  --add-data "assets\icone.ico;assets" ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module pandas ^
  main.py
