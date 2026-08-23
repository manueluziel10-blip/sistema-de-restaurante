import sqlite3
import pandas as pd

DB_NAME = "restaurante.db"

def inicializar_base_datos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabla de empleados con soporte para vales, penalización, descuento y transferencia
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            sueldo_base REAL DEFAULT 0.0,
            vales_nomina REAL DEFAULT 0.0,
            penalizada BOOLEAN DEFAULT 0,
            descuento_nomina REAL DEFAULT 100.0,
            transferencia_nomina REAL DEFAULT 0.0
        )
    ''')
    
    # Tabla de ventas de meseros
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ventas_meseros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idmesero INTEGER,
            efectivo REAL DEFAULT 0.0,
            propina_efectivo REAL DEFAULT 0.0,
            tarjeta REAL DEFAULT 0.0,
            propina_tarjeta REAL DEFAULT 0.0,
            vales REAL DEFAULT 0.0,
            propina_vales REAL DEFAULT 0.0,
            otros REAL DEFAULT 0.0,
            propinacredito REAL DEFAULT 0.0,
            archivo_origen TEXT
        )
    ''')

    # Tabla de productos de chicas / bailarinas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS productos_chicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER,
            clave TEXT,
            descripcion TEXT,
            grupo TEXT,
            precio REAL,
            cantidad REAL,
            comision_unitaria REAL,
            archivo_origen TEXT,
            FOREIGN KEY (empleado_id) REFERENCES empleados (id)
        )
    ''')

    # Tabla de gastos diarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_diarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gasto_cocina REAL DEFAULT 0.0,
            gasto_compras REAL DEFAULT 0.0,
            gasto_vales REAL DEFAULT 0.0,
            fecha TEXT
        )
    ''')

    conn.commit()
    conn.close()

# Asegurar que la BD y columnas existan al importar
inicializar_base_datos()

def cargar_empleados_df():
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query("SELECT * FROM empleados", conn)
        # Migración automática si faltan columnas nuevas en bases de datos existentes
        if 'transferencia_nomina' not in df.columns:
            conn.execute("ALTER TABLE empleados ADD COLUMN transferencia_nomina REAL DEFAULT 0.0")
            conn.commit()
            df = pd.read_sql_query("SELECT * FROM empleados", conn)
        return df
    except Exception:
        return pd.DataFrame(columns=['id', 'nombre', 'tipo', 'sueldo_base', 'vales_nomina', 'penalizada', 'descuento_nomina', 'transferencia_nomina'])
    finally:
        conn.close()

def agregar_empleado(nombre, tipo, sueldo_base):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO empleados (nombre, tipo, sueldo_base, vales_nomina, penalizada, descuento_nomina, transferencia_nomina)
            VALUES (?, ?, ?, 0.0, 0, 100.0, 0.0)
        ''', (nombre.strip().upper(), tipo, sueldo_base))
        conn.commit()
    finally:
        conn.close()

def actualizar_empleado(empleado_id, tipo, sueldo_base, vales_nomina=0.0, penalizada=False, descuento_nomina=100.0, transferencia_nomina=0.0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE empleados 
            SET tipo = ?, sueldo_base = ?, vales_nomina = ?, penalizada = ?, descuento_nomina = ?, transferencia_nomina = ?
            WHERE id = ?
        ''', (tipo, sueldo_base, vales_nomina, int(penalizada), descuento_nomina, transferencia_nomina, empleado_id))
        conn.commit()
    finally:
        conn.close()

def guardar_corte_ventas(df_v, df_p, archivo_origen):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ventas_meseros")
        
        for _, row in df_v.iterrows():
            idmesero = int(row.get('idmesero', 0))
            efectivo = float(row.get('efectivo', 0.0))
            tarjeta = float(row.get('tarjeta', 0.0))
            vales = float(row.get('vales', 0.0))
            otros = float(row.get('otros', 0.0))
            
            # Buscar propinas correspondientes del otro dataframe si existen
            prop_efec, prop_tarj, prop_vale, prop_cred = 0.0, 0.0, 0.0, 0.0
            if not df_p.empty and 'idmesero' in df_p.columns:
                match = df_p[df_p['idmesero'] == idmesero]
                if not match.empty:
                    m_row = match.iloc[0]
                    prop_efec = float(m_row.get('propina_efectivo', 0.0))
                    prop_tarj = float(m_row.get('propina_tarjeta', 0.0))
                    prop_vale = float(m_row.get('propina_vales', 0.0))
                    prop_cred = float(m_row.get('propinacredito', 0.0))

            cursor.execute('''
                INSERT INTO ventas_meseros (idmesero, efectivo, propina_efectivo, tarjeta, propina_tarjeta, vales, propina_vales, otros, propinacredito, archivo_origen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (idmesero, efectivo, prop_efec, tarjeta, prop_tarj, vales, prop_vale, otros, prop_cred, archivo_origen))
        
        conn.commit()
    finally:
        conn.close()

def guardar_corte_chicas(filas_chicas, funcion_comision, archivo_origen):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    empleados_actuales = cargar_empleados_df()
    nombres_registrados = empleados_actuales['nombre'].tolist() if not empleados_actuales.empty else []
    
    nuevas_detectadas = set()
    try:
        cursor.execute("DELETE FROM productos_chicas")
        
        for _, row in filas_chicas.iterrows():
            desc_completa = str(row['DESCRIPCION']).strip()
            if '>' in desc_completa:
                partes = desc_completa.split('>', 1)
                nombre_chica = partes[0].strip().upper()
                nombre_prod = partes[1].strip()
            else:
                continue

            cantidad = float(row['CANTIDAD']) if pd.notna(row['CANTIDAD']) else 0.0
            comision_unit = funcion_comision(nombre_prod)

            # Registrar automáticamente si la chica no existe en el catálogo
            if nombre_chica not in nombres_registrados and nombre_chica not in nuevas_detectadas:
                cursor.execute('''
                    INSERT INTO empleados (nombre, tipo, sueldo_base, vales_nomina, penalizada, descuento_nomina, transferencia_nomina)
                    VALUES (?, 'Chicas / Bailarinas (Comisiones)', 300.0, 0.0, 0, 100.0, 0.0)
                ''', (nombre_chica,))
                conn.commit()
                nuevas_detectadas.add(nombre_chica)
                nombres_registrados.append(nombre_chica)

            # Obtener ID del empleado
            cursor.execute("SELECT id FROM empleados WHERE nombre = ?", (nombre_chica,))
            res_id = cursor.fetchone()
            emp_id = res_id[0] if res_id else None

            if emp_id:
                cursor.execute('''
                    INSERT INTO productos_chicas (empleado_id, clave, descripcion, grupo, precio, cantidad, comision_unitaria, archivo_origen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (emp_id, str(row.get('CLAVE', '')), nombre_prod, str(row.get('GRUPO', '')), float(row.get('PRECIO', 0.0)), cantidad, comision_unit, archivo_origen))

        conn.commit()
    finally:
        conn.close()
    return nuevas_detectadas

def cargar_ventas_df():
    conn = sqlite3.connect(DB_NAME)
    try:
        return pd.read_sql_query("SELECT * FROM ventas_meseros", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

def cargar_chicas_df():
    conn = sqlite3.connect(DB_NAME)
    try:
        return pd.read_sql_query("SELECT * FROM productos_chicas", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

def guardar_gastos_del_dia(cocina, compras, vales):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    fecha_hoy = pd.Timestamp.now().strftime('%Y-%m-%d')
    try:
        cursor.execute("DELETE FROM gastos_diarios")
        cursor.execute('''
            INSERT INTO gastos_diarios (gasto_cocina, gasto_compras, gasto_vales, fecha)
            VALUES (?, ?, ?, ?)
        ''', (cocina, compras, vales, fecha_hoy))
        conn.commit()
    finally:
        conn.close()

def cargar_gastos_hoy():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT gasto_cocina, gasto_compras, gasto_vales FROM gastos_diarios ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            class Gastos:
                def __init__(self, c, comp, v):
                    self.gasto_cocina = c
                    self.gasto_compras = comp
                    self.gasto_vales = v
            return Gastos(row[0], row[1], row[2])
        return None
    except Exception:
        return None
    finally:
        conn.close()

def reiniciar_base_de_datos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS empleados")
        cursor.execute("DROP TABLE IF EXISTS ventas_meseros")
        cursor.execute("DROP TABLE IF EXISTS productos_chicas")
        cursor.execute("DROP TABLE IF EXISTS gastos_diarios")
        conn.commit()
    finally:
        conn.close()
    inicializar_base_datos()