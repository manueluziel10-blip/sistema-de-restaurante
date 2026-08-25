"""
Modelos SQLAlchemy + funciones de acceso a datos con soporte histórico completo por fecha, ID y empleado.
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime,
    ForeignKey, func, inspect, UniqueConstraint, text as db_text
)
from sqlalchemy.orm import declarative_base, relationship
import pandas as pd
from datetime import datetime

from database import get_session

Base = declarative_base()


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
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.now())


class NominaDiaria(Base):
    __tablename__ = "nomina_diaria"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    sueldo_base = Column(Numeric(10, 2), default=0.0)
    vales_nomina = Column(Numeric(10, 2), default=0.0)
    descuento_nomina = Column(Numeric(10, 2), default=100.0)
    transferencia_nomina = Column(Numeric(10, 2), default=0.0)
    penalizada = Column(Boolean, default=False)


class Asistencia(Base):
    __tablename__ = "asistencias"
    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    estado = Column(String(50), default="Presente")
    comentarios = Column(String, default="Automático por sistema")
    creado_en = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('empleado_id', 'fecha', name='unique_empleado_fecha'),
    )


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


class UsuarioSistema(Base):
    __tablename__ = "usuarios_sistema"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    rol = Column(String, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())


class CorteBloqueo(Base):
    __tablename__ = "cortes_bloqueos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, unique=True, nullable=False)
    bloqueado = Column(Boolean, default=True)
    bloqueado_por = Column(String)
    fecha_bloqueo = Column(DateTime, server_default=func.now())


# --- FUNCIONES DE AUTENTICACIÓN Y BLOQUEOS ---

def inicializar_usuarios_por_defecto():
    session = get_session()
    try:
        admin = session.query(UsuarioSistema).filter(UsuarioSistema.username == "admin").first()
        if not admin:
            session.add(UsuarioSistema(username="admin", password="123", rol="admin"))
        cajero = session.query(UsuarioSistema).filter(UsuarioSistema.username == "cajero").first()
        if not cajero:
            session.add(UsuarioSistema(username="cajero", password="123", rol="cajero"))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def validar_login(username, password):
    session = get_session()
    try:
        user = session.query(UsuarioSistema).filter(
            UsuarioSistema.username == username, 
            UsuarioSistema.password == password
        ).first()
        if user:
            return {"username": user.username, "rol": user.rol}
        return None
    finally:
        session.close()


def cargar_usuarios_df() -> pd.DataFrame:
    session = get_session()
    try:
        query = session.query(UsuarioSistema).order_by(UsuarioSistema.id)
        df = pd.read_sql(query.statement, session.bind)
        return df
    finally:
        session.close()


def crear_usuario(username, password, rol):
    session = get_session()
    try:
        existe = session.query(UsuarioSistema).filter(UsuarioSistema.username == username).first()
        if not existe:
            nuevo = UsuarioSistema(username=username, password=password, rol=rol)
            session.add(nuevo)
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def actualizar_credenciales(usuario_id, nuevo_username, nueva_password, nuevo_rol):
    session = get_session()
    try:
        user = session.query(UsuarioSistema).filter(UsuarioSistema.id == usuario_id).first()
        if user:
            user.username = nuevo_username
            if nueva_password and nueva_password.strip():
                user.password = nueva_password
            user.rol = nuevo_rol
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def verificar_corte_bloqueado(fecha_str: str) -> bool:
    session = get_session()
    try:
        f_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        bloqueo = session.query(CorteBloqueo).filter(CorteBloqueo.fecha == f_obj, CorteBloqueo.bloqueado == True).first()
        return bloqueo is not None
    except Exception:
        return False
    finally:
        session.close()


def bloquear_corte_fecha(fecha_str: str, usuario: str):
    session = get_session()
    try:
        f_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        bloqueo = session.query(CorteBloqueo).filter(CorteBloqueo.fecha == f_obj).first()
        if bloqueo:
            bloqueo.bloqueado = True
            bloqueo.bloqueado_por = usuario
        else:
            nuevo_b = CorteBloqueo(fecha=f_obj, bloqueado=True, bloqueado_por=usuario)
            session.add(nuevo_b)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def desbloquear_corte_fecha(fecha_str: str):
    session = get_session()
    try:
        f_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        session.query(CorteBloqueo).filter(CorteBloqueo.fecha == f_obj).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def cambiar_fecha_corte(fecha_antigua_str: str, fecha_nueva_str: str):
    session = get_session()
    try:
        f_ant = datetime.strptime(fecha_antigua_str, "%Y-%m-%d").date()
        f_nue = datetime.strptime(fecha_nueva_str, "%Y-%m-%d").date()
        
        if f_ant == f_nue:
            return

        bloqueo_destino = session.query(CorteBloqueo).filter(CorteBloqueo.fecha == f_nue).first()
        if bloqueo_destino:
            session.delete(bloqueo_destino)
            
        gasto_destino = session.query(GastoDiario).filter(GastoDiario.fecha == f_nue).first()
        if gasto_destino:
            session.delete(gasto_destino)
            
        session.commit()

        session.query(CorteVenta).filter(CorteVenta.fecha == f_ant).update({CorteVenta.fecha: f_nue}, synchronize_session=False)
        session.query(ProductoChica).filter(ProductoChica.fecha == f_ant).update({ProductoChica.fecha: f_nue}, synchronize_session=False)
        session.query(NominaDiaria).filter(NominaDiaria.fecha == f_ant).update({NominaDiaria.fecha: f_nue}, synchronize_session=False)
        session.query(GastoDiario).filter(GastoDiario.fecha == f_ant).update({GastoDiario.fecha: f_nue}, synchronize_session=False)
        session.query(CorteBloqueo).filter(CorteBloqueo.fecha == f_ant).update({CorteBloqueo.fecha: f_nue}, synchronize_session=False)
        
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


# --- FUNCIONES GENERALES DE NEGOCIO Y NÓMINA HISTÓRICA ---

def asegurar_puesto_existe(session, nombre_puesto: str, sueldo_base: float = 300.0, es_comision: bool = True):
    puesto = session.query(PuestoCatalogo).filter(PuestoCatalogo.nombre == nombre_puesto).first()
    if not puesto:
        puesto = PuestoCatalogo(nombre=nombre_puesto, sueldo_base=sueldo_base, es_comision=es_comision)
        session.add(puesto)
        session.commit()


def asegurar_nomina_dia(session, fecha_date):
    """Verifica que la tabla tenga las columnas correctas."""
    try:
        inspector = inspect(session.bind)
        if 'nomina_diaria' in inspector.get_table_names():
            columnas_tabla = [col['name'] for col in inspector.get_columns('nomina_diaria')]
            if 'sueldo_base' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN sueldo_base NUMERIC(10,2) DEFAULT 0.0"))
            if 'vales_nomina' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN vales_nomina NUMERIC(10,2) DEFAULT 0.0"))
            if 'descuento_nomina' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN descuento_nomina NUMERIC(10,2) DEFAULT 100.0"))
            if 'transferencia_nomina' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN transferencia_nomina NUMERIC(10,2) DEFAULT 0.0"))
            if 'penalizada' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN penalizada BOOLEAN DEFAULT 0"))
            session.commit()
    except Exception:
        session.rollback()


def cargar_empleados_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
    
    asegurar_nomina_dia(session, f_date)
    
    query = session.query(
        Empleado.id,
        Empleado.nombre,
        Empleado.tipo,
        NominaDiaria.sueldo_base,
        NominaDiaria.vales_nomina,
        NominaDiaria.descuento_nomina,
        NominaDiaria.transferencia_nomina,
        NominaDiaria.penalizada
    ).join(NominaDiaria, Empleado.id == NominaDiaria.empleado_id).filter(
        NominaDiaria.fecha == f_date,
        Empleado.activo == True
    ).order_by(Empleado.id)
    
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    
    if not df.empty:
        df['sueldo_base'] = df['sueldo_base'].astype(float)
        df['vales_nomina'] = df['vales_nomina'].astype(float) if 'vales_nomina' in df.columns else 0.0
        df['descuento_nomina'] = df['descuento_nomina'].astype(float) if 'descuento_nomina' in df.columns else 100.0
        df['transferencia_nomina'] = df['transferencia_nomina'].astype(float) if 'transferencia_nomina' in df.columns else 0.0
        df['penalizada'] = df['penalizada'].astype(bool) if 'penalizada' in df.columns else False
    return df


def agregar_empleado(nombre, tipo, sueldo_base, fecha_str=None, **kwargs):
    session = get_session()
    asegurar_puesto_existe(session, tipo)
    emp = session.query(Empleado).filter(Empleado.nombre == nombre.upper()).first()
    if emp:
        emp.tipo = tipo
        emp.sueldo_base = sueldo_base
    else:
        emp = Empleado(
            nombre=nombre.upper(),
            tipo=tipo,
            sueldo_base=sueldo_base
        )
        session.add(emp)
        session.commit()
        session.refresh(emp)
    
    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()

    existe_nom = session.query(NominaDiaria).filter(
        NominaDiaria.fecha == f_date,
        NominaDiaria.empleado_id == emp.id
    ).first()

    if not existe_nom:
        session.add(NominaDiaria(
            fecha=f_date,
            empleado_id=emp.id,
            sueldo_base=sueldo_base,
            vales_nomina=0.0,
            descuento_nomina=100.0,
            transferencia_nomina=0.0,
            penalizada=False
        ))
    else:
        existe_nom.sueldo_base = sueldo_base

    session.commit()
    session.close()


def actualizar_empleado(emp_id, nuevo_tipo, nuevo_sueldo, nuevo_vales=None, nueva_penalizacion=None, nuevo_descuento=None, nueva_transferencia=None, fecha_str=None, **kwargs):
    session = get_session()
    asegurar_puesto_existe(session, nuevo_tipo)
    
    emp = session.query(Empleado).filter(Empleado.id == emp_id).first()
    if emp:
        emp.tipo = nuevo_tipo

    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()

    nom = session.query(NominaDiaria).filter(
        NominaDiaria.fecha == f_date,
        NominaDiaria.empleado_id == emp_id
    ).first()

    if not nom:
        nom = NominaDiaria(fecha=f_date, empleado_id=emp_id, sueldo_base=nuevo_sueldo)
        session.add(nom)

    nom.sueldo_base = nuevo_sueldo
    if nuevo_vales is not None:
        nom.vales_nomina = nuevo_vales
    if nueva_penalizacion is not None:
        nom.penalizada = nueva_penalizacion
    if nuevo_descuento is not None:
        nom.descuento_nomina = nuevo_descuento
    if nueva_transferencia is not None:
        nom.transferencia_nomina = nueva_transferencia

    session.commit()
    session.close()


def obtener_o_crear_empleado(nombre: str, tipo: str = "Chicas / Bailarinas (Comisiones)", sueldo_base: float = 300.0, fecha_date=None, existing_session=None):
    session = existing_session if existing_session else get_session()
    try:
        asegurar_puesto_existe(session, tipo, sueldo_base, es_comision=True)
        emp = session.query(Empleado).filter(Empleado.nombre == nombre.upper()).first()
        creado = False
        if not emp:
            emp = Empleado(
                nombre=nombre.upper(),
                tipo=tipo,
                sueldo_base=sueldo_base
            )
            session.add(emp)
            session.commit()
            session.refresh(emp)
            creado = True

        f_date = fecha_date if fecha_date else datetime.now().date()
        nom = session.query(NominaDiaria).filter(
            NominaDiaria.fecha == f_date,
            NominaDiaria.empleado_id == emp.id
        ).first()
        if not nom:
            session.add(NominaDiaria(
                fecha=f_date,
                empleado_id=emp.id,
                sueldo_base=sueldo_base,
                vales_nomina=0.0,
                descuento_nomina=100.0,
                transferencia_nomina=0.0,
                penalizada=False
            ))
            session.commit()

        return emp.id, creado
    finally:
        if not existing_session:
            session.close()


def guardar_corte_ventas(df_v: pd.DataFrame, df_propinas: pd.DataFrame, archivo_origen: str, fecha_corte=None, usuario_nombre="sistema"):
    session = get_session()
    try:
        f_filtro_str = fecha_corte if fecha_corte else datetime.now().strftime('%Y-%m-%d')
        f_filtro_date = datetime.strptime(f_filtro_str, "%Y-%m-%d").date()
        
        session.query(CorteVenta).filter(CorteVenta.fecha == f_filtro_date).delete()
        session.commit()

        tipo_por_defecto = "Mesero (Comisiones)"
        asegurar_puesto_existe(session, tipo_por_defecto)

        df_completo = pd.merge(df_v, df_propinas, on='idmesero', how='left', suffixes=('_v', '_p'))
        df_completo = df_completo.fillna(0)

        for _, row in df_completo.iterrows():
            nombre_mesero = str(row.get("nombre_v", row.get("nombre_p", "MESERO"))).strip().upper()
            emp_id, _ = obtener_o_crear_empleado(nombre_mesero, tipo_por_defecto, 300.0, fecha_date=f_filtro_date, existing_session=session)

            kwargs = {
                "fecha": f_filtro_date,
                "idmesero": emp_id,
                "importe": row.get("importe_x", row.get("importe", 0)),
                "efectivo": row.get("efectivo", 0),
                "propina_efectivo": row.get("propinaefectivo", 0),
                "tarjeta": row.get("tarjeta", 0),
                "propina_tarjeta": row.get("propinatarjeta", 0),
                "vales": row.get("vales", 0),
                "propina_vales": row.get("propinavales", 0),
                "otros": row.get("otros", 0),
                "archivo_origen": archivo_origen,
            }

            session.add(CorteVenta(**kwargs))
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def guardar_corte_chicas(filas_chicas: pd.DataFrame, calcular_comision_fn, archivo_origen: str, fecha_corte=None, usuario_nombre="sistema"):
    session = get_session()
    try:
        f_filtro_str = fecha_corte if fecha_corte else datetime.now().strftime('%Y-%m-%d')
        f_filtro_date = datetime.strptime(f_filtro_str, "%Y-%m-%d").date()
        
        session.query(ProductoChica).filter(ProductoChica.fecha == f_filtro_date).delete()
        session.commit()

        nuevas_detectadas = []
        for _, row in filas_chicas.iterrows():
            desc = str(row["DESCRIPCION"])
            if ">" in desc:
                prod_parte, chica_parte = desc.split(">", 1)
                nombre_persona = chica_parte.strip().upper()
            else:
                nombre_persona = "GENERAL"
                prod_parte = desc

            comision_unit = calcular_comision_fn(prod_parte)
            cantidad = float(row["CANTIDAD"]) if pd.notna(row.get("CANTIDAD")) else 1.0

            emp_id, creado = obtener_o_crear_empleado(nombre_persona, "Chicas / Bailarinas (Comisiones)", 300.0, fecha_date=f_filtro_date, existing_session=session)
            if creado:
                nuevas_detectadas.append(nombre_persona)

            kwargs = {
                "fecha": f_filtro_date,
                "clave": row.get("CLAVE"),
                "descripcion": desc,
                "grupo": row.get("GRUPO"),
                "precio": row.get("PRECIO"),
                "cantidad": cantidad,
                "empleado_nombre": nombre_persona,
                "empleado_id": emp_id,
                "comision_unitaria": comision_unit,
                "archivo_origen": archivo_origen,
            }

            session.add(ProductoChica(**kwargs))
        session.commit()
        return nuevas_detectadas
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales, nomina_personal_fijo=4483.66, fecha_corte=None, usuario_nombre="sistema"):
    session = get_session()
    f_filtro_str = fecha_corte if fecha_corte else datetime.now().strftime('%Y-%m-%d')
    f_filtro_date = datetime.strptime(f_filtro_str, "%Y-%m-%d").date()
    
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == f_filtro_date).first()

    if hoy:
        hoy.gasto_cocina = gasto_cocina
        hoy.gasto_compras = gasto_compras
        hoy.gasto_vales = gasto_vales
    else:
        kwargs = {
            "fecha": f_filtro_date,
            "gasto_cocina": gasto_cocina,
            "gasto_compras": gasto_compras,
            "gasto_vales": gasto_vales,
            "nomina_personal_fijo": nomina_personal_fijo,
        }
        session.add(GastoDiario(**kwargs))
    session.commit()
    session.close()


def obtener_fechas_disponibles() -> list:
    session = get_session()
    try:
        fechas_v = session.query(CorteVenta.fecha).distinct().all()
        fechas_c = session.query(ProductoChica.fecha).distinct().all()
        fechas_g = session.query(GastoDiario.fecha).distinct().all()
        fechas_n = session.query(NominaDiaria.fecha).distinct().all()
        
        todas = set([f[0] for f in fechas_v + fechas_c + fechas_g + fechas_n if f[0] is not None])
        ordenadas = sorted(list(todas), reverse=True)
        return [f.strftime('%Y-%m-%d') for f in ordenadas]
    finally:
        session.close()


def cargar_ventas_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
    
    query = session.query(CorteVenta).filter(CorteVenta.fecha == f_date)
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def cargar_chicas_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
    
    query = session.query(ProductoChica).filter(ProductoChica.fecha == f_date)
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def cargar_gastos_hoy(fecha_str: str = None):
    session = get_session()
    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
    
    hoy = session.query(GastoDiario).filter(GastoDiario.fecha == f_date).first()
    session.close()
    return hoy


def cargar_empleados_rango_df(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    session = get_session()
    f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
    f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    
    query = session.query(
        Empleado.id,
        Empleado.nombre,
        Empleado.tipo,
        func.sum(NominaDiaria.sueldo_base).label("sueldo_base"),
        func.sum(NominaDiaria.vales_nomina).label("vales_nomina"),
        func.sum(NominaDiaria.descuento_nomina).label("descuento_nomina"),
        func.sum(NominaDiaria.transferencia_nomina).label("transferencia_nomina")
    ).join(NominaDiaria, Empleado.id == NominaDiaria.empleado_id).filter(
        NominaDiaria.fecha >= f_ini,
        NominaDiaria.fecha <= f_fin,
        Empleado.activo == True
    ).group_by(Empleado.id, Empleado.nombre, Empleado.tipo).order_by(Empleado.id)
    
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    
    if not df.empty:
        df['sueldo_base'] = df['sueldo_base'].astype(float)
        df['vales_nomina'] = df['vales_nomina'].astype(float)
        df['descuento_nomina'] = df['descuento_nomina'].astype(float)
        df['transferencia_nomina'] = df['transferencia_nomina'].astype(float)
    return df


def cargar_chicas_rango_df(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    session = get_session()
    f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
    f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    
    query = session.query(ProductoChica).filter(
        ProductoChica.fecha >= f_ini,
        ProductoChica.fecha <= f_fin
    )
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def cargar_ventas_rango_df(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    session = get_session()
    f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
    f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
    
    query = session.query(CorteVenta).filter(
        CorteVenta.fecha >= f_ini,
        CorteVenta.fecha <= f_fin
    )
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def reiniciar_base_de_datos():
    session = get_session()
    try:
        session.commit()
        session.execute(db_text('DROP TABLE IF EXISTS asistencias CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS cortes_bloqueos CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS nomina_diaria CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS cortes_productos_chicas CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS cortes_ventas CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS gastos_diarios CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS empleados CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS puestos_catalogo CASCADE;'))
        session.execute(db_text('DROP TABLE IF EXISTS usuarios_sistema CASCADE;'))
        session.commit()
        
        Base.metadata.create_all(session.bind)
        
        puestos_iniciales = [
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
        ]
        session.add_all(puestos_iniciales)
        session.commit()
        inicializar_usuarios_por_defecto()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


try:
    _session_auto = get_session()
    Base.metadata.create_all(_session_auto.bind)
    _session_auto.close()
except Exception:
    pass