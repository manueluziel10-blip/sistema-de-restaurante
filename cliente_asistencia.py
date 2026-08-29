"""
Cliente de asistencia para las PCs "comandero".

Programa muy ligero -- NO trae su propio servidor de Streamlit ni base
de datos -- solo abre una ventana apuntando al kiosko de asistencia que
corre en la PC principal (ver kiosko_servidor.py / escritorio.py,
PUERTO_KIOSKO). La IP de esa PC se configura una sola vez, escribiéndola
en el archivo servidor_ip.txt que queda junto a este programa.
"""

import sys
from pathlib import Path

import webview

PUERTO_KIOSKO = 8765


def _carpeta_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _leer_ip_servidor() -> str:
    archivo_ip = _carpeta_programa() / "servidor_ip.txt"
    if archivo_ip.exists():
        ip = archivo_ip.read_text(encoding="utf-8").strip()
        if ip:
            return ip
    return ""


def main():
    ip_servidor = _leer_ip_servidor()

    if not ip_servidor:
        html_instrucciones = """
        <html><body style="font-family: sans-serif; padding: 40px; text-align: center;">
            <h2>Falta configurar el servidor</h2>
            <p>Crea un archivo llamado <b>servidor_ip.txt</b> junto a este programa,
            con la dirección IP de la PC principal (donde corre Zully's Sistema).</p>
            <p>Ejemplo de contenido del archivo: <b>192.168.1.50</b></p>
            <p>Luego vuelve a abrir este programa.</p>
        </body></html>
        """
        webview.create_window("Registro de Asistencia - Configuración", html=html_instrucciones, width=600, height=400)
    else:
        url_kiosko = f"http://{ip_servidor}:{PUERTO_KIOSKO}"
        webview.create_window("Registro de Asistencia", url_kiosko, width=900, height=800, min_size=(500, 600))

    webview.start()


if __name__ == "__main__":
    main()
