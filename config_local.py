"""
Configuración local de la app de escritorio (impresora principal para los
tickets de 80mm). Solo tiene efecto real cuando corre como app de
escritorio (requiere pywin32, que no se instala en la versión web/nube) —
en la web, las funciones de impresión simplemente se reportan como no
disponibles.

La preferencia se guarda en un archivo JSON junto al ejecutable (o junto
al código fuente en desarrollo), igual que la base de datos local, para
que sobreviva entre aperturas del programa.
"""

import json
import sys
from pathlib import Path

try:
    import win32print
    import win32api
    IMPRESION_DISPONIBLE = True
except ImportError:
    IMPRESION_DISPONIBLE = False


def _carpeta_base_local() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _ruta_config() -> Path:
    return _carpeta_base_local() / "config_local.json"


def _leer_config() -> dict:
    ruta = _ruta_config()
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _guardar_config(datos: dict):
    _ruta_config().write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def listar_impresoras() -> list:
    """Nombres de las impresoras instaladas en Windows. Lista vacía si no
    está disponible (versión web, o no-Windows)."""
    if not IMPRESION_DISPONIBLE:
        return []
    impresoras = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
    return [p[2] for p in impresoras]


def obtener_impresora_principal() -> str | None:
    """La impresora elegida por el usuario, o la impresora predeterminada
    de Windows si nunca se eligió una."""
    guardada = _leer_config().get("impresora_principal")
    if guardada:
        return guardada
    if IMPRESION_DISPONIBLE:
        try:
            return win32print.GetDefaultPrinter()
        except Exception:
            return None
    return None


def guardar_impresora_principal(nombre_impresora: str):
    config = _leer_config()
    config["impresora_principal"] = nombre_impresora
    _guardar_config(config)


def imprimir_pdf_bytes(pdf_bytes: bytes, nombre_impresora: str, nombre_archivo: str = "ticket.pdf") -> bool:
    """Envía un PDF (en memoria) directo a una impresora de Windows, sin
    abrir ningún diálogo, usando el visor de PDF predeterminado del sistema
    (verbo "printto" de ShellExecute). Devuelve True si se pudo lanzar la
    impresión. Requiere que exista un programa asociado a .pdf capaz de
    imprimir (Edge, Adobe Reader, etc. — normalmente ya viene con Windows)."""
    if not IMPRESION_DISPONIBLE or not nombre_impresora:
        return False

    carpeta_temp = _carpeta_base_local() / "tickets_temp"
    carpeta_temp.mkdir(exist_ok=True)
    ruta_pdf = carpeta_temp / nombre_archivo
    ruta_pdf.write_bytes(pdf_bytes)

    win32api.ShellExecute(0, "printto", str(ruta_pdf), f'"{nombre_impresora}"', ".", 0)
    return True
