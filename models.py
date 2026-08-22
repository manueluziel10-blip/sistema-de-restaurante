"""
Modelos SQLAlchemy + funciones de acceso a datos.

Estas funciones reemplazan el uso de st.session_state por lecturas/escrituras
reales en PostgreSQL, para que la información persista entre sesiones y
usuarios (útil en Streamlit Cloud, donde cada usuario tiene su propia
sesión en memoria y hoy se pierde todo al recargar).
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime,
    ForeignKey, func
)
from sqlalchemy.orm import declarative_base, relationship
import pandas as pd

from database import get_session

Base = declarative_base()


class PuestoCatalogo(Base):
    __tablename__ = "puestos_catalogo"
    nombre = Column(String, primary_key=True)
    sueldo_base = Column(Numeric(10, 2), nullable=False)
    es_comision = Column(Boolean, default=False)


class Empleado(Base):
    __tablename__ = "empleados"
    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True, nullable=False)
    tipo = Column(String, ForeignKey("puestos_catalogo.nombre"), nullable=False)
    sueldo_base = Column(Numeric(10, 2), nullable=False)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.now())


class CorteVenta(Base):
    __tablename__ = "cortes_ventas"
    id = Column(Integer, primary_key=True)
    fecha = Column(Date, server_default=func.current_date())
    idmesero = Column(Integer, ForeignKey("empleados.id"))
    importe = Column(Numeric(10, 2), default=0)
    efectivo = Column(Numeric(10, 2), default=0)
    tarjeta = Column(Numeric(10, 2), default=0)
    propina = Column(Numeric(10, 2), default=0)
    penalizado = Column(Boolean, default=False)
    archivo_origen = Column(String)
    cargado_en = Column(DateTime, server_default=func.now())


class ProductoChica(Base):
    __tablename__ = "cortes_productos_chicas"
    id = Column(Integer, primary_key=True)
    fecha = Column(Date, server_default=func.current_date())
    clave = Column(String)
    descripcion = Column(String, nullable=False)
    grupo = Column(String)
    precio = Column(Numeric(10, 2))
    cantidad = Column(Numeric(10, 2), default=1)
    empleado_nombre = Column(String, nullable=False)
    empleado_id = Column(Integer, ForeignKey("empleados.id"))
    comision_unitaria = Column(Numeric(10, 2), default=0)
    penalizada = Column(Boolean, default=False)
    archivo_origen = Column(String)
    cargado_en = Column(DateTime, server_default=func.now())


class GastoDiario(Base):
    __tablename__ = "gastos_diarios"
    id = Column(Integer, primary_key=True)
    fecha = Column(Date, unique=True, server_default=func.current_date())
    gasto_cocina = Column(Numeric(10, 2), default=0)
    gasto_compras = Column(Numeric(10, 2), default=0)
    gasto_vales = Column(Numeric(10, 2), default=0)
    nomina_personal_fijo = Column(Numeric(10, 2), default=4483.66)
    notas = Column(String)
    creado_en = Column(DateTime, server_default=func.now())


# ---------------------------------------------------------
# FUNCIONES DE ACCESO A DATOS (reemplazan session_state)
# ---------------------------------------------------------

def cargar_empleados_df() -> pd.DataFrame:
    """Equivalente a leer st.session_state.empleados"""
    session = get_session()
    query = session.query(Empleado)
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def agregar_empleado(nombre, tipo, sueldo_base):
    session = get_session()
    emp = Empleado(nombre=nombre.upper(), tipo=tipo, sueldo_base=sueldo_base)
    session.add(emp)
    session.commit()
    session.close()


def actualizar_empleado(nombre, nuevo_tipo, nuevo_sueldo):
    session = get_session()
    session.query(Empleado).filter(Empleado.nombre == nombre).update(
        {"tipo": nuevo_tipo, "sueldo_base": nuevo_sueldo}
    )
    session.commit()
    session.close()


def guardar_corte_ventas(df_v: pd.DataFrame, archivo_origen: str):
    """Limpia los registros del día actual e inserta el nuevo corte de ventas validando empleados."""
    session = get_session()
    try:
        # 1. Borrar los registros de la fecha actual antes de guardar los nuevos
        session.query(CorteVenta).filter(CorteVenta.fecha == func.current_date()).delete()
        session.commit()

        # 2. Insertar los nuevos registros del Excel
        for _, row in df_v.iterrows():
            idmesero = row.get("idmesero")
            nombre_mesero = str(row.get("nombre", f"MESERO {idmesero}"))

            # Verificar si el empleado existe, si no, crearlo con su ID o nombre
            emp = session.query(Empleado).filter(Empleado.id == idmesero).first()
            if not emp:
                # Si no existe por ID, intentamos buscarlo por nombre
                emp = session.query(Empleado).filter(Empleado.nombre == nombre_mesero.upper()).first()
            
            if not emp:
                # Si de plano no existe, lo creamos asignándole su ID del Excel
                emp = Empleado(
                    id=idmesero,
                    nombre=nombre_mesero.upper(),
                    tipo="Mesero",  # O el tipo de puesto correspondiente en tu catálogo
                    sueldo_base=300.0
                )
                session.add(emp)
                session.commit()

            session.add(CorteVenta(
                idmesero=emp.id,
                importe=row.get("importe", 0),
                efectivo=row.get("efectivo", 0),
                tarjeta=row.get("tarjeta", 0),
                propina=row.get("propina", 0),
                archivo_origen=archivo_origen,
            ))
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def guardar_corte_chicas(filas_chicas: pd.DataFrame, calcular_comision_fn, archivo_origen: str):
    """
    Limpia los registros del día actual de productos de chicas e inserta los nuevos (sobrescribe).
    """
    session = get_session()
    try:
        # 1. Borrar los registros de la fecha actual antes de guardar
        session.query(ProductoChica).filter(ProductoChica.fecha == func.current_date()).delete()
        session.commit()

        nuevas_detectadas = []
        for _, row in filas_chicas.iterrows():
            desc = str(row["DESCRIPCION"])
            prod_parte, chica_parte = desc.split(">")
            nombre_persona = chica_parte.strip().upper()
            comision_unit = calcular_comision_fn(prod_parte)
            cantidad = float(row["CANTIDAD"]) if pd.notna(row.get("CANTIDAD")) else 1.0

            empleado_id, creado = obtener_o_crear_empleado(nombre_persona)
            if creado:
                nuevas_detectadas.append(nombre_persona)

            session.add(ProductoChica(
                clave=row.get("CLAVE"),
                descripcion=desc,
                grupo=row.get("GRUPO"),
                precio=row.get("PRECIO"),
                cantidad=cantidad,
                empleado_nombre=nombre_persona,
                empleado_id=empleado_id,
                comision_unitaria=comision_unit,
                archivo_origen=archivo_origen,
            ))
        session.commit()
        return nuevas_detectadas
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales, nomina_personal_fijo=4483.66):
    session = get_session()
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == func.current_date()).first()
    if hoy:
        hoy.gasto_cocina = gasto_cocina
        hoy.gasto_compras = gasto_compras
        hoy.gasto_vales = gasto_vales
    else:
        session.add(GastoDiario(
            gasto_cocina=gasto_cocina,
            gasto_compras=gasto_compras,
            gasto_vales=gasto_vales,
            nomina_personal_fijo=nomina_personal_fijo,
        ))
    session.commit()
    session.close()


def cargar_ventas_df() -> pd.DataFrame:
    """Todas las ventas de meseros acumuladas (reemplaza historial_ventas)"""
    session = get_session()
    df = pd.read_sql(session.query(CorteVenta).statement, session.bind)
    session.close()
    return df


def cargar_chicas_df() -> pd.DataFrame:
    """Todos los productos de chicas/bailarinas acumulados (reemplaza historial_chicas)"""
    session = get_session()
    df = pd.read_sql(session.query(ProductoChica).statement, session.bind)
    session.close()
    return df


def cargar_gastos_hoy():
    session = get_session()
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == func.current_date()).first()
    session.close()
    return hoy


def obtener_o_crear_empleado(nombre: str, tipo: str = "Chicas / Bailarinas (Comisiones)", sueldo_base: float = 300.0):
    """Devuelve el id del empleado si existe; si no, lo crea (usado al detectar nombres nuevos en un corte)."""
    session = get_session()
    emp = session.query(Empleado).filter(Empleado.nombre == nombre.upper()).first()
    creado = False
    if not emp:
        emp = Empleado(nombre=nombre.upper(), tipo=tipo, sueldo_base=sueldo_base)
        session.add(emp)
        session.commit()
        session.refresh(emp)
        creado = True
    emp_id = emp.id
    session.close()
    return emp_id, creado
