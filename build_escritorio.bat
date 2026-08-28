@echo off
REM Genera la app de escritorio (ZullysSistema.exe) en dist\ZullysSistema.
REM Requiere: pip install -r requirements-desktop.txt

pyinstaller --name ZullysSistema --onedir --noconfirm ^
  --collect-all streamlit ^
  --collect-all pandas ^
  --collect-all sqlalchemy ^
  --collect-all psycopg2 ^
  --collect-all openpyxl ^
  --collect-all xlrd ^
  --collect-all reportlab ^
  --hidden-import win32print ^
  --hidden-import win32api ^
  --hidden-import win32con ^
  --add-data "app.py;." ^
  --add-data "models.py;." ^
  --add-data "comisiones.py;." ^
  --add-data "database.py;." ^
  --add-data "config_local.py;." ^
  escritorio.py

echo.
echo Listo. El programa quedo en dist\ZullysSistema\ZullysSistema.exe
pause
