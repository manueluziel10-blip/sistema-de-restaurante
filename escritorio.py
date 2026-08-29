"""
Punto de entrada de la app de escritorio.

Levanta el servidor de Streamlit (app.py) en un hilo de fondo dentro del
mismo proceso -- así funciona también empaquetado con PyInstaller, sin
necesitar una instalación de Python aparte ni abrir una consola -- y abre
una ventana nativa (pywebview) apuntando a ese servidor local. La base de
datos sigue siendo la misma SQLite local de siempre (ver database.py).

Además, arranca como proceso hijo un SEGUNDO servidor de Streamlit
(kiosko_servidor.py) en la red local, en el puerto fijo PUERTO_KIOSKO --
ese servidor solo tiene la pantalla de registrar asistencia (nada de
login ni el resto del sistema), para que las PCs "comandero" conectadas
por red puedan usarlo sin poder llegar a ninguna otra parte de la app.
Este mismo .exe, invocado con la bandera --kiosko-servidor, es el que
corre ese segundo servidor (ver _en_modo_kiosko_servidor / main).
"""

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import webview

PUERTO_KIOSKO = 8765


def _carpeta_codigo() -> Path:
    # Los .py son código: si está empaquetado, se leen de la carpeta
    # temporal donde PyInstaller los descomprime (sys._MEIPASS) -- a
    # diferencia de la base de datos (ver database.py), no importa que
    # esa carpeta sea temporal porque aquí no se guarda nada, solo se
    # leen los scripts.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def _ruta_app() -> str:
    return str(_carpeta_codigo() / "app.py")


def _ruta_kiosko() -> str:
    return str(_carpeta_codigo() / "kiosko_servidor.py")


def _en_modo_kiosko_servidor() -> bool:
    return "--kiosko-servidor" in sys.argv


def _comando_reinvocacion_kiosko() -> list:
    """Comando para volver a lanzar este mismo programa, pero en modo
    servidor de kiosko (ver _en_modo_kiosko_servidor). Empaquetado, el
    propio .exe entiende la bandera; en desarrollo hay que pasarle también
    la ruta de escritorio.py al intérprete de Python."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--kiosko-servidor"]
    return [sys.executable, __file__, "--kiosko-servidor"]


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


def _iniciar_streamlit_kiosko():
    """Corre el servidor de kiosko de asistencia, escuchando en la red
    local (0.0.0.0) en un puerto fijo. Bloqueante -- se usa como el
    programa completo del proceso hijo (ver main / --kiosko-servidor),
    no en un hilo de fondo."""
    from streamlit.web import bootstrap, cli as stcli

    bootstrap._set_up_signal_handler = lambda server: None

    sys.argv = [
        "streamlit", "run", _ruta_kiosko(),
        "--server.port", str(PUERTO_KIOSKO),
        "--server.address", "0.0.0.0",
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
    if _en_modo_kiosko_servidor():
        # Proceso hijo: solo corre el servidor de kiosko en red, sin ventana.
        _iniciar_streamlit_kiosko()
        return

    puerto = _puerto_libre()

    hilo_servidor = threading.Thread(target=_iniciar_streamlit, args=(puerto,), daemon=True)
    hilo_servidor.start()

    if not _esperar_servidor(puerto):
        raise RuntimeError("El servidor local no arrancó a tiempo.")

    proceso_kiosko = subprocess.Popen(_comando_reinvocacion_kiosko())
    try:
        webview.create_window(
            "Zully's Men's Club - Sistema Integral",
            f"http://127.0.0.1:{puerto}",
            width=1400, height=900, min_size=(1000, 700)
        )
        webview.start()
    finally:
        proceso_kiosko.terminate()


if __name__ == "__main__":
    main()
