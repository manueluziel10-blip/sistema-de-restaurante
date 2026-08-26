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
import hashlib
import hmac
import os
import secrets
import unicodedata

from database import get_session

Base = declarative_base()


# --- UTILIDADES DE HASH (contraseñas de usuarios y PIN de empleados) ---
# Usa PBKDF2-HMAC-SHA256 (parte de la librería estándar, sin dependencias extra).
# El valor guardado en BD tiene el formato "salt_hex$hash_hex".

def _hash_valor(valor_plano: str, salt_hex: str = None) -> str:
    if salt_hex is None:
        salt_hex = secrets.token_hex(16)
    salt_bytes = bytes.fromhex(salt_hex)
    hash_bytes = hashlib.pbkdf2_hmac('sha256', valor_plano.encode('utf-8'), salt_bytes, 100_000)
    return f"{salt_hex}${hash_bytes.hex()}"


def _es_valor_hasheado(valor_guardado: str) -> bool:
    return isinstance(valor_guardado, str) and '$' in valor_guardado and len(valor_guardado.split('$')[0]) == 32


def _verificar_valor(valor_plano: str, valor_guardado: str) -> bool:
    if not valor_guardado:
        return False
    if not _es_valor_hasheado(valor_guardado):
        # Compatibilidad con datos viejos guardados en texto plano
        return hmac.compare_digest(str(valor_plano), str(valor_guardado))
    salt_hex, hash_hex = valor_guardado.split('$', 1)
    intento = _hash_valor(valor_plano, salt_hex)
    return hmac.compare_digest(intento, valor_guardado)


def generar_pin_aleatorio() -> str:
    return f"{secrets.randbelow(10000):04d}"


def normalizar_nombre(nombre) -> str:
    """Normaliza un nombre de empleado para comparar/guardar de forma
    consistente: quita espacios extra, pasa a mayúsculas y elimina
    acentos/diacríticos — así "DÍAZ" y "DIAZ" se tratan como el mismo
    empleado en vez de crear un duplicado por una tilde de diferencia
    entre el Excel y lo que ya está en la base de datos."""
    texto = str(nombre).strip().upper()
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')


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
    pin_hash = Column(String, nullable=True)
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

    __table_args__ = (
        UniqueConstraint('empleado_id', 'fecha', name='unique_empleado_fecha_nomina'),
    )


class Asistencia(Base):
    __tablename__ = "asistencias"
    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    nombre_empleado = Column(String)
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
    # NOTA: cambia estas contraseñas por defecto ("admin123" / "cajero123")
    # la primera vez que entres al sistema, desde "6. Usuarios y Accesos".
    session = get_session()
    try:
        admin = session.query(UsuarioSistema).filter(UsuarioSistema.username == "admin").first()
        if not admin:
            session.add(UsuarioSistema(username="admin", password=_hash_valor("admin123"), rol="admin"))
        cajero = session.query(UsuarioSistema).filter(UsuarioSistema.username == "cajero").first()
        if not cajero:
            session.add(UsuarioSistema(username="cajero", password=_hash_valor("cajero123"), rol="cajero"))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def validar_login(username, password):
    session = get_session()
    try:
        user = session.query(UsuarioSistema).filter(UsuarioSistema.username == username).first()
        if not user:
            return None
        if not _verificar_valor(password, user.password):
            return None
        # Migración transparente: si la contraseña seguía en texto plano, la re-guardamos hasheada.
        if not _es_valor_hasheado(user.password):
            user.password = _hash_valor(password)
            session.commit()
        return {"username": user.username, "rol": user.rol}
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
            nuevo = UsuarioSistema(username=username, password=_hash_valor(password), rol=rol)
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
                user.password = _hash_valor(nueva_password)
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


def _deduplicar_nomina_diaria(session) -> int:
    """Fusiona (elimina) filas duplicadas de nomina_diaria para el mismo
    (empleado_id, fecha), quedándose con la más reciente (mayor id).
    Es un paso previo necesario para poder crear la restricción única
    que faltaba (ver asegurar_nomina_dia). Devuelve cuántas filas se
    eliminaron."""
    try:
        duplicados = session.execute(db_text("""
            SELECT empleado_id, fecha FROM nomina_diaria
            GROUP BY empleado_id, fecha HAVING COUNT(*) > 1
        """)).fetchall()

        total_borradas = 0
        for empleado_id, fecha in duplicados:
            ids = session.execute(db_text("""
                SELECT id FROM nomina_diaria
                WHERE empleado_id = :emp_id AND fecha = :fecha
                ORDER BY id DESC
            """), {"emp_id": empleado_id, "fecha": fecha}).fetchall()
            for row in ids[1:]:  # conserva la primera (más reciente), borra el resto
                session.execute(db_text("DELETE FROM nomina_diaria WHERE id = :id"), {"id": row[0]})
                total_borradas += 1
        session.commit()
        return total_borradas
    except Exception as e:
        session.rollback()
        print(f"[models.py] Error al deduplicar nomina_diaria: {e}")
        return 0


def asegurar_nomina_dia(session, fecha_date):
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

            # IMPORTANTE: el resto del código (registro de asistencia, sincronización
            # automática, reparación de nómina) usa "ON CONFLICT (empleado_id, fecha)
            # DO NOTHING", lo cual requiere que exista una restricción única sobre
            # esas dos columnas. Esa restricción nunca se creó en la tabla real, así
            # que todos esos INSERT fallaban en silencio (el error quedaba atrapado
            # por un try/except y solo se imprimía en los logs). Aquí se crea si falta.
            constraints = inspector.get_unique_constraints('nomina_diaria')
            tiene_restriccion = any(
                set(c.get('column_names', [])) == {'empleado_id', 'fecha'} for c in constraints
            )
            if not tiene_restriccion:
                try:
                    session.execute(db_text(
                        "ALTER TABLE nomina_diaria ADD CONSTRAINT unique_empleado_fecha_nomina UNIQUE (empleado_id, fecha)"
                    ))
                    session.commit()
                except Exception:
                    session.rollback()
                    # Probablemente hay filas duplicadas (empleado_id, fecha) de
                    # antes de esta corrección. Se fusionan y se reintenta una vez.
                    borradas = _deduplicar_nomina_diaria(session)
                    if borradas:
                        print(f"[models.py] Se fusionaron {borradas} fila(s) duplicadas en nomina_diaria.")
                    try:
                        session.execute(db_text(
                            "ALTER TABLE nomina_diaria ADD CONSTRAINT unique_empleado_fecha_nomina UNIQUE (empleado_id, fecha)"
                        ))
                        session.commit()
                    except Exception as e_final:
                        session.rollback()
                        print(f"[models.py] No se pudo crear la restricción única en nomina_diaria: {e_final}")
    except Exception:
        session.rollback()


def asegurar_columnas_empleado(session):
    try:
        inspector = inspect(session.bind)
        if 'empleados' in inspector.get_table_names():
            columnas_tabla = [col['name'] for col in inspector.get_columns('empleados')]
            if 'pin_hash' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE empleados ADD COLUMN pin_hash VARCHAR"))
                session.commit()
    except Exception:
        session.rollback()


def establecer_pin_empleado(empleado_id: int, pin_plano: str):
    """Asigna (o cambia) el PIN individual de un empleado, guardado con hash."""
    session = get_session()
    try:
        asegurar_columnas_empleado(session)
        emp = session.query(Empleado).filter(Empleado.id == empleado_id).first()
        if emp:
            emp.pin_hash = _hash_valor(str(pin_plano).strip())
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def verificar_pin_empleado(empleado_id: int, pin_ingresado: str) -> bool:
    """Valida el PIN de un empleado contra su hash individual.
    Si el empleado aún no tiene PIN configurado, no permite el acceso
    (en vez de aceptar un PIN genérico como antes)."""
    session = get_session()
    try:
        asegurar_columnas_empleado(session)
        emp = session.query(Empleado).filter(Empleado.id == empleado_id).first()
        if not emp or not emp.pin_hash:
            return False
        return _verificar_valor(str(pin_ingresado).strip(), emp.pin_hash)
    finally:
        session.close()


def cargar_empleados_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
    f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
    
    asegurar_nomina_dia(session, f_date)
    asegurar_columnas_empleado(session)
    
    # Sincronización automática: crea nóminas faltantes para empleados activos que ya tengan asistencia en esta fecha
    try:
        session.execute(
            db_text("""
                INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, penalizada)
                SELECT :fecha, a.empleado_id, COALESCE(e.sueldo_base, 300.0), 0.0, 100.0, 0.0, FALSE
                FROM asistencias a
                JOIN empleados e ON e.id = a.empleado_id
                WHERE a.fecha = :fecha AND e.activo = TRUE
                ON CONFLICT (empleado_id, fecha) DO NOTHING;
            """),
            {"fecha": f_date}
        )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error al sincronizar nóminas automáticas: {e}")

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


def agregar_empleado_catalogo(nombre, tipo, sueldo_base, pin=None):
    """Da de alta o actualiza un empleado SOLO en el catálogo (tabla
    empleados) — NO crea ni toca ningún registro de nomina_diaria.
    Devuelve el id del empleado (nuevo o existente).

    Se usa para altas individuales sueltas. Para importar varios
    empleados de un Excel a la vez, usar agregar_empleados_catalogo_bulk
    (una sola conexión para todo el archivo, mucho más rápida).
    """
    session = get_session()
    try:
        asegurar_columnas_empleado(session)
        asegurar_puesto_existe(session, tipo)
        emp = session.query(Empleado).filter(Empleado.nombre == normalizar_nombre(nombre)).first()
        if emp:
            emp.tipo = tipo
            emp.sueldo_base = sueldo_base
            emp.activo = True
            if pin:
                emp.pin_hash = _hash_valor(str(pin).strip())
            session.commit()
            return emp.id
        else:
            pin_final = str(pin).strip() if pin else generar_pin_aleatorio()
            emp = Empleado(
                nombre=normalizar_nombre(nombre),
                tipo=tipo,
                sueldo_base=sueldo_base,
                activo=True,
                pin_hash=_hash_valor(pin_final)
            )
            session.add(emp)
            session.commit()
            session.refresh(emp)
            return emp.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def agregar_empleados_catalogo_bulk(filas: list) -> list:
    """Versión en lote de agregar_empleado_catalogo, pensada para la
    importación masiva por Excel. Antes, cada fila del archivo abría su
    propia conexión a la base de datos (get_session/commit/close) y
    volvía a verificar el esquema y el catálogo de puestos desde cero —
    con un Excel de 50+ empleados eso son 50+ viajes redondos a la BD.
    Aquí se hace todo en UNA sola sesión: el esquema y los puestos se
    verifican una sola vez, y solo hay un commit al final.

    filas: lista de dicts con llaves 'nombre', 'tipo', 'sueldo_base',
    y opcionalmente 'pin'.
    Devuelve una lista de empleado_id en el mismo orden que 'filas'.
    """
    if not filas:
        return []
    session = get_session()
    try:
        asegurar_columnas_empleado(session)
        # Solo se asegura cada puesto distinto una vez, no por fila.
        puestos_unicos = {f['tipo'] for f in filas}
        for puesto in puestos_unicos:
            asegurar_puesto_existe(session, puesto)

        nombres_norm = [normalizar_nombre(f['nombre']) for f in filas]
        existentes = session.query(Empleado).filter(Empleado.nombre.in_(nombres_norm)).all()
        mapa_existentes = {e.nombre: e for e in existentes}

        ids_resultado = []
        for f in filas:
            nombre_norm = normalizar_nombre(f['nombre'])
            pin = f.get('pin')
            emp = mapa_existentes.get(nombre_norm)
            if emp:
                emp.tipo = f['tipo']
                emp.sueldo_base = f['sueldo_base']
                emp.activo = True
                if pin:
                    emp.pin_hash = _hash_valor(str(pin).strip())
            else:
                pin_final = str(pin).strip() if pin else generar_pin_aleatorio()
                emp = Empleado(
                    nombre=nombre_norm,
                    tipo=f['tipo'],
                    sueldo_base=f['sueldo_base'],
                    activo=True,
                    pin_hash=_hash_valor(pin_final)
                )
                session.add(emp)
                session.flush()  # asigna el id sin comitear toda la transacción
                mapa_existentes[nombre_norm] = emp
            ids_resultado.append(emp.id)

        session.commit()
        return ids_resultado
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def registrar_asistencia_lista_empleados(empleado_ids: list, fecha_str: str,
                                          comentario: str = "Automático por alta masiva"):
    """Marca 'Presente' y crea la nómina diaria SOLO para los
    empleado_id indicados, en la fecha dada.

    A diferencia de registrar_asistencias_automaticas_dia() —que marca a
    TODOS los empleados activos del sistema, hayan o no venido en el
    archivo que se subió— esta función es selectiva: solo toca a los
    empleados que realmente vinieron en el Excel procesado."""
    if not empleado_ids:
        return
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        empleados = session.query(Empleado.id, Empleado.nombre, Empleado.sueldo_base).filter(
            Empleado.id.in_(empleado_ids), Empleado.activo == True
        ).all()
        for emp_id, nombre_emp, sueldo_emp in empleados:
            session.execute(
                db_text("""
                    INSERT INTO asistencias (empleado_id, nombre_empleado, fecha, estado, comentarios)
                    VALUES (:emp_id, :nombre_emp, :fecha, 'Presente', :comentario)
                    ON CONFLICT (empleado_id, fecha) DO NOTHING
                """),
                {"emp_id": emp_id, "nombre_emp": nombre_emp, "fecha": f_date, "comentario": comentario}
            )
            session.execute(
                db_text("""
                    INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, penalizada)
                    VALUES (:fecha, :emp_id, :sueldo, 0.0, 100.0, 0.0, FALSE)
                    ON CONFLICT (empleado_id, fecha) DO NOTHING
                """),
                {"fecha": f_date, "emp_id": emp_id, "sueldo": float(sueldo_emp) if sueldo_emp is not None else 300.0}
            )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error al registrar asistencia por lista de empleados: {e}")
    finally:
        session.close()


def agregar_empleado(nombre, tipo, sueldo_base, fecha_str=None, pin=None, **kwargs):
    session = get_session()
    try:
        asegurar_columnas_empleado(session)
        asegurar_puesto_existe(session, tipo)
        emp = session.query(Empleado).filter(Empleado.nombre == normalizar_nombre(nombre)).first()
        if emp:
            emp.tipo = tipo
            emp.sueldo_base = sueldo_base
            emp.activo = True
            if pin:
                emp.pin_hash = _hash_valor(str(pin).strip())
            session.commit()
        else:
            pin_final = str(pin).strip() if pin else generar_pin_aleatorio()
            emp = Empleado(
                nombre=normalizar_nombre(nombre),
                tipo=tipo,
                sueldo_base=sueldo_base,
                activo=True,
                pin_hash=_hash_valor(pin_final)
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
    except Exception as e:
        session.rollback()
        raise e
    finally:
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


def eliminar_empleado_por_id(emp_id, fecha_str):
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        
        # 1. Limpiar dependencias asociadas a la fecha activa
        session.execute(
            db_text("DELETE FROM cortes_productos_chicas WHERE empleado_id = :emp_id AND fecha = :fecha"),
            {"emp_id": emp_id, "fecha": f_date}
        )
        session.execute(
            db_text("DELETE FROM nomina_diaria WHERE empleado_id = :emp_id AND fecha = :fecha"),
            {"emp_id": emp_id, "fecha": f_date}
        )
        session.execute(
            db_text("DELETE FROM asistencias WHERE empleado_id = :emp_id AND fecha = :fecha"),
            {"emp_id": emp_id, "fecha": f_date}
        )
        
        # 2. Verificar si tiene registros históricos en otras fechas
        otras_nominas = session.execute(
            db_text("SELECT COUNT(*) FROM nomina_diaria WHERE empleado_id = :emp_id AND fecha != :fecha"),
            {"emp_id": emp_id, "fecha": f_date}
        ).scalar()
        
        if otras_nominas == 0:
            session.execute(
                db_text("DELETE FROM cortes_productos_chicas WHERE empleado_id = :emp_id"),
                {"emp_id": emp_id}
            )
            session.execute(
                db_text("DELETE FROM cortes_ventas WHERE idmesero = :emp_id"),
                {"emp_id": emp_id}
            )
            session.execute(
                db_text("DELETE FROM empleados WHERE id = :emp_id"),
                {"emp_id": emp_id}
            )
            
        session.commit()
        return True, None
    except Exception as e:
        session.rollback()
        print(f"Error detallado al eliminar empleado: {e}")
        return False, str(e)
    finally:
        session.close()


def obtener_o_crear_empleado(nombre: str, tipo: str = "Chicas / Bailarinas (Comisiones)", sueldo_base: float = 300.0,
                              fecha_date=None, existing_session=None, cache: dict = None):
    """cache: dict opcional {nombre_upper: empleado_id} que el caller
    mantiene durante todo un archivo/corte. Si el nombre ya se resolvió
    antes en esta misma carga (típico: el mismo mesero aparece en
    decenas o cientos de filas del Excel), se evita volver a consultar
    o crear — solo se regresa el id ya conocido. Esto es lo que más
    acelera la carga de archivos grandes, ya que antes cada fila volvía
    a golpear la base de datos aunque fuera el mismo empleado."""
    nombre_norm = normalizar_nombre(nombre)
    if cache is not None and nombre_norm in cache:
        return cache[nombre_norm], False

    session = existing_session if existing_session else get_session()
    try:
        if existing_session is None:
            # Llamada aislada (sin sesión/lote compartido): se asegura el
            # esquema aquí. Cuando SÍ hay existing_session, se asume que
            # el caller ya hizo esto una sola vez antes del bucle.
            asegurar_columnas_empleado(session)
            asegurar_puesto_existe(session, tipo, sueldo_base, es_comision=True)

        emp = session.query(Empleado).filter(Empleado.nombre == nombre_norm).first()
        creado = False
        if not emp:
            emp = Empleado(
                nombre=nombre_norm,
                tipo=tipo,
                sueldo_base=sueldo_base,
                activo=True,
                pin_hash=_hash_valor(generar_pin_aleatorio())
            )
            session.add(emp)
            # flush() asigna el id sin cerrar/comitear toda la transacción
            # — mucho más barato que session.commit() en cada fila.
            session.flush()
            creado = True
        else:
            emp.activo = True

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
            session.flush()

        if existing_session is None:
            session.commit()

        if cache is not None:
            cache[nombre_norm] = emp.id

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
        # Esquema y catálogo de puesto: UNA sola vez para todo el archivo,
        # no en cada fila (antes esto se repetía por cada venta).
        asegurar_columnas_empleado(session)
        asegurar_puesto_existe(session, tipo_por_defecto)

        # IMPORTANTE: how='outer' (antes 'left'). Con 'left' se perdían por
        # completo los registros que solo existen en el archivo de propinas
        # — típico de un Cajero/Gerente/Capitán que cobra una cuenta y recibe
        # propina directo, sin generar su propia línea en "ventasmeseros.xls".
        df_completo = pd.merge(df_v, df_propinas, on='idmesero', how='outer', suffixes=('_v', '_p'))

        # El nombre puede venir solo de uno de los dos archivos —se resuelve
        # ANTES de rellenar NaN con 0 (si no, un nombre faltante se
        # convertiría en el número 0 en vez de tomarse del otro archivo).
        if 'nombre_v' in df_completo.columns and 'nombre_p' in df_completo.columns:
            df_completo['nombre_resuelto'] = df_completo['nombre_v'].combine_first(df_completo['nombre_p'])
        elif 'nombre_v' in df_completo.columns:
            df_completo['nombre_resuelto'] = df_completo['nombre_v']
        elif 'nombre_p' in df_completo.columns:
            df_completo['nombre_resuelto'] = df_completo['nombre_p']
        else:
            df_completo['nombre_resuelto'] = "MESERO"

        df_completo = df_completo.fillna(0)

        # No se da de alta ni se marca actividad para filas con TODO en $0
        # (ventas y propinas). Soft Restaurant exporta el reporte de
        # propinas con TODOS los meseros/cajeros registrados, aunque ese
        # día no hayan ido a trabajar — vienen con puros ceros. Sin este
        # filtro, esas filas "fantasma" se daban de alta y se les pagaba
        # sueldo base como si hubieran trabajado.
        columnas_actividad = [c for c in [
            'importe_v', 'importe_p', 'importe', 'efectivo', 'tarjeta', 'vales', 'otros',
            'propina', 'propinaefectivo', 'propinatarjeta', 'propinavales', 'propinacredito',
            'propinatotal', 'comision', 'cuentas', 'nopersonas'
        ] if c in df_completo.columns]

        filas_sin_actividad = 0
        if columnas_actividad:
            suma_actividad = df_completo[columnas_actividad].apply(pd.to_numeric, errors='coerce').fillna(0).abs().sum(axis=1)
            filas_sin_actividad = int((suma_actividad == 0).sum())
            df_completo = df_completo[suma_actividad > 0].copy()

        cache_empleados = {}
        nuevas_filas = []
        ids_con_actividad = []
        for _, row in df_completo.iterrows():
            nombre_mesero = normalizar_nombre(row.get("nombre_resuelto", "MESERO"))
            emp_id, _ = obtener_o_crear_empleado(
                nombre_mesero, tipo_por_defecto, 300.0, fecha_date=f_filtro_date,
                existing_session=session, cache=cache_empleados
            )
            ids_con_actividad.append(emp_id)

            nuevas_filas.append(CorteVenta(
                fecha=f_filtro_date,
                idmesero=emp_id,
                importe=row.get("importe_v", row.get("importe", 0)),
                efectivo=row.get("efectivo", 0),
                propina_efectivo=row.get("propinaefectivo", 0),
                tarjeta=row.get("tarjeta", 0),
                propina_tarjeta=row.get("propinatarjeta", 0),
                vales=row.get("vales", 0),
                propina_vales=row.get("propinavales", 0),
                otros=row.get("otros", 0),
                archivo_origen=archivo_origen,
            ))

        session.add_all(nuevas_filas)
        session.commit()
        return list(set(ids_con_actividad)), filas_sin_actividad
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

        # Esquema y catálogo de puesto: UNA sola vez para todo el archivo.
        asegurar_columnas_empleado(session)
        asegurar_puesto_existe(session, "Chicas / Bailarinas (Comisiones)", 300.0, es_comision=True)

        nuevas_detectadas = []
        cache_empleados = {}
        nuevas_filas = []
        ids_con_actividad = []
        for _, row in filas_chicas.iterrows():
            desc = str(row["DESCRIPCION"])
            if ">" in desc:
                prod_parte, chica_parte = desc.split(">", 1)
                nombre_persona = normalizar_nombre(chica_parte)
            else:
                nombre_persona = "GENERAL"
                prod_parte = desc

            comision_unit = calcular_comision_fn(prod_parte)
            cantidad = float(row["CANTIDAD"]) if pd.notna(row.get("CANTIDAD")) else 1.0

            emp_id, creado = obtener_o_crear_empleado(
                nombre_persona, "Chicas / Bailarinas (Comisiones)", 300.0, fecha_date=f_filtro_date,
                existing_session=session, cache=cache_empleados
            )
            if creado:
                nuevas_detectadas.append(nombre_persona)
            ids_con_actividad.append(emp_id)

            nuevas_filas.append(ProductoChica(
                fecha=f_filtro_date,
                clave=row.get("CLAVE"),
                descripcion=desc,
                grupo=row.get("GRUPO"),
                precio=row.get("PRECIO"),
                cantidad=cantidad,
                empleado_nombre=nombre_persona,
                empleado_id=emp_id,
                comision_unitaria=comision_unit,
                archivo_origen=archivo_origen,
            ))

        session.add_all(nuevas_filas)
        session.commit()
        return nuevas_detectadas, list(set(ids_con_actividad))
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


def obtener_penalizaciones_rango(fecha_inicio: str, fecha_fin: str) -> dict:
    """Devuelve {empleado_id: set(fechas)} con los días marcados como
    'penalizada' dentro del rango, para aplicar la mitad de comisión
    día por día en los reportes por periodo (la penalización es un
    flag diario en NominaDiaria, no aplica al periodo completo)."""
    session = get_session()
    try:
        f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()
        filas = session.query(NominaDiaria.empleado_id, NominaDiaria.fecha).filter(
            NominaDiaria.fecha >= f_ini,
            NominaDiaria.fecha <= f_fin,
            NominaDiaria.penalizada == True
        ).all()
        mapa = {}
        for emp_id, fecha in filas:
            mapa.setdefault(emp_id, set()).add(fecha)
        return mapa
    finally:
        session.close()


def diagnosticar_dias_rango(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    """Para cada empleado, compara sus días de asistencia contra sus días
    con registro en nomina_diaria dentro del rango. Detecta:
    - días con asistencia pero SIN fila en nomina_diaria (no se les paga ese día)
    - días con fila en nomina_diaria pero con sueldo_base en $0

    Sirve para explicar por qué "Asistencias (Días)" y "Sueldo Base
    Acumulado" no coinciden en el reporte por periodo."""
    session = get_session()
    try:
        f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()

        asis = session.query(Asistencia.empleado_id, Asistencia.nombre_empleado, Asistencia.fecha).filter(
            Asistencia.fecha >= f_ini, Asistencia.fecha <= f_fin
        ).all()
        nom = session.query(NominaDiaria.empleado_id, NominaDiaria.fecha, NominaDiaria.sueldo_base).filter(
            NominaDiaria.fecha >= f_ini, NominaDiaria.fecha <= f_fin
        ).all()

        mapa_asis = {}
        for emp_id, nombre, fecha in asis:
            info = mapa_asis.setdefault(emp_id, {"nombre": nombre, "fechas": set()})
            info["fechas"].add(fecha)

        mapa_nom = {}
        for emp_id, fecha, sueldo in nom:
            mapa_nom.setdefault(emp_id, {})[fecha] = float(sueldo) if sueldo is not None else 0.0

        filas = []
        for emp_id, info in mapa_asis.items():
            fechas_asistencia = info["fechas"]
            fechas_nomina_dict = mapa_nom.get(emp_id, {})
            fechas_nomina = set(fechas_nomina_dict.keys())

            dias_sin_nomina = sorted(fechas_asistencia - fechas_nomina)
            dias_nomina_cero = sorted(f for f in (fechas_asistencia & fechas_nomina) if fechas_nomina_dict[f] == 0.0)

            if dias_sin_nomina or dias_nomina_cero:
                filas.append({
                    "empleado_id": emp_id,
                    "nombre": info["nombre"],
                    "dias_asistencia_sin_nomina": ", ".join(str(f) for f in dias_sin_nomina) or "-",
                    "dias_con_sueldo_base_en_cero": ", ".join(str(f) for f in dias_nomina_cero) or "-",
                    "total_dias_afectados": len(dias_sin_nomina) + len(dias_nomina_cero),
                })
        return pd.DataFrame(filas)
    finally:
        session.close()


def reparar_nomina_faltante_rango(fecha_inicio: str, fecha_fin: str) -> int:
    """Crea la fila de nomina_diaria (con el sueldo_base actual del
    empleado) para cada día del rango en el que exista asistencia pero
    falte el registro de nómina. NO toca días donde ya existe una fila
    (aunque esté en $0, para no pisar un $0 puesto a propósito por un
    admin). Devuelve cuántas filas se crearon."""
    session = get_session()
    try:
        f_ini = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        f_fin = datetime.strptime(fecha_fin, "%Y-%m-%d").date()

        resultado = session.execute(
            db_text("""
                INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, penalizada)
                SELECT DISTINCT a.fecha, a.empleado_id, COALESCE(e.sueldo_base, 300.0), 0.0, 100.0, 0.0, FALSE
                FROM asistencias a
                JOIN empleados e ON e.id = a.empleado_id
                WHERE a.fecha BETWEEN :f_ini AND :f_fin
                ON CONFLICT (empleado_id, fecha) DO NOTHING
                RETURNING 1;
            """),
            {"f_ini": f_ini, "f_fin": f_fin}
        )
        filas_creadas = len(resultado.fetchall())
        session.commit()
        return filas_creadas
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


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
    # Migración de la restricción única de nomina_diaria (ver asegurar_nomina_dia):
    # se corre aquí, al arrancar el módulo, para que quede lista ANTES de que
    # cualquier registro de asistencia (incluido el modo kiosko público, que no
    # pasa por cargar_empleados_df) intente un INSERT ... ON CONFLICT.
    asegurar_nomina_dia(_session_auto, None)
    _session_auto.close()
except Exception as _err_inicial:
    # No se traga el error: se deja constancia visible en consola/logs.
    # Si la BD no está disponible al arrancar, es mejor saberlo de inmediato
    # que descubrirlo más tarde con fallas difíciles de rastrear.
    print(f"[models.py] ADVERTENCIA: no se pudo inicializar la conexión/tablas al arrancar: {_err_inicial}")