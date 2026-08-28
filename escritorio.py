"""
Punto de entrada de la app de escritorio.

Levanta el servidor de Streamlit (app.py) en un hilo de fondo dentro del
mismo proceso -- así funciona también empaquetado con PyInstaller, sin
necesitar una instalación de Python aparte ni abrir una consola -- y abre
una ventana nativa (pywebview) apuntando a ese servidor local. La base de
datos sigue siendo la misma SQLite local de siempre (ver database.py).
"""

import socket
import sys
import threading
import time
from pathlib import Path

import webview


def _ruta_app() -> str:
    # app.py es código: si está empaquetado, se lee de la carpeta temporal
    # donde PyInstaller lo descomprime (sys._MEIPASS) -- a diferencia de la
    # base de datos (ver database.py), no importa que esa carpeta sea
    # temporal porque aquí no se guarda nada, solo se lee el script.
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).parent
    return str(base / "app.py")


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iniciar_streamlit(puerto: int):
    from streamlit.web import bootstrap, cli as stcli

    # Streamlit intenta registrar manejadores de señales (SIGTERM/SIGINT),
    # lo cual solo funciona en el hilo principal. Aquí corre en un hilo de
    # fondo (el hilo principal lo ocupa la ventana de pywebview), y no
    # necesitamos manejo de señales: la app se cierra junto con el proceso
    # al cerrar la ventana. Se desactiva para evitar el crash.
    bootstrap._set_up_signal_handler = lambda server: None

    sys.argv = [
        "streamlit", "run", _ruta_app(),
        "--server.port", str(puerto),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    stcli.main()


def _esperar_servidor(puerto: int, intentos: int = 60):
    for _ in range(intentos):
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    puerto = _puerto_libre()

    hilo_servidor = threading.Thread(target=_iniciar_streamlit, args=(puerto,), daemon=True)
    hilo_servidor.start()

    if not _esperar_servidor(puerto):
        raise RuntimeError("El servidor local no arrancó a tiempo.")

    webview.create_window(
        "Zully's Men's Club - Sistema Integral",
        f"http://127.0.0.1:{puerto}",
        width=1400, height=900, min_size=(1000, 700)
    )
    webview.start()


if __name__ == "__main__":
    main()
