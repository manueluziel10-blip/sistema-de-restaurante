"""
Módulo único de reglas de comisiones — fuente de verdad para el cálculo
de comisiones de bailarinas/chicas y del bono de gerencia/caja.

IMPORTANTE: si cambias un precio de comisión, cámbialo SOLO aquí.
Tanto el corte diario (app.py -> procesar_grupo_chicas) como el reporte
por periodo (app.py -> Sección 5. Reportes) importan estas funciones,
así que un cambio aquí se refleja automáticamente en ambos lugares y
ya no hace falta actualizar la misma tabla de precios en dos sitios.
"""

import pandas as pd

# Tabla de comisiones por producto vendido por una chica/bailarina.
# El orden importa: se evalúa de arriba hacia abajo y se usa la
# PRIMERA coincidencia (por eso "PRIVADO ARTISTA" va antes que "PRIVADO"
# a secas, y "BOONS ARTISTA" antes que "BOONS").
# Formato: (subcadena a buscar en la descripción, comisión unitaria, categoría del desglose)
TABLA_COMISIONES_CHICAS = [
    ("PRIVADO PROMO",   80.0,   "Privados Promo"),
    ("PRIVADO ARTISTA", 300.0,  "VIP 5 / Priv / Artista"),
    ("BOONS ARTISTA",   1000.0, "Boons"),
    ("BOONS",           700.0,  "Boons"),
    ("COPA LADY",       100.0,  "Copa Lady"),
    ("MINI STRONGBOW",  250.0,  "Strongbow"),
    ("VIP30",           1900.0, "VIP 30"),
    ("VIP 15",          1000.0, "VIP 15"),
    ("VIP15",           1000.0, "VIP 15"),
    ("VIP5",            100.0,  "VIP 5 / Priv / Artista"),
    ("PRIVADO",         100.0,  "VIP 5 / Priv / Artista"),
    ("VIP3",            50.0,   "VIP 3"),
]

# Categorías del desglose, en el orden en que se muestran las columnas.
CATEGORIAS_CHICAS = [
    "Boons", "Copa Lady", "Strongbow", "VIP 3",
    "Privados Promo", "VIP 5 / Priv / Artista", "VIP 15", "VIP 30",
]

# Bono de gerencia/caja (Gerente, Capitán de Mesero, Cajero) por producto vendido.
# Se paga sobre el total de productos vendidos en el bar (no por chica
# individual), a diferencia de calcular_comision_chica.
TABLA_COMISION_GERENCIA_CAJA = [
    ("MOET IMPERIAL",  170.0),
    ("VINO ESPUMOSO",  60.0),
    ("BOONS",          30.0),
    ("STRONGBOW",      10.0),
    ("COPA",           5.0),
]


def calcular_comision_chica(producto_str: str) -> float:
    """Comisión unitaria de un producto para una chica/bailarina."""
    p = str(producto_str).upper().strip()
    for clave, monto, _categoria in TABLA_COMISIONES_CHICAS:
        if clave in p:
            return monto
    return 0.0


def _categoria_producto(producto_str: str) -> str:
    p = str(producto_str).upper().strip()
    for clave, _monto, categoria in TABLA_COMISIONES_CHICAS:
        if clave in p:
            return categoria
    return "Otros"


def calcular_comision_gerencia_caja(producto_str: str) -> float:
    p = str(producto_str).upper().strip()
    for clave, monto in TABLA_COMISION_GERENCIA_CAJA:
        if clave in p:
            return monto
    return 0.0


def calcular_bono_dj_animador(cantidad_chicas_con_descuento: int) -> float:
    """Bono real de DJ/Animador: $40 por cada chica/bailarina que tuvo
    descuento_nomina > 0 en el periodo consultado (día o rango).
    Fuente única — antes esta fórmula estaba repetida en 3 lugares
    (corte diario, dashboard y reporte por periodo), y el reporte por
    periodo contaba mal (todas las chicas, no solo las que tuvieron
    descuento)."""
    return cantidad_chicas_con_descuento * 40.0


def calcular_propina_ventas_propias(df_ventas: pd.DataFrame, empleado_id, porcentaje: float = 50.0) -> float:
    """Propina de las ventas que un empleado atendió personalmente
    (idmesero = su propio id), pagada al mismo % que un mesero normal
    (50% por defecto — ya con el 16% de comisión bancaria descontado en
    tarjeta, igual que a cualquier mesero).

    Pensado para Gerente/Capitán de Mesero/Cajero: normalmente cobran un
    % fijo del total de propinas del restaurante por su rol (8%), pero a
    veces también atienden mesas directamente (su nombre aparece como
    "idmesero" en el Excel de Soft Restaurant). Esta función calcula esa
    propina personal (al 50%, como cualquier mesero) para sumarla aparte
    a su comisión de rol, en un solo pago."""
    if df_ventas is None or df_ventas.empty or 'idmesero' not in df_ventas.columns:
        return 0.0
    filas_propias = df_ventas[df_ventas['idmesero'] == empleado_id]
    if filas_propias.empty:
        return 0.0
    p_tarj = (filas_propias['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in filas_propias.columns else 0.0
    p_efec = filas_propias['propina_efectivo'].sum() if 'propina_efectivo' in filas_propias.columns else 0.0
    p_vale = filas_propias['propina_vales'].sum() if 'propina_vales' in filas_propias.columns else 0.0
    p_cred = filas_propias['propinacredito'].sum() if 'propinacredito' in filas_propias.columns else 0.0
    total_propina_bruta = p_tarj + p_efec + p_vale + p_cred
    return float(total_propina_bruta * (porcentaje / 100.0))


def calcular_comisiones_detalle(df_productos_empleado: pd.DataFrame, penalizada: bool = False,
                                 fechas_penalizadas: set = None) -> dict:
    """
    Calcula el desglose de comisiones de una chica/bailarina a partir de
    sus filas de productos vendidos.

    Columnas esperadas en df_productos_empleado: 'descripcion', 'cantidad',
    y opcionalmente 'fecha' (solo se usa si se pasa fechas_penalizadas).

    - penalizada: si es True, TODAS las filas se calculan a mitad de
      comisión. Pensado para el corte de un solo día (ahí "penalizada"
      es un único booleano para todo el día).
    - fechas_penalizadas: set opcional de fechas (date) en las que aplicar
      mitad de comisión, evaluado fila por fila según su columna 'fecha'.
      Pensado para reportes por periodo (varios días), donde cada día
      puede tener o no la penalización activa.

    Devuelve un dict con "<Categoria>_cant", "<Categoria>_monto" por cada
    categoría en CATEGORIAS_CHICAS, más "total" (suma de todos los montos).
    La cantidad ("_cant") NUNCA se divide por penalización, solo el monto
    (igual que en la lógica original: se sigue viendo cuántas unidades
    vendió, pero se le paga la mitad).
    """
    resultado = {}
    for cat in CATEGORIAS_CHICAS:
        resultado[f"{cat}_cant"] = 0.0
        resultado[f"{cat}_monto"] = 0.0
    resultado["total"] = 0.0

    if df_productos_empleado is None or df_productos_empleado.empty:
        return resultado

    for _, fila in df_productos_empleado.iterrows():
        desc = str(fila["descripcion"])
        cant = float(fila["cantidad"]) if pd.notna(fila.get("cantidad")) else 0.0
        com_unit = calcular_comision_chica(desc)
        subtotal = cant * com_unit

        aplica_penalizacion = penalizada
        if fechas_penalizadas is not None and "fecha" in fila.index:
            aplica_penalizacion = fila["fecha"] in fechas_penalizadas

        if aplica_penalizacion:
            subtotal /= 2.0

        categoria = _categoria_producto(desc)
        if categoria == "Otros":
            continue

        resultado[f"{categoria}_cant"] += cant
        resultado[f"{categoria}_monto"] += subtotal
        resultado["total"] += subtotal

    return resultado
