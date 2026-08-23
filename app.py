import streamlit as st
import pandas as pd
from datetime import datetime
import io

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from models import (
    cargar_empleados_df, agregar_empleado, actualizar_empleado,
    guardar_corte_ventas, guardar_corte_chicas,
    cargar_ventas_df, cargar_chicas_df,
    guardar_gastos_del_dia, cargar_gastos_hoy,
    reiniciar_base_de_datos, obtener_fechas_disponibles,
    verificar_dia_bloqueado, bloquear_dia_db, desbloquear_dia_db
)

st.set_page_config(layout="wide")
st.title("Sistema Integral: Nómina, Ventas y Cierre de Caja - Restaurante")

# --- ESTILOS CSS GLOBALES PARA TABLAS Y EDITORES OSCUROS ---
st.markdown("""
    <style>
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            background-color: #141D26 !important;
            border-radius: 10px;
            border: 1px solid #1F2937 !important;
            padding: 5px;
        }
        th {
            background-color: #1A2634 !important;
            color: #FFFFFF !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- LISTA OFICIAL DE PUESTOS Y SUELDOS BASE ---
PUESTOS_CATALOGO = {
    "Chicas / Bailarinas (Comisiones)": 300.0,
    "Mesero (Comisiones)": 300.0,
    "Barman (Fijo)": 400.0,
    "Seguridad (Fijo)": 500.0,
    "DJ (Fijo)": 600.0,
    "Animador (Fijo)": 400.0,
    "Gerente (Fijo)": 500.0,
    "Capitán de Mesero (Fijo)": 400.0,
    "Ayudante de Mesero (Fijo)": 300.0,
    "Cajero (Fijo)": 400.0
}

def es_chica_o_bailarina(tipo_str):
    t = str(tipo_str).upper()
    return ('CHICA' in t) or ('BAILARINA' in t)

def calcular_comision_chica(producto_str):
    p = producto_str.upper().strip()
    if 'PRIVADO ARTISTA' in p:
        return 300.0
    elif 'BOONS ARTISTA' in p:
        return 1000.0
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

def calcular_comision_gerencia_caja(producto_str):
    p = producto_str.upper().strip()
    if 'MOET IMPERIAL' in p:
        return 170.0
    elif 'VINO ESPUMOSO' in p:
        return 60.0
    elif 'BOONS' in p:
        return 30.0
    elif 'STRONGBOW' in p:
        return 10.0
    elif 'COPA' in p:
        return 5.0
    return 0.0

# --- MENÚ LATERAL Y BÚSQUEDA DE HISTORIAL ---
st.sidebar.header("Menú de Control")

# --- SISTEMA DE AUTENTICACIÓN DE ADMINISTRADOR ---
st.sidebar.markdown("---")
st.sidebar.subheader("🔒 Acceso de Administrador")
if "es_admin" not in st.session_state:
    st.session_state.es_admin = False

if not st.session_state.es_admin:
    password_input = st.sidebar.text_input("Contraseña de Admin", type="password")
    if st.sidebar.button("🔓 Iniciar Sesión Admin"):
        if password_input == "Zullys2026*": 
            st.session_state.es_admin = True
            st.sidebar.success("¡Acceso concedido!")
            st.rerun()
        else:
            st.sidebar.error("Contraseña incorrecta")
else:
    st.sidebar.success("🛡️ Sesión de Admin Activa")
    if st.sidebar.button("🔒 Cerrar Sesión"):
        st.session_state.es_admin = False
        st.rerun()

st.sidebar.markdown("---")
fechas_disponibles = obtener_fechas_disponibles()
modo_fecha = st.sidebar.radio("Modo de Operación", ["📅 Día Actual / Nuevo Corte", "🔍 Buscar Corte Histórico"])

fecha_activa = None
if modo_fecha == "🔍 Buscar Corte Histórico":
    if fechas_disponibles:
        fecha_activa = st.sidebar.selectbox("Selecciona la fecha del reporte", fechas_disponibles)
        st.sidebar.warning(f"⚠️ Visualizando histórico: {fecha_activa}")
    else:
        st.sidebar.info("No hay cortes históricos registrados aún.")
        fecha_activa = datetime.now().strftime('%Y-%m-%d')
else:
    fecha_activa = st.sidebar.date_input("Fecha para el Corte Actual", datetime.now()).strftime('%Y-%m-%d')

# Verificar si el día actual está bloqueado
dia_bloqueado = verificar_dia_bloqueado(fecha_activa)
if dia_bloqueado:
    st.sidebar.error(f"🔒 Este día ({fecha_activa}) está bloqueado.")

opcion = st.sidebar.selectbox("Selecciona una sección", [
    "1. Subir Cortes Diarios (Excel)",
    "2. Gestión y Edición de Empleados",
    "3. Corte y Nómina Final",
    "4. Cierre de Caja Diario (Dashboard)"
], key="menu_seccion_principal")

st.sidebar.markdown("---")
st.sidebar.subheader("⚠️ Zona de Peligro")
if st.sidebar.button("🗑️ Reiniciar Base de Datos"):
    if st.session_state.es_admin:
        reiniciar_base_de_datos()
        st.sidebar.success("¡Base de datos limpiada con éxito!")
        st.rerun()
    else:
        st.sidebar.error("⚠️ Se requiere sesión de Administrador para reiniciar la base de datos.")

# --- SECCIÓN 1: SUBIR ARCHIVOS DIARIOS ---
if opcion == "1. Subir Cortes Diarios (Excel)":
    st.subheader(f"Carga de Archivos Diarios para la fecha: {fecha_activa}")
    
    if dia_bloqueado:
        st.error(f"🚫 El reporte del día {fecha_activa} está **BLOQUEADO**. No se pueden subir nuevos archivos a menos que un administrador lo desbloquee en el Dashboard.")
    else:
        st.info("Sube los archivos correspondientes al corte del día seleccionado.")
        col_1, col_2, col_3 = st.columns(3)
        with col_1:
            up_ventas = st.file_uploader("Subir 'ventasmeseros.xls'", type=["xls", "xlsx"], key="subir_ventas_meseros")
        with col_2:
            up_propinas = st.file_uploader("Subir 'chequesconpropinaincluida.xls'", type=["xls", "xlsx"], key="subir_cheques_propinas")
        with col_3:
            up_chicas = st.file_uploader("Subir 'PRODUCTOSVENDIDOSPERIODO.XLS'", type=["xls", "xlsx"], key="subir_productos_chicas")

        if up_ventas is not None and up_propinas is not None:
            df_v = pd.read_excel(up_ventas)
            df_p = pd.read_excel(up_propinas)
            df_v['idmesero'] = pd.to_numeric(df_v['idmesero'], errors='coerce').fillna(0).astype(int)
            df_p['idmesero'] = pd.to_numeric(df_p['idmesero'], errors='coerce').fillna(0).astype(int)

            st.success("¡Archivos de ventas y propinas cargados correctamente!")
            st.dataframe(df_v.head(), width=700)
            
            if st.session_state.es_admin:
                if st.button("Guardar corte de Meseros", key="btn_guardar_corte_meseros"):
                    guardar_corte_ventas(df_v, df_p, archivo_origen=up_ventas.name, fecha_corte=fecha_activa)
                    st.success(f"¡Corte guardado correctamente para el día {fecha_activa}!")
            else:
                st.warning("🔒 Inicia sesión como Administrador en la barra lateral para guardar este corte.")

        if up_chicas is not None:
            df_c = pd.read_excel(up_chicas, skiprows=4)
            st.success("¡Archivo de productos cargado!")

            if st.session_state.es_admin:
                if st.button("Procesar y Guardar Comisiones del Día", key="btn_guardar_chicas"):
                    if len(df_c.columns) >= 5:
                        df_c.columns = ['CLAVE', 'DESCRIPCION', 'GRUPO', 'PRECIO', 'CANTIDAD'] + list(df_c.columns[5:])
                        filas_chicas = df_c[df_c['DESCRIPCION'].astype(str).str.contains('>')].copy()
                        nuevas_detectadas = guardar_corte_chicas(
                            filas_chicas, calcular_comision_chica, archivo_origen=up_chicas.name, fecha_corte=fecha_activa
                        )
                        st.success(f"¡Corte procesado! Se registraron {len(nuevas_detectadas)} personas nuevas.")
                    else:
                        st.error("El archivo no tiene el formato esperado.")
            else:
                st.warning("🔒 Inicia sesión como Administrador para procesar estas comisiones.")

# --- SECCIÓN 2: GESTIÓN Y EDICIÓN DE EMPLEADOS ---
elif opcion == "2. Gestión y Edición de Empleados":
    st.subheader("Gestión y Catálogo de Personal")
    empleados_df = cargar_empleados_df()

    if not st.session_state.es_admin:
        st.info("👁️ Estás viendo el catálogo en modo lectura. Inicia sesión como Administrador en la barra lateral para modificar o agregar personal.")
        st.dataframe(empleados_df, use_container_width=True)
    else:
        tab_gest_chicas, tab_gest_general, tab_carga_masiva = st.tabs([
            "💃 Bailarinas y Chicas de Salón",
            "📋 Personal Operativo y General",
            "📂 Alta Masiva por Excel"
        ])

        with tab_gest_chicas:
            if not empleados_df.empty:
                st.dataframe(empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)], use_container_width=True)

        with tab_gest_general:
            if not empleados_df.empty:
                st.dataframe(empleados_df[~empleados_df['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina)], use_container_width=True)

        with tab_carga_masiva:
            up_excel_personal = st.file_uploader("Sube tu archivo Excel de empleados", type=["xls", "xlsx"])
            if up_excel_personal is not None and st.button("Procesar e Importar Personal"):
                df_subido = pd.read_excel(up_excel_personal)
                for _, row in df_subido.iterrows():
                    agregar_empleado(str(row['Nombre']), str(row['Puesto']), float(row['Sueldo Base']))
                st.success("¡Importado correctamente!")
                st.rerun()

        st.markdown("---")
        col_izq, col_der = st.columns(2)
        with col_izq:
            st.markdown("### Modificar Empleado")
            if not empleados_df.empty:
                emp_a_editar = st.selectbox("Selecciona empleado", empleados_df['nombre'].tolist())
                emp_actual = empleados_df[empleados_df['nombre'] == emp_a_editar].iloc[0]
                nuevo_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()))
                nuevo_sueldo = st.number_input("Sueldo Base ($)", value=float(emp_actual['sueldo_base']))
                if st.button("Actualizar Empleado"):
                    actualizar_empleado(int(emp_actual['id']), nuevo_tipo, nuevo_sueldo)
                    st.success("¡Actualizado!")
                    st.rerun()

        with col_der:
            st.markdown("### Agregar Empleado Manual")
            with st.form("form_empleado"):
                n_nombre = st.text_input("Nombre Completo")
                n_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()))
                n_sueldo = st.number_input("Sueldo Base ($)", value=300.0)
                if st.form_submit_button("Guardar Empleado"):
                    if n_nombre.strip():
                        agregar_empleado(n_nombre, n_tipo, n_sueldo)
                        st.success("¡Guardado!")
                        st.rerun()

# --- SECCIÓN 3: CORTE Y NÓMINA FINAL ---
elif opcion == "3. Corte y Nómina Final":
    st.subheader(f"Cálculo de Nómina - Fecha: {fecha_activa}")
    if dia_bloqueado:
        st.warning("🔒 Este día está **Bloqueado**. Los campos de edición de nómina están deshabilitados.")

    empleados_df = cargar_empleados_df()
    ventas_totales = cargar_ventas_df(fecha_activa)
    chicas_totales = cargar_chicas_df(fecha_activa)

    tab_bailarinas, tab_meseros, tab_seguridad, tab_general = st.tabs([
        "💃 Bailarinas y Chicas", "👥 Meseros y Ayudantes", "🛡️ Seguridad", "📋 Personal General"
    ])

    def procesar_grupo_chicas(df_subgrupo, nombre_pestana, key_sufijo):
        if df_subgrupo.empty:
            st.info(f"No hay registros en {nombre_pestana}.")
            return pd.DataFrame(), 0.0

        res_grupo = []
        for _, emp in df_subgrupo.iterrows():
            emp_id = emp['id']
            nombre = emp['nombre']
            sueldo_base = float(emp['sueldo_base'])
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            descuento_emp = float(emp.get('descuento_nomina', 100.0))
            penalizada_actual = bool(emp.get('penalizada', False))

            penalizada_cambiada = st.checkbox(
                f"¿Aplicar mitad de comisiones (penalización) a {nombre}?",
                value=penalizada_actual,
                disabled=dia_bloqueado or not st.session_state.es_admin,
                key=f"pen_{key_sufijo}_{emp_id}"
            )

            if penalizada_cambiada != penalizada_actual and st.session_state.es_admin and not dia_bloqueado:
                actualizar_empleado(emp_id, emp['tipo'], sueldo_base, vales_emp, penalizada_cambiada, descuento_emp, transf_emp)
                st.rerun()

            extras = 0.0
            boons_cant, boons_monto = 0.0, 0.0
            copa_cant, copa_monto = 0.0, 0.0
            strong_cant, strong_monto = 0.0, 0.0
            vip3_cant, vip3_monto = 0.0, 0.0
            vip5_priv_art_cant, vip5_priv_art_monto = 0.0, 0.0
            vip15_cant, vip15_monto = 0.0, 0.0
            vip30_cant, vip30_monto = 0.0, 0.0

            if not chicas_totales.empty and 'empleado_id' in chicas_totales.columns:
                sus_filas = chicas_totales[chicas_totales['empleado_id'] == emp_id]
                for _, f_prod in sus_filas.iterrows():
                    desc = str(f_prod['descripcion']).upper()
                    cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                    com_unit = 300.0 if 'PRIVADO ARTISTA' in desc else float(f_prod['comision_unitaria'])
                    subtotal_prod = cant * com_unit
                    
                    if 'PRIVADO ARTISTA' in desc:
                        vip5_priv_art_cant += cant; vip5_priv_art_monto += subtotal_prod
                    elif 'BOONS' in desc:
                        boons_cant += cant; boons_monto += subtotal_prod
                    elif 'COPA LADY' in desc:
                        copa_cant += cant; copa_monto += subtotal_prod
                    elif 'MINI STRONGBOW' in desc:
                        strong_cant += cant; strong_monto += subtotal_prod
                    elif 'VIP30' in desc:
                        vip30_cant += cant; vip30_monto += subtotal_prod
                    elif 'VIP 15' in desc or 'VIP15' in desc:
                        vip15_cant += cant; vip15_monto += subtotal_prod
                    elif 'VIP5' in desc or 'PRIVADO' in desc:
                        vip5_priv_art_cant += cant; vip5_priv_art_monto += subtotal_prod
                    elif 'VIP3' in desc:
                        vip3_cant += cant; vip3_monto += subtotal_prod

                extras = boons_monto + copa_monto + strong_monto + vip3_monto + vip5_priv_art_monto + vip15_monto + vip30_monto

            if penalizada_cambiada:
                extras /= 2.0

            total_pagar = (sueldo_base + extras) - vales_emp - transf_emp - descuento_emp
            res_grupo.append({
                "ID": emp_id, "Nombre": nombre, "Puesto": emp['tipo'], "Total a Pagar": total_pagar,
                "Sueldo Base": sueldo_base, "Vales": vales_emp, "Transferencia": transf_emp,
                "Descuento": descuento_emp, "Comisiones": extras,
                "_b_cant": boons_cant, "_b_m": boons_monto, "_c_cant": copa_cant, "_c_m": copa_monto,
                "_s_cant": strong_cant, "_s_m": strong_monto, "_v3_cant": vip3_cant, "_v3_m": vip3_monto,
                "_v5_art_cant": vip5_priv_art_cant, "_v5_art_m": vip5_priv_art_monto,
                "_v15_cant": vip15_cant, "_v15_m": vip15_monto, "_v30_cant": vip30_cant, "_v30_m": vip30_monto
            })

        df_res = pd.DataFrame(res_grupo)
        cols_mostrar = [c for c in df_res.columns if not c.startswith("_")]
        
        # Permitir edición solo si es admin y el día NO está bloqueado
        desactivar_edicion = dia_bloqueado or not st.session_state.es_admin
        editor_key = f"editor_sueldos_{key_sufijo}"
        
        df_editado = st.data_editor(
            df_res[cols_mostrar],
            disabled=True if desactivar_edicion else [c for c in cols_mostrar if c not in ["Sueldo Base", "Vales", "Transferencia", "Descuento"]],
            use_container_width=True,
            key=editor_key
        )

        if not desactivar_edicion and editor_key in st.session_state:
            cambios = st.session_state[editor_key].get("edited_rows", {})
            for row_idx, edits in cambios.items():
                fila_modificada = df_res.iloc[int(row_idx)]
                e_id = int(fila_modificada['ID'])
                nuevo_sb = float(edits.get("Sueldo Base", fila_modificada['Sueldo Base']))
                nuevo_vales = float(edits.get("Vales", fila_modificada['Vales']))
                nueva_transf = float(edits.get("Transferencia", fila_modificada['Transferencia']))
                nuevo_desc = float(edits.get("Descuento", fila_modificada['Descuento']))
                actualizar_empleado(e_id, fila_modificada['Puesto'], nuevo_sb, nuevo_vales, None, nuevo_desc, nueva_transf)
                st.rerun()

        return df_editado, float(df_res['Total a Pagar'].sum() if not df_res.empty else 0.0)

    with tab_bailarinas:
        _, sub_b = procesar_grupo_chicas(empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)] if not empleados_df.empty else pd.DataFrame(), "Bailarinas", "bailarinas_chicas")

# --- SECCIÓN 4: CIERRE DE CAJA DIARIO (DASHBOARD) ---
elif opcion == "4. Cierre de Caja Diario (Dashboard)":
    st.subheader(f"📊 Dashboard y Resumen de Cierre - Fecha: {fecha_activa}")

    ventas_acumuladas = cargar_ventas_df(fecha_activa)
    chicas_acumuladas = cargar_chicas_df(fecha_activa)
    empleados_dashboard_df = cargar_empleados_df()

    st.markdown("### 🛡️ Control de Cierre y Bloqueo Definitivo")
    if dia_bloqueado:
        st.error(f"🔒 Este reporte del día {fecha_activa} está **BLOQUEADO Y CERRADO DEFINITIVAMENTE**.")
        if st.session_state.es_admin:
            if st.button("🔓 Desbloquear Día para Edición"):
                desbloquear_dia_db(fecha_activa)
                st.success("¡Día desbloqueado con éxito!")
                st.rerun()
        else:
            st.info("ℹ️ Solo un Administrador puede desbloquear este día.")
    else:
        st.warning(f"⚠️ El día {fecha_activa} se encuentra abierto a modificaciones.")
        if st.session_state.es_admin:
            if st.button("🔒 Bloquear y Guardar Reporte Definitivo"):
                bloquear_dia_db(fecha_activa)
                st.success(f"¡El reporte del día {fecha_activa} ha sido bloqueado con éxito!")
                st.rerun()
        else:
            st.info("ℹ️ Inicia sesión como Administrador para bloquear este día.")

    st.markdown("---")
    st.markdown("### 📥 Registro de Gastos del Día")
    gasto_previo = cargar_gastos_hoy(fecha_activa)
    g_cocina_val = float(gasto_previo.gasto_cocina) if gasto_previo else 0.0
    g_compras_val = float(gasto_previo.gasto_compras) if gasto_previo else 0.0
    g_vales_val = float(gasto_previo.gasto_vales) if gasto_previo else 0.0

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        gasto_cocina = st.number_input("Gastos - Cocina ($)", value=g_cocina_val, disabled=dia_bloqueado or not st.session_state.es_admin)
    with col_g2:
        gasto_compras = st.number_input("Gastos - Compras ($)", value=g_compras_val, disabled=dia_bloqueado or not st.session_state.es_admin)
    with col_g3:
        gasto_vales = st.number_input("Vales / Otros ($)", value=g_vales_val, disabled=dia_bloqueado or not st.session_state.es_admin)

    if not dia_bloqueado and st.session_state.es_admin:
        if st.button("Guardar Gastos del Día"):
            guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales, fecha_corte=fecha_activa)
            st.success("¡Gastos guardados!")
            st.rerun()

    # Cálculos finales de ventas para dashboard
    efectivo_ventas = tarjeta_ventas = transferencia_ventas = ventas_por_cobrar = 0.0
    if not ventas_acumuladas.empty:
        efectivo_ventas = float((ventas_acumuladas.get('efectivo', 0) + ventas_acumuladas.get('propina_efectivo', 0)).sum())
        tarjeta_ventas = float((ventas_acumuladas.get('tarjeta', 0) + ventas_acumuladas.get('propina_tarjeta', 0)).sum())
        transferencia_ventas = float((ventas_acumuladas.get('vales', 0) + ventas_acumuladas.get('propina_vales', 0)).sum())
        ventas_por_cobrar = float((ventas_acumuladas.get('otros', 0) + ventas_acumuladas.get('propinacredito', 0)).sum())

    ventas_totales = efectivo_ventas + tarjeta_ventas + transferencia_ventas + ventas_por_cobrar
    st.metric("VENTAS TOTALES", f"${ventas_totales:,.2f}")