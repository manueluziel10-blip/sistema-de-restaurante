"""
Conexión a la base de datos PostgreSQL (Neon).

En Streamlit Cloud, ve a: Settings -> Secrets, y agrega la cadena de
conexión completa que Neon te dio (botón "Mostrar contraseña" en la
consola de Neon), así:

database_url = "postgresql://neondb_owner:TU_PASSWORD@ep-broad-voice-axovmpvo.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

Para probar en tu computadora, crea un archivo .streamlit/secrets.toml
en la raíz de tu proyecto con esa misma línea.
"""

import sys
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

def _carpeta_base_local() -> Path:
    """Carpeta donde vive (o debe vivir) restaurante_local.db.

    Si el programa corre empaquetado (PyInstaller), sys.executable apunta
    al .exe; usar __file__ ahí apuntaría a la carpeta temporal donde
    PyInstaller descomprime el programa en cada arranque, borrando la
    base de datos local cada vez que se abre. Por eso, empaquetado usa la
    carpeta del .exe; en desarrollo (código fuente) usa la carpeta del
    propio archivo, como antes.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

@st.cache_resource
def get_engine():
    try:
        url = st.secrets["database_url"]
    except (KeyError, FileNotFoundError):
        # Permite ejecutar la aplicación localmente sin exponer credenciales.
        url = f"sqlite:///{_carpeta_base_local() / 'restaurante_local.db'}"

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)

def get_session():
    Session = sessionmaker(bind=get_engine())
    return Session()
