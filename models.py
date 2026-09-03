"""
Modelos SQLAlchemy + funciones de acceso a datos con soporte histórico completo por fecha, ID y empleado.
"""

from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime,
    ForeignKey, func, inspect, UniqueConstraint, text as db_text
)
from sqlalchemy.orm import declarative_base, relationship
import pandas as pd
from datetime import datetime, time
import hashlib
import hmac
import os
import secrets
import unicodedata
import io

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
    fecha_nacimiento = Column(Date)


class CarnetSanidad(Base):
    __tablename__ = "carnet_sanidad"
    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False, unique=True)
    fecha_entrega = Column(Date)
    fecha_expiracion = Column(Date)


class NominaDiaria(Base):
    __tablename__ = "nomina_diaria"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    sueldo_base = Column(Numeric(10, 2), default=0.0)
    vales_nomina = Column(Numeric(10, 2), default=0.0)
    descuento_nomina = Column(Numeric(10, 2), default=100.0)
    transferencia_nomina = Column(Numeric(10, 2), default=0.0)
    consumo_cocina = Column(Numeric(10, 2), default=0.0)
    vales_excel = Column(Numeric(10, 2), default=0.0)
    consumo_comedor_excel = Column(Numeric(10, 2), default=0.0)
    comision_excel = Column(Numeric(10, 2), default=0.0)
    origen_importacion = Column(String)
    penalizada = Column(Boolean, default=False)
    puesto_dia = Column(String)
    retencion_nomina = Column(Numeric(10, 2), default=0.0)
    peinado_maquillaje = Column(Numeric(10, 2), default=0.0)
    dulceria = Column(Numeric(10, 2), default=0.0)

    __table_args__ = (
        UniqueConstraint('empleado_id', 'fecha', name='unique_empleado_fecha_nomina'),
    )


class ValeDiario(Base):
    __tablename__ = "vales_diarios"
    id = Column(Integer, primary_key=True, autoincrement=True)
    folio = Column(String, unique=True, nullable=False)
    fecha = Column(Date, nullable=False)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    empleado_nombre = Column(String, nullable=False)
    importe = Column(Numeric(10, 2), nullable=False, default=0.0)
    importe_bruto = Column(Numeric(10, 2), nullable=False, default=0.0)
    abono_boutique = Column(Numeric(10, 2), nullable=False, default=0.0)
    estado = Column(String(20), nullable=False, default="PENDIENTE")
    forma_pago = Column(String(30))
    fecha_pago = Column(Date)
    archivo_origen = Column(String)
    creado_en = Column(DateTime, server_default=func.now())


class ProductoBoutique(Base):
    __tablename__ = "productos_boutique"
    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String)
    nombre = Column(String, nullable=False)
    categoria = Column(String, nullable=False)
    talla = Column(String)
    precio_venta = Column(Numeric(10, 2), nullable=False, default=0.0)
    stock = Column(Integer, nullable=False, default=0)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, server_default=func.now())


class VentaBoutique(Base):
    __tablename__ = "ventas_boutique"
    id = Column(Integer, primary_key=True, autoincrement=True)
    folio = Column(String, unique=True, nullable=False)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos_boutique.id"), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    total = Column(Numeric(10, 2), nullable=False, default=0.0)
    fecha_venta = Column(Date, nullable=False)
    estatus_pago = Column(String(20), nullable=False, default="Pendiente")
    metodo_pago = Column(String(30))
    fecha_pago = Column(Date)
    creado_en = Column(DateTime, server_default=func.now())


class AbonoBoutique(Base):
    """Pago (abono) de un empleado hacia su saldo general de la Boutique —
    no se liga a una venta/folio en particular, se aplica contra el total
    pendiente de todas sus compras."""
    __tablename__ = "abonos_boutique"
    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    metodo_pago = Column(String(30), nullable=False)
    fecha_pago = Column(Date, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())


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
    fondo_apertura = Column(Numeric(10, 2))
    monto_cierre = Column(Numeric(10, 2))


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


class LogMovimiento(Base):
    """Bitácora de acciones sensibles del sistema (altas/bajas de
    empleados, cambios de puesto, cierres de corte, vales, etc.) — quién
    hizo qué y cuándo."""
    __tablename__ = "log_movimientos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario = Column(String, nullable=False)
    accion = Column(String, nullable=False)
    detalle = Column(String)
    fecha = Column(DateTime, server_default=func.now())


def registrar_log(usuario: str, accion: str, detalle: str = ""):
    """Escribe una entrada en el log de movimientos. No lanza excepción
    si falla — nunca debe tumbar la acción principal por un problema de
    logging."""
    session = get_session()
    try:
        session.add(LogMovimiento(usuario=usuario or "sistema", accion=accion, detalle=detalle))
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error al registrar log de movimientos: {e}")
    finally:
        session.close()


def cargar_log_movimientos(limite: int = 500) -> pd.DataFrame:
    session = get_session()
    try:
        query = session.query(
            LogMovimiento.fecha, LogMovimiento.usuario, LogMovimiento.accion, LogMovimiento.detalle
        ).order_by(LogMovimiento.fecha.desc()).limit(limite)
        return pd.read_sql(query.statement, session.bind)
    finally:
        session.close()


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


def crear_usuario(username, password, rol, actor=None):
    session = get_session()
    try:
        existe = session.query(UsuarioSistema).filter(UsuarioSistema.username == username).first()
        if not existe:
            nuevo = UsuarioSistema(username=username, password=_hash_valor(password), rol=rol)
            session.add(nuevo)
            session.commit()
            registrar_log(actor or username, "Alta usuario del sistema", f"usuario={username}, rol={rol}")
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
        registrar_log(usuario, "Cierre de corte", f"fecha={fecha_str}")
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
            if 'consumo_cocina' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN consumo_cocina NUMERIC(10,2) DEFAULT 0.0"))
            if 'vales_excel' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN vales_excel NUMERIC(10,2) DEFAULT 0.0"))
            if 'consumo_comedor_excel' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN consumo_comedor_excel NUMERIC(10,2) DEFAULT 0.0"))
            if 'comision_excel' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN comision_excel NUMERIC(10,2) DEFAULT 0.0"))
            if 'origen_importacion' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN origen_importacion VARCHAR"))
            if 'penalizada' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN penalizada BOOLEAN DEFAULT 0"))
            if 'puesto_dia' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN puesto_dia VARCHAR"))
            if 'retencion_nomina' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN retencion_nomina NUMERIC(10,2) DEFAULT 0.0"))
            if 'peinado_maquillaje' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN peinado_maquillaje NUMERIC(10,2) DEFAULT 0.0"))
            if 'dulceria' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE nomina_diaria ADD COLUMN dulceria NUMERIC(10,2) DEFAULT 0.0"))

            # Filas insertadas por el sincronizador automático antes de que
            # estas columnas se agregaran explícitamente ahí quedaron con
            # NULL (SQLite no aplica el DEFAULT de la ORM a INSERTs en SQL
            # crudo). Se corrigen aquí para que no aparezcan como "None" en
            # la nómina ni rompan el cálculo de Total a Pagar.
            session.execute(db_text("UPDATE nomina_diaria SET retencion_nomina = 0.0 WHERE retencion_nomina IS NULL"))
            session.execute(db_text("UPDATE nomina_diaria SET peinado_maquillaje = 0.0 WHERE peinado_maquillaje IS NULL"))
            session.execute(db_text("UPDATE nomina_diaria SET dulceria = 0.0 WHERE dulceria IS NULL"))
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
            if 'fecha_nacimiento' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE empleados ADD COLUMN fecha_nacimiento DATE"))
            session.commit()
    except Exception:
        session.rollback()


def asegurar_columnas_gasto(session):
    try:
        inspector = inspect(session.bind)
        if 'gastos_diarios' in inspector.get_table_names():
            columnas_tabla = [col['name'] for col in inspector.get_columns('gastos_diarios')]
            if 'fondo_apertura' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE gastos_diarios ADD COLUMN fondo_apertura NUMERIC(10,2)"))
            if 'monto_cierre' not in columnas_tabla:
                session.execute(db_text("ALTER TABLE gastos_diarios ADD COLUMN monto_cierre NUMERIC(10,2)"))
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


def cargar_catalogo_empleados() -> pd.DataFrame:
    """Catálogo completo de empleados (id, nombre, tipo, sueldo_base, activo),
    sin filtrar por fecha ni por activo — para clasificar registros que
    abarcan varias fechas (ej. el historial completo de vales) por tipo de
    puesto, y para el directorio completo de personal (activos e inactivos)."""
    session = get_session()
    asegurar_columnas_empleado(session)
    df = pd.read_sql(
        session.query(
            Empleado.id, Empleado.nombre, Empleado.tipo, Empleado.sueldo_base,
            Empleado.activo, Empleado.creado_en, Empleado.fecha_nacimiento
        ).statement,
        session.bind
    )
    session.close()
    if not df.empty:
        df['sueldo_base'] = df['sueldo_base'].astype(float)
        df['activo'] = df['activo'].astype(bool)
    return df


def actualizar_fecha_nacimiento(empleado_id: int, fecha_nacimiento):
    session = get_session()
    try:
        emp = session.query(Empleado).filter(Empleado.id == empleado_id).first()
        if emp:
            emp.fecha_nacimiento = fecha_nacimiento
            session.commit()
    finally:
        session.close()


def cargar_carnet_sanidad_df() -> pd.DataFrame:
    """Todos los empleados activos con su carnet de sanidad (si ya lo
    tienen capturado) -- LEFT JOIN para que aparezcan incluso quienes
    todavía no tienen fecha de entrega/expiración registrada."""
    session = get_session()
    df = pd.read_sql(
        session.query(
            Empleado.id, Empleado.nombre,
            CarnetSanidad.fecha_entrega, CarnetSanidad.fecha_expiracion
        ).outerjoin(CarnetSanidad, Empleado.id == CarnetSanidad.empleado_id)
        .filter(Empleado.activo == True)
        .order_by(Empleado.nombre)
        .statement,
        session.bind
    )
    session.close()
    return df


def guardar_carnet_sanidad(empleado_id: int, fecha_entrega, fecha_expiracion):
    session = get_session()
    try:
        fila = session.query(CarnetSanidad).filter(CarnetSanidad.empleado_id == empleado_id).first()
        if fila:
            fila.fecha_entrega = fecha_entrega
            fila.fecha_expiracion = fecha_expiracion
        else:
            session.add(CarnetSanidad(
                empleado_id=empleado_id, fecha_entrega=fecha_entrega, fecha_expiracion=fecha_expiracion
            ))
        session.commit()
    finally:
        session.close()


PUESTOS_CATALOGO = {
    "Chicas / Bailarinas (Comisiones)": 600.0,
    "Mesero (Comisiones)": 300.0,
    "Barman (Fijo)": 300.0,
    "Seguridad (Fijo)": 500.0,
    "DJ (Fijo)": 600.0,
    "Animador (Fijo)": 400.0,
    "Gerente (Fijo)": 500.0,
    "Capitán de Mesero (Fijo)": 400.0,
    "Ayudante de Mesero (Fijo)": 300.0,
    "Cajero (Fijo)": 400.0,
    "DJ/Scom (Fijo)": 600.0
}


def es_chica_o_bailarina(tipo_str):
    t = str(tipo_str).upper()
    return ('CHICA' in t) or ('BAILARINA' in t)


def registrar_asistencia(empleado_id, nombre_emp, tipo_puesto, fecha_str, hora_actual_obj):
    """Registra el check-in de un empleado: crea/actualiza su fila de
    'asistencias' del día y asegura que exista su fila de 'nomina_diaria'
    (para que aparezca en la nómina del día sin que nadie más la cree a
    mano). Usada tanto por el módulo de asistencia logueado como por los
    kioskos públicos (web y de red local), para no duplicar esta lógica
    en varios lugares."""
    if es_chica_o_bailarina(tipo_puesto):
        limite_retardo = time(19, 30, 0)
    else:
        limite_retardo = time(18, 30, 0)

    estado = "Presente" if hora_actual_obj <= limite_retardo else "Retardo"
    comentarios = f"Check-in a las {hora_actual_obj.strftime('%H:%M:%S')}"

    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()

        existente = session.query(Asistencia).filter(
            Asistencia.empleado_id == empleado_id, Asistencia.fecha == f_date
        ).first()
        if existente:
            return False, existente.estado, "", f"Ya registraste tu asistencia hoy ({existente.comentarios})."

        session.execute(
            db_text("""
            INSERT INTO asistencias (empleado_id, nombre_empleado, fecha, estado, comentarios)
            VALUES (:emp_id, :nombre_emp, :fecha, :estado, :comentarios)
            ON CONFLICT (empleado_id, fecha)
            DO NOTHING
            """),
            {"emp_id": empleado_id, "nombre_emp": nombre_emp, "fecha": f_date, "estado": estado, "comentarios": comentarios}
        )

        sueldo_default = PUESTOS_CATALOGO.get(tipo_puesto, 300.0)
        session.execute(
            db_text("""
            INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada, retencion_nomina, peinado_maquillaje, dulceria)
            VALUES (:fecha, :emp_id, :sueldo, 0.0, 100.0, 0.0, 0.0, FALSE, 0.0, 0.0, 0.0)
            ON CONFLICT DO NOTHING
            """),
            {"fecha": f_date, "emp_id": empleado_id, "sueldo": sueldo_default}
        )

        session.commit()
        return True, estado, hora_actual_obj.strftime('%H:%M:%S'), None
    except Exception as e:
        session.rollback()
        return False, "", "", str(e)
    finally:
        session.close()


def actualizar_estatus_empleado(emp_id: int, activo: bool, actor: str = None):
    """Activa o desactiva a un empleado (baja/alta indefinida, reversible).
    No toca su puesto, sueldo ni ningún registro de nomina_diaria."""
    session = get_session()
    try:
        emp = session.query(Empleado).filter(Empleado.id == emp_id).first()
        if not emp:
            return False
        emp.activo = activo
        session.commit()
        registrar_log(actor or "sistema", "Baja de empleado" if not activo else "Reactivación de empleado", f"empleado={emp.nombre} (id={emp_id})")
        return True
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
                INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada, retencion_nomina, peinado_maquillaje, dulceria)
                SELECT :fecha, a.empleado_id, COALESCE(e.sueldo_base, 300.0), 0.0, 100.0, 0.0, 0.0, FALSE, 0.0, 0.0, 0.0
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
        NominaDiaria.consumo_cocina,
        NominaDiaria.penalizada,
        NominaDiaria.puesto_dia,
        NominaDiaria.retencion_nomina,
        NominaDiaria.peinado_maquillaje,
        NominaDiaria.dulceria
    ).join(NominaDiaria, Empleado.id == NominaDiaria.empleado_id).filter(
        NominaDiaria.fecha == f_date,
        Empleado.activo == True
    ).order_by(Empleado.id)
    
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    
    if not df.empty:
        df['sueldo_base'] = df['sueldo_base'].astype(float)
        df['vales_nomina'] = df['vales_nomina'].astype(float).fillna(0.0) if 'vales_nomina' in df.columns else 0.0
        df['descuento_nomina'] = df['descuento_nomina'].astype(float).fillna(100.0) if 'descuento_nomina' in df.columns else 100.0
        df['transferencia_nomina'] = df['transferencia_nomina'].astype(float).fillna(0.0) if 'transferencia_nomina' in df.columns else 0.0
        df['consumo_cocina'] = df['consumo_cocina'].astype(float).fillna(0.0) if 'consumo_cocina' in df.columns else 0.0
        df['penalizada'] = df['penalizada'].astype(bool) if 'penalizada' in df.columns else False
        df['puesto_dia'] = df['puesto_dia'].fillna("") if 'puesto_dia' in df.columns else ""
        df['tipo_efectivo'] = df['puesto_dia'].where(df['puesto_dia'] != "", df['tipo'])
        df['retencion_nomina'] = df['retencion_nomina'].astype(float).fillna(0.0) if 'retencion_nomina' in df.columns else 0.0
        df['peinado_maquillaje'] = df['peinado_maquillaje'].astype(float).fillna(0.0) if 'peinado_maquillaje' in df.columns else 0.0
        df['dulceria'] = df['dulceria'].astype(float).fillna(0.0) if 'dulceria' in df.columns else 0.0
    return df


def generar_vales_desde_nomina(fecha_str: str):
    """Al cerrar el corte del día, crea en el historial de vales (con folio
    nuevo autogenerado V-0001, V-0002, ...) una fila por cada empleado cuya
    columna 'Vales ($)' de Nómina sea mayor a cero, con el monto que haya
    quedado capturado ahí."""
    fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    session = get_session()
    try:
        nominas = session.query(NominaDiaria).filter(
            NominaDiaria.fecha == fecha, NominaDiaria.vales_nomina > 0
        ).all()
        for nomina in nominas:
            empleado = session.query(Empleado).filter(Empleado.id == nomina.empleado_id).first()
            if not empleado:
                continue

            vale_existente = session.query(ValeDiario).filter(
                ValeDiario.fecha == fecha, ValeDiario.empleado_id == empleado.id
            ).first()
            if vale_existente:
                vale_existente.importe = float(nomina.vales_nomina)
                vale_existente.importe_bruto = float(nomina.vales_nomina)
                continue

            ultimo_folio = session.query(ValeDiario.folio).filter(
                ValeDiario.folio.like("V-%")
            ).order_by(ValeDiario.id.desc()).first()
            siguiente = 1
            if ultimo_folio:
                try:
                    siguiente = int(ultimo_folio[0].split("-")[1]) + 1
                except (IndexError, ValueError):
                    siguiente = session.query(ValeDiario).count() + 1
            folio = f"V-{siguiente:04d}"

            session.add(ValeDiario(
                folio=folio, fecha=fecha, empleado_id=empleado.id, empleado_nombre=empleado.nombre,
                importe=float(nomina.vales_nomina), importe_bruto=float(nomina.vales_nomina),
                abono_boutique=0.0, estado="PENDIENTE", fecha_pago=None,
            ))
            registrar_log("sistema", "Vale generado", f"folio={folio}, empleado={empleado.nombre}, monto=${float(nomina.vales_nomina):.2f}, fecha={fecha_str}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cargar_vales_df(fecha_str: str = None) -> pd.DataFrame:
    session = get_session()
    query = session.query(ValeDiario).order_by(ValeDiario.fecha, ValeDiario.id)
    if fecha_str:
        query = query.filter(ValeDiario.fecha == datetime.strptime(fecha_str, "%Y-%m-%d").date())
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    return df


def actualizar_estado_vale(vale_id: int, estado: str, forma_pago: str = None):
    estados = {"PAGADO", "PENDIENTE", "YA NO PAGAR"}
    if estado not in estados:
        raise ValueError("Estado de vale no válido")
    if forma_pago is not None and not isinstance(forma_pago, str):
        forma_pago = None if pd.isna(forma_pago) else str(forma_pago)
    session = get_session()
    try:
        vale = session.query(ValeDiario).filter(ValeDiario.id == vale_id).first()
        if not vale:
            return False
        forma_pago_efectiva = (forma_pago or vale.forma_pago or "").strip()
        if estado == "PAGADO" and not forma_pago_efectiva:
            raise ValueError(f"El vale {vale.folio} no tiene forma de pago; asígnale una antes de marcarlo como PAGADO.")
        vale.estado = estado
        vale.forma_pago = forma_pago or vale.forma_pago
        vale.fecha_pago = datetime.now().date() if estado == "PAGADO" else None
        session.commit()
        return True
    finally:
        session.close()


def eliminar_vale(vale_id: int, actor: str = None) -> bool:
    session = get_session()
    try:
        vale = session.query(ValeDiario).filter(ValeDiario.id == vale_id).first()
        if not vale:
            return False
        detalle = f"folio={vale.folio}, empleado={vale.empleado_nombre}, monto=${float(vale.importe):.2f}"
        session.delete(vale)
        session.commit()
        registrar_log(actor or "sistema", "Vale eliminado", detalle)
        return True
    finally:
        session.close()


PREFIJOS_CODIGO_BOUTIQUE = {"Zapatillas": "ZAP", "Ropa": "ROP", "Accesorios": "ACC"}


def _generar_codigo_producto_boutique(session, categoria):
    prefijo = PREFIJOS_CODIGO_BOUTIQUE.get(categoria, "PRD")
    ultimo_codigo = session.query(ProductoBoutique.codigo).filter(
        ProductoBoutique.codigo.like(f"{prefijo}-%")
    ).order_by(ProductoBoutique.id.desc()).first()
    siguiente = 1
    if ultimo_codigo and ultimo_codigo[0]:
        try:
            siguiente = int(ultimo_codigo[0].split("-")[1]) + 1
        except (IndexError, ValueError):
            siguiente = session.query(ProductoBoutique).filter(ProductoBoutique.categoria == categoria).count() + 1
    return f"{prefijo}-{siguiente:04d}"


def agregar_producto_boutique(nombre, categoria, talla, precio_venta, stock):
    """Da de alta un producto nuevo en el inventario de la Boutique. El
    código se genera solo por categoría (ZAP-0001, ROP-0001, ACC-0001)."""
    session = get_session()
    try:
        codigo = _generar_codigo_producto_boutique(session, categoria)
        session.add(ProductoBoutique(
            codigo=codigo, nombre=nombre, categoria=categoria, talla=talla,
            precio_venta=precio_venta, stock=stock, activo=True,
        ))
        session.commit()
        return codigo
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def actualizar_producto_boutique(producto_id, nombre, categoria, talla, precio_venta, stock, activo):
    """Edita los datos de un producto de la Boutique (incluido el stock —
    para incrementarlo basta con capturar el nuevo total aquí). El código
    no se toca: es autogenerado y fijo desde el alta."""
    session = get_session()
    try:
        producto = session.query(ProductoBoutique).filter(ProductoBoutique.id == producto_id).first()
        if not producto:
            return False
        producto.nombre = nombre
        producto.categoria = categoria
        producto.talla = talla
        producto.precio_venta = precio_venta
        producto.stock = stock
        producto.activo = activo
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cargar_productos_boutique_df(solo_con_stock: bool = False) -> pd.DataFrame:
    """Catálogo de productos de la Boutique. Con solo_con_stock=True filtra
    a los que tienen stock > 0 (para el selector de 'Registrar venta')."""
    session = get_session()
    query = session.query(ProductoBoutique)
    if solo_con_stock:
        query = query.filter(ProductoBoutique.stock > 0, ProductoBoutique.activo == True)
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    if not df.empty:
        df['precio_venta'] = df['precio_venta'].astype(float)
    return df


def registrar_venta_boutique(empleado_id: int, producto_id: int, cantidad: int, fecha_venta: str = None) -> str:
    """Registra una venta de la Boutique a un empleado: valida stock
    suficiente, descuenta el inventario, calcula el total y genera un folio
    autogenerado B-0001, B-0002, ... — 100% independiente de nómina/vales."""
    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor a cero.")
    fecha = datetime.strptime(fecha_venta, "%Y-%m-%d").date() if fecha_venta else datetime.now().date()
    session = get_session()
    try:
        producto = session.query(ProductoBoutique).filter(ProductoBoutique.id == producto_id).first()
        if not producto:
            raise ValueError("Producto no encontrado.")
        if producto.stock < cantidad:
            raise ValueError(f"Stock insuficiente de '{producto.nombre}' (disponible: {producto.stock}).")
        empleado = session.query(Empleado).filter(Empleado.id == empleado_id).first()
        if not empleado:
            raise ValueError("Empleado no encontrado.")

        ultimo_folio = session.query(VentaBoutique.folio).filter(
            VentaBoutique.folio.like("B-%")
        ).order_by(VentaBoutique.id.desc()).first()
        siguiente = 1
        if ultimo_folio:
            try:
                siguiente = int(ultimo_folio[0].split("-")[1]) + 1
            except (IndexError, ValueError):
                siguiente = session.query(VentaBoutique).count() + 1
        folio = f"B-{siguiente:04d}"

        total = float(producto.precio_venta) * cantidad
        producto.stock -= cantidad
        session.add(VentaBoutique(
            folio=folio, empleado_id=empleado.id, producto_id=producto.id,
            cantidad=cantidad, total=total, fecha_venta=fecha, estatus_pago="Pendiente",
        ))
        session.commit()
        return folio
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cargar_ventas_boutique_df(empleado_id: int = None) -> pd.DataFrame:
    """Historial de compras de la Boutique (puede haber varias por
    empleado), con nombre de empleado y producto ya resueltos."""
    session = get_session()
    query = session.query(
        VentaBoutique.id, VentaBoutique.folio, VentaBoutique.empleado_id,
        Empleado.nombre.label("empleado_nombre"),
        VentaBoutique.producto_id, ProductoBoutique.nombre.label("producto_nombre"),
        VentaBoutique.cantidad, VentaBoutique.total, VentaBoutique.fecha_venta,
    ).join(Empleado, Empleado.id == VentaBoutique.empleado_id).join(
        ProductoBoutique, ProductoBoutique.id == VentaBoutique.producto_id
    )
    if empleado_id is not None:
        query = query.filter(VentaBoutique.empleado_id == empleado_id)
    query = query.order_by(VentaBoutique.fecha_venta.desc(), VentaBoutique.id.desc())
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    if not df.empty:
        df['total'] = df['total'].astype(float)
    return df


def cargar_saldos_boutique_df() -> pd.DataFrame:
    """Saldo general de Boutique por empleado: total comprado (todas sus
    ventas), total abonado (todos sus abonos) y saldo pendiente — sin ligar
    el pago a una venta/folio en particular. Solo incluye empleados con al
    menos una compra."""
    session = get_session()
    comprado = dict(
        session.query(VentaBoutique.empleado_id, func.sum(VentaBoutique.total))
        .group_by(VentaBoutique.empleado_id).all()
    )
    abonado = dict(
        session.query(AbonoBoutique.empleado_id, func.sum(AbonoBoutique.monto))
        .group_by(AbonoBoutique.empleado_id).all()
    )
    empleados = session.query(Empleado.id, Empleado.nombre).filter(Empleado.id.in_(comprado.keys())).all()
    session.close()

    filas = []
    for emp_id, nombre in empleados:
        total_comprado = float(comprado.get(emp_id, 0) or 0)
        total_abonado = float(abonado.get(emp_id, 0) or 0)
        filas.append({
            "empleado_id": emp_id, "empleado_nombre": nombre,
            "total_comprado": total_comprado, "total_abonado": total_abonado,
            "saldo_pendiente": total_comprado - total_abonado,
        })
    df = pd.DataFrame(filas, columns=["empleado_id", "empleado_nombre", "total_comprado", "total_abonado", "saldo_pendiente"])
    if not df.empty:
        df = df.sort_values("empleado_nombre").reset_index(drop=True)
    return df


def registrar_abono_boutique(empleado_id: int, monto: float, metodo_pago: str):
    """Registra un abono de un empleado hacia su saldo general de Boutique.
    La fecha de pago se fija sola (hoy), no se captura a mano."""
    metodos = {"Efectivo", "Transferencia"}
    if metodo_pago not in metodos:
        raise ValueError("Debes indicar un método de pago (Efectivo o Transferencia).")
    if monto is None or monto <= 0:
        raise ValueError("El monto del abono debe ser mayor a cero.")
    session = get_session()
    try:
        empleado = session.query(Empleado).filter(Empleado.id == empleado_id).first()
        if not empleado:
            raise ValueError("Empleado no encontrado.")
        session.add(AbonoBoutique(
            empleado_id=empleado_id, monto=monto, metodo_pago=metodo_pago,
            fecha_pago=datetime.now().date(),
        ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cargar_abonos_boutique_df(empleado_id: int = None) -> pd.DataFrame:
    """Historial de abonos de Boutique, con nombre de empleado resuelto."""
    session = get_session()
    query = session.query(
        AbonoBoutique.id, AbonoBoutique.empleado_id, Empleado.nombre.label("empleado_nombre"),
        AbonoBoutique.monto, AbonoBoutique.metodo_pago, AbonoBoutique.fecha_pago,
    ).join(Empleado, Empleado.id == AbonoBoutique.empleado_id)
    if empleado_id is not None:
        query = query.filter(AbonoBoutique.empleado_id == empleado_id)
    query = query.order_by(AbonoBoutique.fecha_pago.desc(), AbonoBoutique.id.desc())
    df = pd.read_sql(query.statement, session.bind)
    session.close()
    if not df.empty:
        df['monto'] = df['monto'].astype(float)
    return df


def agregar_empleado_catalogo(nombre, tipo, sueldo_base, pin=None, fecha_str=None, actor=None):
    """Da de alta o actualiza un empleado SOLO en el catálogo (tabla
    empleados) — NO crea registros nuevos de nomina_diaria.
    Devuelve el id del empleado (nuevo o existente).

    Se usa para altas individuales sueltas. Para importar varios
    empleados de un Excel a la vez, usar agregar_empleados_catalogo_bulk
    (una sola conexión para todo el archivo, mucho más rápida).

    Si el empleado YA existía (se está reactivando o volviendo a subir),
    se limpian los montos de nómina que pudiera tener de antes para la
    fecha activa (vales, descuentos, consumos, etc.) — de lo contrario
    un vale o descuento capturado en el pasado reaparecería tal cual
    "solo", sin que nadie lo haya vuelto a teclear."""
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

            f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
            f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
            nom = session.query(NominaDiaria).filter(
                NominaDiaria.fecha == f_date, NominaDiaria.empleado_id == emp.id
            ).first()
            if nom:
                nom.vales_nomina = 0.0
                nom.descuento_nomina = 100.0
                nom.transferencia_nomina = 0.0
                nom.consumo_cocina = 0.0
                nom.retencion_nomina = 0.0
                nom.peinado_maquillaje = 0.0
                nom.dulceria = 0.0
                nom.penalizada = False
                nom.sueldo_base = sueldo_base

            session.commit()
            registrar_log(actor or "sistema", "Alta de empleado (reactivación)", f"empleado={emp.nombre}")
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
            registrar_log(actor or "sistema", "Alta de empleado", f"empleado={emp.nombre}, puesto={tipo}")
            return emp.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def agregar_empleados_catalogo_bulk(filas: list, fecha_str: str = None, actor: str = None) -> list:
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

    Si un nombre subido ya existía (reactivación, o el mismo Excel se
    vuelve a importar), se limpian los montos de nómina de la fecha
    activa que pudiera tener de antes (vales, descuentos, consumos,
    etc.) — igual que en agregar_empleado_catalogo, para que no
    reaparezcan vales o descuentos viejos sin que nadie los haya vuelto
    a capturar."""
    if not filas:
        return []
    session = get_session()
    try:
        asegurar_columnas_empleado(session)
        # Solo se asegura cada puesto distinto una vez, no por fila.
        puestos_unicos = {f['tipo'] for f in filas}
        for puesto in puestos_unicos:
            asegurar_puesto_existe(session, puesto)

        f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
        f_date = datetime.strptime(f_str, "%Y-%m-%d").date()

        nombres_norm = [normalizar_nombre(f['nombre']) for f in filas]
        existentes = session.query(Empleado).filter(Empleado.nombre.in_(nombres_norm)).all()
        mapa_existentes = {e.nombre: e for e in existentes}

        nominas_existentes = session.query(NominaDiaria).filter(
            NominaDiaria.fecha == f_date,
            NominaDiaria.empleado_id.in_([e.id for e in existentes])
        ).all() if existentes else []
        mapa_nominas = {n.empleado_id: n for n in nominas_existentes}

        ids_resultado = []
        reactivados = []
        nuevos = []
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

                nom = mapa_nominas.get(emp.id)
                if nom:
                    nom.vales_nomina = 0.0
                    nom.descuento_nomina = 100.0
                    nom.transferencia_nomina = 0.0
                    nom.consumo_cocina = 0.0
                    nom.retencion_nomina = 0.0
                    nom.peinado_maquillaje = 0.0
                    nom.dulceria = 0.0
                    nom.penalizada = False
                    nom.sueldo_base = f['sueldo_base']
                reactivados.append(nombre_norm)
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
                nuevos.append(nombre_norm)
            ids_resultado.append(emp.id)

        session.commit()
        registrar_log(
            actor or "sistema", "Alta masiva de empleados",
            f"nuevos={len(nuevos)}, reactivados={len(reactivados)}" + (f" ({', '.join(reactivados)})" if reactivados else "")
        )
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
                    INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada, retencion_nomina, peinado_maquillaje, dulceria)
                    VALUES (:fecha, :emp_id, :sueldo, 0.0, 100.0, 0.0, 0.0, FALSE, 0.0, 0.0, 0.0)
                    ON CONFLICT (empleado_id, fecha) DO NOTHING
                """),
                {"fecha": f_date, "emp_id": emp_id, "sueldo": float(sueldo_emp) if sueldo_emp is not None else 300.0}
            )
            # Si la fila de nómina de este día YA existía (por ejemplo, se
            # creó antes con el sueldo por defecto al subir el corte de
            # ventas/comisiones, antes de procesar el Alta Masiva con el
            # sueldo real), el INSERT de arriba no la toca por el
            # ON CONFLICT DO NOTHING. Este UPDATE la sincroniza con el
            # sueldo actual del catálogo, sin importar el orden en que se
            # hayan subido los archivos — y sin tocar vales/descuento/
            # transferencia/penalizada que ya se hayan capturado ese día.
            session.execute(
                db_text("""
                    UPDATE nomina_diaria
                    SET sueldo_base = :sueldo
                    WHERE empleado_id = :emp_id AND fecha = :fecha
                """),
                {"sueldo": float(sueldo_emp) if sueldo_emp is not None else 300.0, "emp_id": emp_id, "fecha": f_date}
            )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error al registrar asistencia por lista de empleados: {e}")
    finally:
        session.close()


def agregar_empleado(nombre, tipo, sueldo_base, fecha_str=None, pin=None, actor=None, **kwargs):
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
                consumo_cocina=0.0,
                penalizada=False
            ))
        else:
            existe_nom.sueldo_base = sueldo_base

        session.commit()
        registrar_log(actor or "sistema", "Alta de empleado", f"empleado={normalizar_nombre(nombre)}, puesto={tipo}")
        return emp.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def actualizar_empleado(emp_id, nuevo_tipo, nuevo_sueldo, nuevo_vales=None, nueva_penalizacion=None, nuevo_descuento=None, nueva_transferencia=None, nuevo_consumo_cocina=None, fecha_str=None, nuevo_puesto_dia=None, nuevo_retencion=None, nuevo_peinado_maquillaje=None, nuevo_dulceria=None, actor=None, **kwargs):
    session = get_session()
    asegurar_puesto_existe(session, nuevo_tipo)

    emp = session.query(Empleado).filter(Empleado.id == emp_id).first()
    tipo_anterior = emp.tipo if emp else None
    cambio_de_puesto = bool(emp) and tipo_anterior != nuevo_tipo
    if emp:
        emp.tipo = nuevo_tipo
        emp.sueldo_base = nuevo_sueldo

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

    if cambio_de_puesto:
        # El puesto cambió: los montos de nómina del día (vales, descuentos,
        # consumos, etc.) pertenecían al puesto anterior y no deben
        # arrastrarse al nuevo puesto.
        nom.vales_nomina = 0.0
        nom.descuento_nomina = 100.0
        nom.transferencia_nomina = 0.0
        nom.consumo_cocina = 0.0
        nom.retencion_nomina = 0.0
        nom.peinado_maquillaje = 0.0
        nom.dulceria = 0.0
        nom.penalizada = False
        nom.puesto_dia = nuevo_tipo

    if nuevo_vales is not None:
        nom.vales_nomina = nuevo_vales
    if nueva_penalizacion is not None:
        nom.penalizada = nueva_penalizacion
    if nuevo_descuento is not None:
        nom.descuento_nomina = nuevo_descuento
    if nueva_transferencia is not None:
        nom.transferencia_nomina = nueva_transferencia
    if nuevo_consumo_cocina is not None:
        nom.consumo_cocina = nuevo_consumo_cocina
    if nuevo_puesto_dia is not None:
        nom.puesto_dia = nuevo_puesto_dia
    if nuevo_retencion is not None:
        nom.retencion_nomina = nuevo_retencion
    if nuevo_peinado_maquillaje is not None:
        nom.peinado_maquillaje = nuevo_peinado_maquillaje
    if nuevo_dulceria is not None:
        nom.dulceria = nuevo_dulceria

    nombre_emp = emp.nombre if emp else str(emp_id)
    session.commit()
    session.close()

    if cambio_de_puesto:
        registrar_log(actor or "sistema", "Cambio de puesto", f"empleado={nombre_emp}: {tipo_anterior} -> {nuevo_tipo}, sueldo=${nuevo_sueldo:.2f}")


def eliminar_empleado_por_id(emp_id, fecha_str):
    """Quita a un empleado de la nómina/asistencia de UNA fecha
    específica (botón "Quitar de nómina de hoy" en Nómina del día) —
    NUNCA borra su registro de la tabla `empleados`. Para dar de baja a
    un empleado de verdad, usar el checkbox "Activo" en
    '2. Gestión de Empleados' (actualizar_estatus_empleado)."""
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()

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
                consumo_cocina=0.0,
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


def guardar_fondo_apertura(fecha_str: str, monto: float):
    session = get_session()
    f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    fila = session.query(GastoDiario).filter(GastoDiario.fecha == f_date).first()
    if fila:
        fila.fondo_apertura = monto
    else:
        session.add(GastoDiario(fecha=f_date, fondo_apertura=monto))
    session.commit()
    session.close()


def guardar_monto_cierre(fecha_str: str, monto: float):
    session = get_session()
    f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    fila = session.query(GastoDiario).filter(GastoDiario.fecha == f_date).first()
    if fila:
        fila.monto_cierre = monto
    else:
        session.add(GastoDiario(fecha=f_date, monto_cierre=monto))
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


def sumar_consumo_cocina_dia(fecha_str: str = None) -> float:
    """Suma el consumo de cocina/comedor de TODOS los empleados (columna
    'consumo_cocina' de nomina_diaria) para una fecha dada. Es la fuente
    única de verdad de ese total: la usan tanto el Dashboard (Sección 4,
    campo 'Gastos - Cocina') como la sección de Pagos y Comedor, para que
    nunca queden desincronizados entre sí."""
    session = get_session()
    try:
        f_str = fecha_str if fecha_str else datetime.now().strftime('%Y-%m-%d')
        f_date = datetime.strptime(f_str, "%Y-%m-%d").date()
        total = session.query(func.sum(NominaDiaria.consumo_cocina)).filter(
            NominaDiaria.fecha == f_date
        ).scalar()
        return float(total) if total is not None else 0.0
    finally:
        session.close()


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
                INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada, retencion_nomina, peinado_maquillaje, dulceria)
                SELECT DISTINCT a.fecha, a.empleado_id, COALESCE(e.sueldo_base, 300.0), 0.0, 100.0, 0.0, 0.0, FALSE, 0.0, 0.0, 0.0
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


def exportar_base_datos_excel() -> io.BytesIO:
    """Exporta TODAS las tablas del sistema a un solo archivo Excel (una
    hoja por tabla). Pensado como respaldo completo antes de un
    'Reiniciar Base de Datos' — luego se puede restaurar con
    importar_base_datos_excel()."""
    session = get_session()
    try:
        tablas = {
            'puestos_catalogo': PuestoCatalogo,
            'usuarios_sistema': UsuarioSistema,
            'empleados': Empleado,
            'nomina_diaria': NominaDiaria,
            'asistencias': Asistencia,
            'cortes_ventas': CorteVenta,
            'cortes_productos_chicas': ProductoChica,
            'gastos_diarios': GastoDiario,
            'cortes_bloqueos': CorteBloqueo,
        }
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for nombre_hoja, modelo in tablas.items():
                query = session.query(modelo)
                df = pd.read_sql(query.statement, session.bind)
                df.to_excel(writer, index=False, sheet_name=nombre_hoja[:31])
        buffer.seek(0)
        return buffer
    finally:
        session.close()


def _normalizar_fechas_para_importar(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte columnas de fecha (leídas de Excel como Timestamp) al
    tipo date de Python, que es lo que esperan las columnas Date."""
    for col in ('fecha', 'fecha_bloqueo'):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    return df


def importar_base_datos_excel(archivo) -> dict:
    """Restaura TODAS las tablas desde un archivo generado por
    exportar_base_datos_excel(). REEMPLAZA el contenido actual de cada
    tabla (se vacía todo primero), conservando los IDs originales del
    archivo para que las relaciones (empleado_id, idmesero, etc.) sigan
    apuntando a quien corresponde, y al final reinicia los contadores
    de autoincremento para que los próximos registros nuevos no choquen
    con los ids restaurados.

    Devuelve un dict {nombre_tabla: filas_importadas}."""
    session = get_session()
    resultado = {}
    try:
        # (nombre_hoja, modelo, columna_id_autoincrement_o_None)
        orden_tablas = [
            ('puestos_catalogo', PuestoCatalogo, None),
            ('usuarios_sistema', UsuarioSistema, 'id'),
            ('empleados', Empleado, 'id'),
            ('nomina_diaria', NominaDiaria, 'id'),
            ('asistencias', Asistencia, 'id'),
            ('cortes_ventas', CorteVenta, 'id'),
            ('cortes_productos_chicas', ProductoChica, 'id'),
            ('gastos_diarios', GastoDiario, 'id'),
            ('cortes_bloqueos', CorteBloqueo, 'id'),
        ]

        xls = pd.ExcelFile(archivo)

        # Se vacía todo (en cascada, por las relaciones) antes de recargar.
        # TRUNCATE ... RESTART IDENTITY CASCADE es sintaxis de PostgreSQL;
        # SQLite (la app de escritorio) no la soporta, así que ahí se
        # vacía tabla por tabla con DELETE.
        tablas_para_vaciar = (
            "cortes_productos_chicas", "cortes_ventas", "nomina_diaria",
            "asistencias", "cortes_bloqueos", "gastos_diarios",
            "empleados", "puestos_catalogo", "usuarios_sistema",
        )
        if session.bind.dialect.name == "postgresql":
            session.execute(db_text(
                "TRUNCATE TABLE " + ", ".join(tablas_para_vaciar) + " RESTART IDENTITY CASCADE"
            ))
        else:
            for tabla in tablas_para_vaciar:
                session.execute(db_text(f"DELETE FROM {tabla}"))
        session.commit()

        for nombre_hoja, modelo, col_id in orden_tablas:
            if nombre_hoja not in xls.sheet_names:
                resultado[nombre_hoja] = 0
                continue

            df = pd.read_excel(xls, sheet_name=nombre_hoja)
            if df.empty:
                resultado[nombre_hoja] = 0
                continue

            df = _normalizar_fechas_para_importar(df)

            registros = df.to_dict(orient='records')
            # NaN -> None DESPUÉS de convertir a diccionarios: un DataFrame
            # numérico no puede contener None (pandas lo revierte a NaN),
            # pero un diccionario de Python sí, y eso es lo que necesita
            # SQLAlchemy para insertar NULL correctamente.
            registros = [
                {k: (None if (v is not None and pd.isna(v)) else v) for k, v in fila.items()}
                for fila in registros
            ]
            session.bulk_insert_mappings(modelo, registros)
            session.commit()
            resultado[nombre_hoja] = len(registros)

        # Reinicia cada secuencia de autoincremento al máximo id restaurado.
        # setval/pg_get_serial_sequence son de PostgreSQL; en SQLite (app de
        # escritorio) no hace falta -- ahí el próximo id autogenerado ya se
        # calcula solo como max(id)+1 de los datos reales, sin secuencia
        # aparte que resincronizar.
        if session.bind.dialect.name == "postgresql":
            for nombre_hoja, modelo, col_id in orden_tablas:
                if col_id:
                    session.execute(db_text(
                        f"SELECT setval(pg_get_serial_sequence('{nombre_hoja}', '{col_id}'), "
                        f"COALESCE((SELECT MAX({col_id}) FROM {nombre_hoja}), 1), true)"
                    ))
        session.commit()

        return resultado
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def eliminar_datos_boutique():
    session = get_session()
    try:
        session.query(AbonoBoutique).delete()
        session.query(VentaBoutique).delete()
        session.query(ProductoBoutique).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def reiniciar_base_de_datos(actor: str = None):
    session = get_session()
    try:
        session.commit()
        # CASCADE es sintaxis de PostgreSQL; SQLite (la app de escritorio)
        # no la soporta y no la necesita, ya que no aplica llaves foráneas
        # por defecto -- se agrega solo cuando el motor es Postgres.
        sufijo_cascade = " CASCADE" if session.bind.dialect.name == "postgresql" else ""
        for tabla in (
            "asistencias", "cortes_bloqueos", "nomina_diaria", "cortes_productos_chicas",
            "cortes_ventas", "gastos_diarios", "empleados", "puestos_catalogo", "usuarios_sistema",
            "vales_diarios", "carnet_sanidad", "productos_boutique", "ventas_boutique", "abonos_boutique",
            # "log_movimientos" se deja fuera a propósito: es la bitácora de
            # auditoría, no debe borrarse ni con el propio reinicio que la
            # registra (ver registrar_log(...) al final de esta función).
        ):
            session.execute(db_text(f"DROP TABLE IF EXISTS {tabla}{sufijo_cascade};"))
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
        registrar_log(actor or "sistema", "Reinicio de base de datos", "Se borraron todas las tablas de datos del sistema.")
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
    asegurar_columnas_gasto(_session_auto)
    asegurar_columnas_empleado(_session_auto)
    _session_auto.close()
    inicializar_usuarios_por_defecto()
except Exception as _err_inicial:
    # No se traga el error: se deja constancia visible en consola/logs.
    # Si la BD no está disponible al arrancar, es mejor saberlo de inmediato
    # que descubrirlo más tarde con fallas difíciles de rastrear.
    print(f"[models.py] ADVERTENCIA: no se pudo inicializar la conexión/tablas al arrancar: {_err_inicial}")