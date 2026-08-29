@echo off
REM Genera el cliente de asistencia para las PCs comandero (ClienteAsistencia.exe)
REM en dist\ClienteAsistencia. Requiere: pip install -r requirements-desktop.txt
REM Mucho mas ligero que build_escritorio.bat: no lleva Streamlit ni el sistema completo.

pyinstaller --name ClienteAsistencia --onedir --noconfirm ^
  --collect-all pywebview ^
  cliente_asistencia.py

echo.
echo Listo. El programa quedo en dist\ClienteAsistencia\ClienteAsistencia.exe
echo IMPORTANTE: crea ahi mismo un archivo servidor_ip.txt con la IP de la PC principal.
pause
