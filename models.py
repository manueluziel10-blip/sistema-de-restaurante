from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime,
    ForeignKey, func, inspect, text as db_text
)
from sqlalchemy.orm import declarative_base
import pandas as pd
from datetime import datetime
from database import get_session

Base = declarative_base()

class DiaBloqueado(Base):
    __tablename__ = "dias_bloqueados"
    fecha = Column(Date, primary_key=True)
    bloqueado = Column(Boolean, default=True)
    bloqueado_en = Column(DateTime, server_default=func.now())

class PuestoCatalogo(Base):
    __tablename__ = "puestos_catalogo"
    nombre = Column(String, primary_key=True)
    sueldo_base = Column(Numeric(10, 2), nullable=False)
    es_comision = Column(Boolean, default=False)

class Empleado(Base):
    __tablename__ = "empleados"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String, unique=True, nullable=False)
    tipo = Column(String, ForeignKey("puestos_catalogo.nombre"), nullable=False)
    sueldo_base = Column(Numeric(10, 2), nullable=False)
    vales_nomina = Column(Numeric(10, 2), default=0.0)
    descuento_nomina = Column(Numeric(10, 2), default=100.0)
    transferencia_nomina = Column(Numeric(10, 2), default=0.0)
    penalizada = Column(Boolean, default=False)
    activo = Column(Boolean, default=True)

class CorteVenta(Base):
    __tablename__ = "cortes_ventas"
    id = Column(Integer, primary_key=True)
    fecha = Column(Date, server_default=func.current_date())
    idmesero = Column(Integer, ForeignKey("empleados.id"))
    importe = Column(Numeric(10, 2), default=0)
    efectivo = Column(Numeric(10, 2), default=0)
    propina_efectivo = Column(Numeric(10, 2), default=0)
    tarjeta = Column(Numeric(10, 2), default=0)
    propina_tarjeta = Column(Numeric(10, 2), default=0)
    vales = Column(Numeric(10, 2), default=0)
    propina_vales = Column(Numeric(10, 2), default=0)
    otros = Column(Numeric(10, 2), default=0)
    archivo_origen = Column(String)

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
    archivo_origen = Column(String)

class GastoDiario(Base):
    __tablename__ = "gastos_diarios"
    id = Column(Integer, primary_key=True)
    fecha = Column(Date, unique=True, server_default=func.current_date())
    gasto_cocina = Column(Numeric(10, 2), default=0)
    gasto_compras = Column(Numeric(10, 2), default=0)
    gasto_vales = Column(Numeric(10, 2), default=0)

# --- FUNCIONES DE BLOQUEO ---
def verificar_dia_bloqueado(fecha_str: str) -> bool:
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        registro = session.query(DiaBloqueado).filter(DiaBloqueado.fecha == f_date).first()
        return registro.bloqueado if registro else False
    except Exception:
        return False
    finally:
        session.close()

def bloquear_dia_db(fecha_str: str):
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        registro = session.query(DiaBloqueado).filter(DiaBloqueado.fecha == f_date).first()
        if registro:
            registro.bloqueado = True
        else:
            session.add(DiaBloqueado(fecha=f_date, bloqueado=True))
        session.commit()
    finally:
        session.close()

def desbloquear_dia_db(fecha_str: str):
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        session.query(DiaBloqueado).filter(DiaBloqueado.fecha == f_date).update({"bloqueado": False})
        session.commit()
    finally:
        session.close()

def cargar_empleados_df() -> pd.DataFrame:
    session = get_session()
    query = session.query(Empleado).order_by(Empleado.id)
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df

def agregar_empleado(nombre, tipo, sueldo_base):
    session = get_session()
    emp = session.query(Empleado).filter(Empleado.nombre == nombre.upper()).first()
    if emp:
        emp.tipo = tipo; emp.sueldo_base = sueldo_base
    else:
        session.add(Empleado(nombre=nombre.upper(), tipo=tipo, sueldo_base=sueldo_base))
    session.commit(); session.close()

def actualizar_empleado(emp_id, nuevo_tipo, nuevo_sueldo, nuevo_vales=None, nueva_penalizacion=None, nuevo_descuento=None, nueva_transferencia=None):
    session = get_session()
    datos = {"tipo": nuevo_tipo, "sueldo_base": nuevo_sueldo}
    if nuevo_vales is not None: datos["vales_nomina"] = nuevo_vales
    if nueva_penalizacion is not None: datos["penalizada"] = nueva_penalizacion
    if nuevo_descuento is not None: datos["descuento_nomina"] = nuevo_descuento
    if nueva_transferencia is not None: datos["transferencia_nomina"] = nueva_transferencia
    session.query(Empleado).filter(Empleado.id == emp_id).update(datos)
    session.commit(); session.close()

def guardar_corte_ventas(df_v, df_p, archivo_origen, fecha_corte=None):
    session = get_session()
    f_date = datetime.strptime(fecha_corte, "%Y-%m-%d").date() if fecha_corte else datetime.now().date()
    session.query(CorteVenta).filter(CorteVenta.fecha == f_date).delete()
    session.commit()
    df_completo = pd.merge(df_v, df_p, on='idmesero', how='left', suffixes=('_v', '_p')).fillna(0)
    for _, row in df_completo.iterrows():
        nombre_mesero = str(row.get("nombre_v", row.get("nombre_p", "MESERO"))).strip().upper()
        emp = session.query(Empleado).filter(Empleado.nombre == nombre_mesero).first()
        if not emp:
            emp = Empleado(nombre=nombre_mesero, tipo="Mesero (Comisiones)", sueldo_base=300.0)
            session.add(emp); session.commit(); session.refresh(emp)
        session.add(CorteVenta(
            fecha=f_date, idmesero=emp.id,
            importe=row.get("importe_x", row.get("importe", 0)),
            efectivo=row.get("efectivo", 0), propina_efectivo=row.get("propinaefectivo", 0),
            tarjeta=row.get("tarjeta", 0), propina_tarjeta=row.get("propinatarjeta", 0),
            vales=row.get("vales", 0), propina_vales=row.get("propinavales", 0),
            otros=row.get("otros", 0), archivo_origen=archivo_origen
        ))
    session.commit(); session.close()

def guardar_corte_chicas(filas_chicas, calcular_comision_fn, archivo_origen, fecha_corte=None):
    session = get_session()
    f_date = datetime.strptime(fecha_corte, "%Y-%m-%d").date() if fecha_corte else datetime.now().date()
    session.query(ProductoChica).filter(ProductoChica.fecha == f_date).delete()
    session.commit()
    nuevas = []
    for _, row in filas_chicas.iterrows():
        desc = str(row["DESCRIPCION"])
        nombre_persona = desc.split(">", 1)[1].strip().upper() if ">" in desc else "GENERAL"
        comision_unit = calcular_comision_fn(desc.split(">", 1)[0] if ">" in desc else desc)
        emp = session.query(Empleado).filter(Empleado.nombre == nombre_persona).first()
        if not emp:
            emp = Empleado(nombre=nombre_persona, tipo="Chicas / Bailarinas (Comisiones)", sueldo_base=300.0)
            session.add(emp); session.commit(); session.refresh(emp); nuevas.append(nombre_persona)
        session.add(ProductoChica(
            fecha=f_date, clave=row.get("CLAVE"), descripcion=desc, grupo=row.get("GRUPO"),
            precio=row.get("PRECIO"), cantidad=float(row.get("CANTIDAD", 1)),
            empleado_nombre=nombre_persona, empleado_id=emp.id,
            comision_unitaria=comision_unit, archivo_origen=archivo_origen
        ))
    session.commit(); session.close()
    return nuevas

def guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales, fecha_corte=None):
    session = get_session()
    f_date = datetime.strptime(fecha_corte, "%Y-%m-%d").date() if fecha_corte else datetime.now().date()
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == f_date).first()
    if hoy:
        hoy.gasto_cocina = gasto_cocina; hoy.gasto_compras = gasto_compras; hoy.gasto_vales = gasto_vales
    else:
        session.add(GastoDiario(fecha=f_date, gasto_cocina=gasto_cocina, gasto_compras=gasto_compras, gasto_vales=gasto_vales))
    session.commit(); session.close()

def obtener_fechas_disponibles() -> list:
    session = get_session()
    try:
        f = session.query(CorteVenta.fecha).distinct().all() + session.query(ProductoChica.fecha).distinct().all()
        todas = set([x[0] for x in f if x[0] is not None])
        return [dt.strftime('%Y-%m-%d') for dt in sorted(list(todas), reverse=True)]
    finally:
        session.close()

def cargar_ventas_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else datetime.now().date()
    df = pd.read_sql(session.query(CorteVenta).filter(CorteVenta.fecha == f_date).statement, session.bind)
    session.close(); return df

def cargar_chicas_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else datetime.now().date()
    df = pd.read_sql(session.query(ProductoChica).filter(ProductoChica.fecha == f_date).statement, session.bind)
    session.close(); return df

def cargar_gastos_hoy(fecha_str: str = None):
    session = get_session()
    f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else datetime.now().date()
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == f_date).first()
    session.close(); return hoy

def reiniciar_base_de_datos():
    session = get_session()
    try:
        Base.metadata.drop_all(session.bind)
        Base.metadata.create_all(session.bind)
        session.add_all([
            PuestoCatalogo(nombre="Chicas / Bailarinas (Comisiones)", sueldo_base=300.0, es_comision=True),
            PuestoCatalogo(nombre="Mesero (Comisiones)", sueldo_base=300.0, es_comision=True),
            PuestoCatalogo(nombre="Barman (Fijo)", sueldo_base=400.0, es_comision=False),
            PuestoCatalogo(nombre="Seguridad (Fijo)", sueldo_base=500.0, es_comision=False),
            PuestoCatalogo(nombre="DJ (Fijo)", sueldo_base=600.0, es_comision=False),
            PuestoCatalogo(nombre="Animador (Fijo)", sueldo_base=400.0, es_comision=False),
            PuestoCatalogo(nombre="Gerente (Fijo)", sueldo_base=500.0, es_comision=False),
            PuestoCatalogo(nombre="Capitán de Mesero (Fijo)", sueldo_base=400.0, es_comision=False),
            PuestoCatalogo(nombre="Ayudante de Mesero (Fijo)", sueldo_base=300.0, es_comision=False),
            PuestoCatalogo(nombre="Cajero (Fijo)", sueldo_base=400.0, es_comision=False),
        ])
        session.commit()
    finally:
        session.close()