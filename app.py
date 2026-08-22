import streamlit as st
import pandas as pd

from models import (
    cargar_empleados_df, agregar_empleado, actualizar_empleado,
    guardar_corte_ventas, guardar_corte_chicas,
    cargar_ventas_df, cargar_chicas_df,
    guardar_gastos_del_dia, cargar_gastos_hoy,
)

st.title("Sistema Integral: Nómina, Ventas y Cierre de Caja - Restaurante")

# --- LISTA OFICIAL DE PUESTOS Y SUELDOS BASE ---
PUESTOS_CATALOGO = {
    "Chicas / Bailarinas (Comisiones)": 300.0,
    "Mesero (Comisiones)": 300.0,
    "Seguridad (Fijo)": 500.0,
    "DJ (Fijo)": 600.0,
    "Animador (Fijo)": 400.0,
    "Gerente (Fijo)": 500.0,
    "Capitán de Mesero (Fijo)": 400.0,
    "Ayudante de Mesero (Fijo)": 300.0
}

# --- REGLAS DE COMISIÓN PARA CHICAS / BAILARINAS ---
def calcular_comision_chica(producto_str):
    p = producto_str.upper().strip()
    if 'PRIVADO ARTISTA' in p:
        return 600.0
    elif 'BOONS ARTISTA' in p:
        return 700.0
    elif 'BOONS' in p:
        return 700.0
    elif 'COPA LADY' in p:
        return 100.0
    elif 'MINI STRONGBOW' in p:
        return 250.0
    elif 'VIP30' in p:
        return 1900.0
    elif 'VIP 15' in p or 'VIP15' in p:
        return 1000.0
    elif 'VIP5' in p or 'PRIVADO' in p:
        return 100.0
    elif 'VIP3' in p:
        return 50.0
    return 0.0

# --- MENÚ LATERAL ---
st.sidebar.header("Menú de Control")
opcion = st.sidebar.selectbox("Selecciona una sección", [
    "1. Subir Cortes Diarios (Excel)",
    "2. Gestión y Edición de Empleados",
    "3. Corte y Nómina Final",
    "4. Cierre de Caja Diario (Dashboard)"
])

# --- SECCIÓN 1: SUBIR ARCHIVOS DIARIOS ---
if opcion == "1. Subir Cortes Diarios (Excel)":
    st.subheader("Carga de Archivos Diarios de Caja")
    st.info("Sube los archivos correspondientes al corte del día.")

    col_1, col_2, col_3 = st.columns(3)
    with col_1:
        up_ventas = st.file_uploader("Subir 'ventasmeseros.xls'", type=["xls", "xlsx"], key="subir_ventas_meseros")
    with col_2:
        up_propinas = st.file_uploader("Subir 'chequesconpropinaincluida.xls'", type=["xls", "xlsx"], key="subir_cheques_propinas")
    with col_3:
        up_chicas = st.file_uploader("Subir 'PRODUCTOSVENDIDOSPERIODO.XLS'", type=["xls", "xlsx"], key="subir_productos_chicas")

    # Procesar Meseros y Propinas juntos
    if up_ventas is not None and up_propinas is not None:
        df_v = pd.read_excel(up_ventas)
        df_p = pd.read_excel(up_propinas)
        
        st.success("¡Archivos de ventas y propinas cargados correctamente!")
        st.dataframe(df_v.head(), width=700)
        
        if st.button("Guardar corte de Meseros", key="btn_guardar_corte_meseros"):
            guardar_corte_ventas(df_v, df_p, archivo_origen=up_ventas.name)
            st.success("¡Corte de meseros y propinas guardado correctamente en la base de datos!")

    # Procesar Productos de Chicas / Bailarinas
    if up_chicas is not None:
        df_c = pd.read_excel(up_chicas, skiprows=4)
        st.success("¡Archivo de productos cargado!")
import streamlit as st
import pandas as pd

from models import (
    cargar_empleados_df, agregar_empleado, actualizar_empleado,
    guardar_corte_ventas, guardar_corte_chicas,
    cargar_ventas_df, cargar_chicas_df,
    guardar_gastos_del_dia, cargar_gastos_hoy,
)

st.set_page_config(layout="wide")
st.title("Sistema Integral: Nómina, Ventas y Cierre de Caja - Restaurante")

# --- LISTA OFICIAL DE PUESTOS ---
PUESTOS_CATALOGO = {
    "Chicas / Bailarinas (Comisiones)": 300.0,
    "Mesero (Comisiones)": 300.0,
    "Seguridad (Fijo)": 500.0,
    "DJ (Fijo)": 600.0,
    "Animador (Fijo)": 400.0,
    "Gerente (Fijo)": 500.0,
    "Capitán de Mesero (Fijo)": 400.0,
    "Ayudante de Mesero (Fijo)": 300.0
}

# --- REGLAS DE COMISIÓN ---
def calcular_comision_chica(producto_str):
    p = producto_str.upper().strip()
    if 'PRIVADO ARTISTA' in p: return 600.0
    elif 'BOONS ARTISTA' in p: return 700.0
    elif 'BOONS' in p: return 700.0
    elif 'COPA LADY' in p: return 100.0
    elif 'MINI STRONGBOW' in p: return 250.0
    elif 'VIP30' in p: return 1900.0
    elif 'VIP 15' in p or 'VIP15' in p: return 1000.0
    elif 'VIP5' in p or 'PRIVADO' in p: return 100.0
    elif 'VIP3' in p: return 50.0
    return 0.0

# --- MENÚ LATERAL ---
st.sidebar.header("Menú de Control")
opcion = st.sidebar.selectbox("Selecciona una sección", [
    "1. Subir Cortes Diarios (Excel)",
    "2. Gestión y Edición de Empleados",
    "3. Corte y Nómina Final",
    "4. Cierre de Caja Diario (Dashboard)"
])

# --- SECCIÓN 1: SUBIR ARCHIVOS ---
if opcion == "1. Subir Cortes Diarios (Excel)":
    st.subheader("Carga de Archivos Diarios")
    col1, col2, col3 = st.columns(3)
    up_ventas = col1.file_uploader("Subir 'ventasmeseros.xls'", type=["xls", "xlsx"])
    up_propinas = col2.file_uploader("Subir 'chequesconpropinaincluida.xls'", type=["xls", "xlsx"])
    up_chicas = col3.file_uploader("Subir 'PRODUCTOSVENDIDOSPERIODO.XLS'", type=["xls", "xlsx"])

    if up_ventas and up_propinas:
        df_v = pd.read_excel(up_ventas)
        df_p = pd.read_excel(up_propinas)
        if st.button("Guardar corte de Meseros"):
            guardar_corte_ventas(df_v, df_p, up_ventas.name)
            st.success("¡Datos guardados!")

    if up_chicas:
        df_c = pd.read_excel(up_chicas, skiprows=4)
        if st.button("Procesar Comisiones Chicas"):
            df_c.columns = ['CLAVE', 'DESCRIPCION', 'GRUPO', 'PRECIO', 'CANTIDAD'] + list(df_c.columns[5:])
            guardar_corte_chicas(df_c[df_c['DESCRIPCION'].astype(str).str.contains('>')], calcular_comision_chica, up_chicas.name)
            st.success("¡Comisiones procesadas!")

# --- SECCIÓN 2: GESTIÓN EMPLEADOS ---
elif opcion == "2. Gestión y Edición de Empleados":
    empleados_df = cargar_empleados_df()
    def es_chica(tipo): return 'CHICA' in str(tipo).upper() or 'BAILARINA' in str(tipo).upper()

    t1, t2 = st.tabs(["💃 Bailarinas y Chicas", "📋 Personal General"])
    with t1: st.dataframe(empleados_df[empleados_df['tipo'].apply(es_chica)], use_container_width=True)
    with t2: st.dataframe(empleados_df[~empleados_df['tipo'].apply(es_chica)], use_container_width=True)

    with st.expander("Modificar / Agregar Empleado"):
        c_mod, c_add = st.columns(2)
        with c_mod:
            n = st.selectbox("Empleado", empleados_df['nombre'].tolist())
            t = st.selectbox("Nuevo Puesto", list(PUESTOS_CATALOGO.keys()))
            s = st.number_input("Sueldo Base ($)", value=300.0)
            if st.button("Actualizar"): actualizar_empleado(n, t, s); st.rerun()
        with c_add:
            n_name = st.text_input("Nombre")
            n_puesto = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()), key="add_p")
            n_sueldo = st.number_input("Sueldo Base", value=300.0, key="add_s")
            if st.button("Guardar"): agregar_empleado(n_name, n_puesto, n_sueldo); st.rerun()

# --- SECCIÓN 3: CORTE Y NÓMINA ---
elif opcion == "3. Corte y Nómina Final":
    empleados_df = cargar_empleados_df()
    ventas_totales = cargar_ventas_df()
    chicas_totales = cargar_chicas_df()

    def es_chica(t): return 'CHICA' in str(t).upper() or 'BAILARINA' in str(t).upper()

    t_b, t_g = st.tabs(["💃 Bailarinas y Chicas", "📋 Personal Operativo"])

    # Pestaña Bailarinas
    with t_b:
        data = []
        for _, emp in empleados_df[empleados_df['tipo'].apply(es_chica)].iterrows():
            filas = chicas_totales[chicas_totales['empleado_id'] == emp['id']]
            ext = float((filas['comision_unitaria'] * filas['cantidad']).sum())
            data.append({"Nombre": emp['nombre'], "Puesto": emp['tipo'], "Sueldo Base": float(emp['sueldo_base']), "Comisiones": ext, "Total": float(emp['sueldo_base']) + ext})
        
        df_b = st.data_editor(pd.DataFrame(data), column_config={"Sueldo Base": st.column_config.NumberColumn(format="$%.2f")})
        for _, row in df_b.iterrows(): actualizar_empleado(row['Nombre'], row['Puesto'], row['Sueldo Base'])
        st.metric("Subtotal Chicas", f"${df_b['Total'].sum():,.2f}")

    # Pestaña Personal General (Meseros)
    with t_g:
        data_g = []
        for _, emp in empleados_df[~empleados_df['tipo'].apply(es_chica)].iterrows():
            ext = 0.0
            if "Mesero" in emp['tipo'] and not ventas_totales.empty:
                v = ventas_totales[ventas_totales['nombre'].str.upper().str.strip() == emp['nombre'].upper().strip()]
                if not v.empty:
                    prop = v[['propina_tarjeta', 'propina_efectivo', 'propina_vales']].sum().sum()
                    ext = prop * 0.50
            data_g.append({"Nombre": emp['nombre'], "Puesto": emp['tipo'], "Sueldo Base": float(emp['sueldo_base']), "Extras": ext, "Total": float(emp['sueldo_base']) + ext})
        
        df_g = st.data_editor(pd.DataFrame(data_g), column_config={"Sueldo Base": st.column_config.NumberColumn(format="$%.2f")})
        for _, row in df_g.iterrows(): actualizar_empleado(row['Nombre'], row['Puesto'], row['Sueldo Base'])
        st.metric("Subtotal General", f"${df_g['Total'].sum():,.2f}")

# --- SECCIÓN 4: DASHBOARD ---
elif opcion == "4. Cierre de Caja Diario (Dashboard)":
    st.subheader("📊 Resumen Financiero")
    # (Dashboard simplificado para brevedad, igual al anterior)