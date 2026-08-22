"""
Modelos SQLAlchemy + funciones de acceso a datos.
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
    propina_efectivo = Column(Numeric(10, 2), default=0)
    tarjeta = Column(Numeric(10, 2), default=0)
    propina_tarjeta = Column(Numeric(10, 2), default=0)
    vales = Column(Numeric(10, 2), default=0)
    propina_vales = Column(Numeric(10, 2), default=0)
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
# FUNCIONES DE AUXILIO PARA CATÁLOGOS
# ---------------------------------------------------------
def asegurar_puesto_existe(session, nombre_puesto: str, sueldo_base: float = 300.0, es_comision: bool = True):
    """Garantiza que el puesto exista en el catálogo para evitar errores de FK."""
    puesto = session.query(PuestoCatalogo).filter(PuestoCatalogo.nombre == nombre_puesto).first()
    if not puesto:
        puesto = PuestoCatalogo(nombre=nombre_puesto, sueldo_base=sueldo_base, es_comision=es_comision)
        session.add(puesto)
        session.commit()


# ---------------------------------------------------------
# FUNCIONES DE ACCESO A DATOS
# ---------------------------------------------------------

def cargar_empleados_df() -> pd.DataFrame:
    session = get_session()
    query = session.query(Empleado)
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def agregar_empleado(nombre, tipo, sueldo_base):
    session = get_session()
    asegurar_puesto_existe(session, tipo)
    emp = Empleado(nombre=nombre.upper(), tipo=tipo, sueldo_base=sueldo_base)
    session.add(emp)
    session.commit()
    session.close()


def actualizar_empleado(nombre, nuevo_tipo, nuevo_sueldo):
    session = get_session()
    asegurar_puesto_existe(session, nuevo_tipo)
    session.query(Empleado).filter(Empleado.nombre == nombre).update(
        {"tipo": nuevo_tipo, "sueldo_base": nuevo_sueldo}
    )
    session.commit()
    session.close()


def guardar_corte_ventas(df_v: pd.DataFrame, df_propinas: pd.DataFrame, archivo_origen: str):
    session = get_session()
    try:
        session.query(CorteVenta).filter(CorteVenta.fecha == func.current_date()).delete()
        session.commit()

        tipo_por_defecto = "Mesero (Comisiones)"
        asegurar_puesto_existe(session, tipo_por_defecto)

        df_completo = pd.merge(df_v, df_propinas, on='idmesero', how='left', suffixes=('_v', '_p'))
        df_completo = df_completo.fillna(0)

        for _, row in df_completo.iterrows():
            idmesero = row.get("idmesero")
            nombre_mesero = str(row.get("nombre_v", row.get("nombre_p", f"MESERO {idmesero}")))

            emp = session.query(Empleado).filter(Empleado.id == idmesero).first()
            if not emp:
                emp = session.query(Empleado).filter(Empleado.nombre == nombre_mesero.upper()).first()
            
            if not emp:
                emp = Empleado(
                    id=idmesero,
                    nombre=nombre_mesero.upper(),
                    tipo=tipo_por_defecto,
                    sueldo_base=300.0
                )
                session.add(emp)
                session.commit()
            else:
                if "CHICA" in emp.tipo.upper() or "BAILARINA" in emp.tipo.upper():
                    emp.tipo = tipo_por_defecto
                    session.commit()

            session.add(CorteVenta(
                idmesero=emp.id,
                importe=row.get("importe_x", row.get("importe", 0)),
                efectivo=row.get("efectivo", 0),
                propina_efectivo=row.get("propinaefectivo", 0),
                tarjeta=row.get("tarjeta", 0),
                propina_tarjeta=row.get("propinatarjeta", 0),
                vales=row.get("vales", 0),
                propina_vales=row.get("propinavales", 0),
                archivo_origen=archivo_origen,
            ))
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def guardar_corte_chicas(filas_chicas: pd.DataFrame, calcular_comision_fn, archivo_origen: str):
    session = get_session()
    try:
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
    """Ventas de meseros del día actual"""
    session = get_session()
    query = session.query(CorteVenta).filter(CorteVenta.fecha == func.current_date())
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def cargar_chicas_df() -> pd.DataFrame:
    """Productos de chicas del día actual"""
    session = get_session()
    query = session.query(ProductoChica).filter(ProductoChica.fecha == func.current_date())
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def cargar_gastos_hoy():
    session = get_session()
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == func.current_date()).first()
    session.close()
    return hoy


def obtener_o_crear_empleado(nombre: str, tipo: str = "Chicas / Bailarinas (Comisiones)", sueldo_base: float = 300.0):
    session = get_session()
    asegurar_puesto_existe(session, tipo, sueldo_base, es_comision=True)
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


def reiniciar_base_de_datos():
    """Elimina, recrea tablas y puebla el catálogo inicial de puestos."""
    session = get_session()
    try:
        Base.metadata.drop_all(session.bind)
        Base.metadata.create_all(session.bind)
        
        puestos_iniciales = [
            PuestoCatalogo(nombre="Chicas / Bailarinas (Comisiones)", sueldo_base=300.0, es_comision=True),
            PuestoCatalogo(nombre="Mesero (Comisiones)", sueldo_base=300.0, es_comision=True),
            PuestoCatalogo(nombre="Seguridad (Fijo)", sueldo_base=500.0, es_comision=False),
            PuestoCatalogo(nombre="DJ (Fijo)", sueldo_base=600.0, es_comision=False),
            PuestoCatalogo(nombre="Animador (Fijo)", sueldo_base=400.0, es_comision=False),
            PuestoCatalogo(nombre="Gerente (Fijo)", sueldo_base=500.0, es_comision=False),
            PuestoCatalogo(nombre="Capitán de Mesero (Fijo)", sueldo_base=400.0, es_comision=False),
            PuestoCatalogo(nombre="Ayudante de Mesero (Fijo)", sueldo_base=300.0, es_comision=False),
        ]
        session.add_all(puestos_iniciales)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()