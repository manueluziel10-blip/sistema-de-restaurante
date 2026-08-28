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
  --add-data "app.py;." ^
  --add-data "models.py;." ^
  --add-data "comisiones.py;." ^
  --add-data "database.py;." ^
  escritorio.py

echo.
echo Listo. El programa quedo en dist\ZullysSistema\ZullysSistema.exe
pause
