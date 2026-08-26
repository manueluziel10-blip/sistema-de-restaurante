"""
Conexión a la base de datos PostgreSQL (Neon).

En Streamlit Cloud, ve a: Settings -> Secrets, y agrega la cadena de
conexión completa que Neon te dio (botón "Mostrar contraseña" en la
consola de Neon), así:

database_url = "postgresql://neondb_owner:TU_PASSWORD@ep-broad-voice-axovmpvo.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

Para probar en tu computadora, crea un archivo .streamlit/secrets.toml
en la raíz de tu proyecto con esa misma línea.
"""

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

@st.cache_resource
def get_engine():
    try:
        url = st.secrets["database_url"]
    except (KeyError, FileNotFoundError):
        # Permite ejecutar la aplicación localmente sin exponer credenciales.
        url = f"sqlite:///{Path(__file__).with_name('restaurante_local.db')}"

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)

def get_session():
    Session = sessionmaker(bind=get_engine())
    return Session()
