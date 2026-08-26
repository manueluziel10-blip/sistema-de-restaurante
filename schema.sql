-- =========================================================
-- ESQUEMA: Sistema de Nómina, Ventas y Cierre de Caja
-- Motor: PostgreSQL
-- =========================================================

-- Catálogo de puestos (reemplaza el diccionario PUESTOS_CATALOGO)
CREATE TABLE IF NOT EXISTS puestos_catalogo (
    nombre           TEXT PRIMARY KEY,
    sueldo_base      NUMERIC(10,2) NOT NULL,
    es_comision      BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO puestos_catalogo (nombre, sueldo_base, es_comision) VALUES
    ('Chicas / Bailarinas (Comisiones)', 300.00, TRUE),
    ('Mesero (Comisiones)',              300.00, TRUE),
    ('Seguridad (Fijo)',                 500.00, FALSE),
    ('DJ (Fijo)',                        600.00, FALSE),
    ('Animador (Fijo)',                  400.00, FALSE),
    ('Gerente (Fijo)',                   500.00, FALSE),
    ('Capitán de Mesero (Fijo)',         400.00, FALSE),
    ('Ayudante de Mesero (Fijo)',        300.00, FALSE)
ON CONFLICT (nombre) DO NOTHING;

-- Empleados
CREATE TABLE IF NOT EXISTS empleados (
    id               SERIAL PRIMARY KEY,
    nombre           TEXT NOT NULL UNIQUE,
    tipo             TEXT NOT NULL REFERENCES puestos_catalogo(nombre),
    sueldo_base      NUMERIC(10,2) NOT NULL,
    activo           BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cortes de ventas de meseros (ventasmeseros.xls)
CREATE TABLE IF NOT EXISTS cortes_ventas (
    id               SERIAL PRIMARY KEY,
    fecha            DATE NOT NULL DEFAULT CURRENT_DATE,
    idmesero         INTEGER REFERENCES empleados(id),
    importe          NUMERIC(10,2) DEFAULT 0,
    efectivo         NUMERIC(10,2) DEFAULT 0,
    tarjeta          NUMERIC(10,2) DEFAULT 0,
    propina          NUMERIC(10,2) DEFAULT 0,
    penalizado       BOOLEAN DEFAULT FALSE,
    archivo_origen   TEXT,
    cargado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Productos vendidos por chicas/bailarinas (PRODUCTOSVENDIDOSPERIODO.XLS)
CREATE TABLE IF NOT EXISTS cortes_productos_chicas (
    id                  SERIAL PRIMARY KEY,
    fecha               DATE NOT NULL DEFAULT CURRENT_DATE,
    clave               TEXT,
    descripcion         TEXT NOT NULL,
    grupo               TEXT,
    precio              NUMERIC(10,2),
    cantidad            NUMERIC(10,2) DEFAULT 1,
    empleado_nombre     TEXT NOT NULL,
    empleado_id         INTEGER REFERENCES empleados(id),
    comision_unitaria   NUMERIC(10,2) DEFAULT 0,
    comision_total      NUMERIC(10,2) GENERATED ALWAYS AS (comision_unitaria * cantidad) STORED,
    penalizada          BOOLEAN DEFAULT FALSE,
    archivo_origen      TEXT,
    cargado_en          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Gastos y cierre diario
CREATE TABLE IF NOT EXISTS gastos_diarios (
    id                      SERIAL PRIMARY KEY,
    fecha                   DATE NOT NULL UNIQUE DEFAULT CURRENT_DATE,
    gasto_cocina            NUMERIC(10,2) DEFAULT 0,
    gasto_compras           NUMERIC(10,2) DEFAULT 0,
    gasto_vales             NUMERIC(10,2) DEFAULT 0,
    nomina_personal_fijo    NUMERIC(10,2) DEFAULT 4483.66,
    notas                   TEXT,
    creado_en               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vales diarios importados desde "Registro de Pagos".
CREATE TABLE IF NOT EXISTS vales_diarios (
    id               SERIAL PRIMARY KEY,
    folio            TEXT NOT NULL UNIQUE,
    fecha            DATE NOT NULL,
    empleado_id      INTEGER NOT NULL REFERENCES empleados(id),
    empleado_nombre  TEXT NOT NULL,
    importe          NUMERIC(10,2) NOT NULL DEFAULT 0,
    importe_bruto    NUMERIC(10,2) NOT NULL DEFAULT 0,
    abono_boutique   NUMERIC(10,2) NOT NULL DEFAULT 0,
    estado           TEXT NOT NULL DEFAULT 'PENDIENTE',
    forma_pago       TEXT,
    fecha_pago       DATE,
    archivo_origen   TEXT,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_vale_estado CHECK (estado IN ('PAGADO', 'PENDIENTE', 'YA NO PAGAR'))
);

-- Índices útiles para las consultas del dashboard y nómina semanal
CREATE INDEX IF NOT EXISTS idx_cortes_ventas_fecha ON cortes_ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_cortes_ventas_idmesero ON cortes_ventas(idmesero);
CREATE INDEX IF NOT EXISTS idx_cortes_chicas_fecha ON cortes_productos_chicas(fecha);
CREATE INDEX IF NOT EXISTS idx_cortes_chicas_empleado ON cortes_productos_chicas(empleado_id);
CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos_diarios(fecha);
CREATE INDEX IF NOT EXISTS idx_vales_fecha ON vales_diarios(fecha);
CREATE INDEX IF NOT EXISTS idx_vales_empleado ON vales_diarios(empleado_id);
