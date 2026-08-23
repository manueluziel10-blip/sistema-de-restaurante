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
    reiniciar_base_de_datos, obtener_fechas_disponibles
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

opcion = st.sidebar.selectbox("Selecciona una sección", [
    "1. Subir Cortes Diarios (Excel)",
    "2. Gestión y Edición de Empleados",
    "3. Corte y Nómina Final",
    "4. Cierre de Caja Diario (Dashboard)"
], key="menu_seccion_principal")

st.sidebar.markdown("---")
st.sidebar.subheader("⚠️ Zona de Peligro")
if st.sidebar.button("🗑️ Reiniciar Base de Datos"):
    reiniciar_base_de_datos()
    st.sidebar.success("¡Base de datos limpiada con éxito!")
    st.rerun()

# --- SECCIÓN 1: SUBIR ARCHIVOS DIARIOS ---
if opcion == "1. Subir Cortes Diarios (Excel)":
    st.subheader(f"Carga de Archivos Diarios para la fecha: {fecha_activa}")
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
        
        if st.button("Guardar corte de Meseros", key="btn_guardar_corte_meseros"):
            guardar_corte_ventas(df_v, df_p, archivo_origen=up_ventas.name, fecha_corte=fecha_activa)
            st.success(f"¡Corte de meseros guardado correctamente para el día {fecha_activa}!")

    if up_chicas is not None:
        df_c = pd.read_excel(up_chicas, skiprows=4)
        st.success("¡Archivo de productos cargado!")

        if st.button("Procesar y Guardar Comisiones del Día", key="btn_guardar_chicas"):
            if len(df_c.columns) >= 5:
                df_c.columns = ['CLAVE', 'DESCRIPCION', 'GRUPO', 'PRECIO', 'CANTIDAD'] + list(df_c.columns[5:])
                filas_chicas = df_c[df_c['DESCRIPCION'].astype(str).str.contains('>')].copy()

                nuevas_detectadas = guardar_corte_chicas(
                    filas_chicas, calcular_comision_chica, archivo_origen=up_chicas.name, fecha_corte=fecha_activa
                )
                st.success(
                    f"¡Corte procesado y guardado para el día {fecha_activa}! Se registraron {len(nuevas_detectadas)} "
                    f"personas nuevas automáticamente."
                )
            else:
                st.error("El archivo no tiene el formato esperado (menos de 5 columnas).")

# --- SECCIÓN 2: GESTIÓN Y EDICIÓN DE EMPLEADOS ---
elif opcion == "2. Gestión y Edición de Empleados":
    st.subheader("Gestión y Catálogo de Personal")
    
    empleados_df = cargar_empleados_df()

    tab_gest_chicas, tab_gest_general, tab_carga_masiva = st.tabs([
        "💃 Bailarinas y Chicas de Salón",
        "📋 Personal Operativo y General",
        "📂 Alta Masiva por Excel"
    ])

    with tab_gest_chicas:
        st.markdown("### Listado: Bailarinas y Chicas de Salón")
        if not empleados_df.empty:
            df_chicas_gen = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)].copy()
            st.dataframe(df_chicas_gen, use_container_width=True)
        else:
            st.info("No hay registros.")

    with tab_gest_general:
        st.markdown("### Listado: Personal Operativo, Meseros y Fijos")
        if not empleados_df.empty:
            df_general_gen = empleados_df[~empleados_df['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina)].copy()
            st.dataframe(df_general_gen, use_container_width=True)
        else:
            st.info("No hay registros.")

    with tab_carga_masiva:
        st.markdown("### Importar o Actualizar Personal Masivamente")
        st.info("Sube un archivo de Excel con las columnas: **Nombre**, **Puesto** y **Sueldo Base**.")

        filas_plantilla = []
        for idx, (puesto, sueldo) in enumerate(PUESTOS_CATALOGO.items(), start=1):
            filas_plantilla.append({
                "Nombre": f"Ejemplo Empleado {idx}",
                "Puesto": puesto,
                "Sueldo Base": sueldo
            })
        df_plantilla = pd.DataFrame(filas_plantilla)

        buffer_plantilla = io.BytesIO()
        with pd.ExcelWriter(buffer_plantilla, engine='openpyxl') as writer:
            df_plantilla.to_excel(writer, index=False, sheet_name='Plantilla_Personal')
        buffer_plantilla.seek(0)

        st.download_button(
            label="📥 Descargar Plantilla de Excel con Todos los Puestos",
            data=buffer_plantilla,
            file_name="Plantilla_Alta_Empleados_Completa.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("---")
        up_excel_personal = st.file_uploader("Sube tu archivo Excel de empleados", type=["xls", "xlsx"], key="subir_excel_personal")

        if up_excel_personal is not None:
            df_subido = pd.read_excel(up_excel_personal)
            st.markdown("**Vista previa del archivo cargado:**")
            st.dataframe(df_subido.head(), use_container_width=True)

            if st.button("Procesar e Importar Personal"):
                columnas_necesarias = {'Nombre', 'Puesto', 'Sueldo Base'}
                if not columnas_necesarias.issubset(df_subido.columns):
                    st.error(f"El archivo Excel debe contener exactamente las columnas: {', '.join(columnas_necesarias)}")
                else:
                    registrados = 0
                    actualizados = 0
                    empleados_actuales = cargar_empleados_df()
                    nombres_existentes = empleados_actuales['nombre'].tolist() if not empleados_actuales.empty else []

                    for _, row in df_subido.iterrows():
                        nombre_emp = str(row['Nombre']).strip()
                        puesto_emp = str(row['Puesto']).strip()
                        sueldo_emp = float(row['Sueldo Base']) if pd.notna(row['Sueldo Base']) else 0.0

                        if not nombre_emp:
                            continue

                        if puesto_emp not in PUESTOS_CATALOGO:
                            puesto_emp = "Mesero (Comisiones)"

                        if nombre_emp in nombres_existentes:
                            emp_encontrado = empleados_actuales[empleados_actuales['nombre'] == nombre_emp].iloc[0]
                            actualizar_empleado(int(emp_encontrado['id']), puesto_emp, sueldo_emp)
                            actualizados += 1
                        else:
                            agregar_empleado(nombre_emp, puesto_emp, sueldo_emp)
                            registrados += 1

                    st.success(f"¡Importación completada con éxito! Nuevos agregados: {registrados} | Actualizados: {actualizados}")
                    st.rerun()

    st.markdown("---")
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.markdown("### Modificar Empleado / Sueldo / Puesto")
        if not empleados_df.empty:
            nombres_emps = empleados_df['nombre'].tolist()
            emp_a_editar = st.selectbox("Selecciona empleado a modificar", nombres_emps, key="sel_emp_mod")

            emp_actual = empleados_df[empleados_df['nombre'] == emp_a_editar].iloc[0]
            nuevo_tipo_edit = st.selectbox(
                "Nuevo Puesto", list(PUESTOS_CATALOGO.keys()),
                index=list(PUESTOS_CATALOGO.keys()).index(emp_actual['tipo'])
                if emp_actual['tipo'] in PUESTOS_CATALOGO else 0,
                key="sel_tipo_mod"
            )
            sueldo_sugerido = PUESTOS_CATALOGO.get(nuevo_tipo_edit, float(emp_actual['sueldo_base']))
            nuevo_sueldo_edit = st.number_input("Sueldo Base ($)", value=sueldo_sugerido, format="%.2f", key="edit_sueldo_input")

            if st.button("Actualizar Empleado"):
                actualizar_empleado(int(emp_actual['id']), nuevo_tipo_edit, nuevo_sueldo_edit)
                st.success(f"¡Datos de {emp_a_editar} actualizados!")
                st.rerun()

    with col_der:
        st.markdown("### Agregar Empleado Manual")
        with st.form("form_empleado"):
            nuevo_nombre = st.text_input("Nombre Completo")
            nuevo_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()), key="form_puesto")
            nuevo_sueldo = st.number_input("Sueldo Base ($)", value=PUESTOS_CATALOGO[nuevo_tipo], format="%.2f", key="form_sueldo_input")

            if st.form_submit_button("Guardar Empleado"):
                if nuevo_nombre.strip():
                    agregar_empleado(nuevo_nombre, nuevo_tipo, nuevo_sueldo)
                    st.success("¡Guardado con éxito!")
                    st.rerun()
                else:
                    st.error("El nombre no puede estar vacío.")

# --- SECCIÓN 3: CORTE Y NÓMINA FINAL ---
elif opcion == "3. Corte y Nómina Final":
    st.subheader(f"Cálculo de Nómina Semanal - Fecha: {fecha_activa}")

    tab_bailarinas, tab_meseros, tab_seguridad, tab_general = st.tabs([
        "💃 Bailarinas y Chicas",
        "👥 Meseros y Ayudantes",
        "🛡️ Seguridad",
        "📋 Personal General y Fijo"
    ])

    empleados_df = cargar_empleados_df()
    ventas_totales = cargar_ventas_df(fecha_activa)
    chicas_totales = cargar_chicas_df(fecha_activa)

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
                key=f"pen_{key_sufijo}_{emp_id}"
            )

            if penalizada_cambiada != penalizada_actual:
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
                if not sus_filas.empty:
                    for _, f_prod in sus_filas.iterrows():
                        desc = str(f_prod['descripcion']).upper()
                        cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                        com_unit = 300.0 if 'PRIVADO ARTISTA' in desc else float(f_prod['comision_unitaria'])
                        subtotal_prod = cant * com_unit
                        
                        if 'PRIVADO ARTISTA' in desc:
                            vip5_priv_art_cant += cant
                            vip5_priv_art_monto += subtotal_prod
                        elif 'BOONS ARTISTA' in desc:
                            boons_cant += cant
                            boons_monto += subtotal_prod
                        elif 'BOONS' in desc:
                            boons_cant += cant
                            boons_monto += subtotal_prod
                        elif 'COPA LADY' in desc:
                            copa_cant += cant
                            copa_monto += subtotal_prod
                        elif 'MINI STRONGBOW' in desc:
                            strong_cant += cant
                            strong_monto += subtotal_prod
                        elif 'VIP30' in desc:
                            vip30_cant += cant
                            vip30_monto += subtotal_prod
                        elif 'VIP 15' in desc or 'VIP15' in desc:
                            vip15_cant += cant
                            vip15_monto += subtotal_prod
                        elif 'VIP5' in desc or 'PRIVADO' in desc:
                            vip5_priv_art_cant += cant
                            vip5_priv_art_monto += subtotal_prod
                        elif 'VIP3' in desc:
                            vip3_cant += cant
                            vip3_monto += subtotal_prod

                    extras = boons_monto + copa_monto + strong_monto + vip3_monto + vip5_priv_art_monto + vip15_monto + vip30_monto

            if penalizada_cambiada:
                extras = extras / 2.0
                boons_monto /= 2.0
                copa_monto /= 2.0
                strong_monto /= 2.0
                vip3_monto /= 2.0
                vip5_priv_art_monto /= 2.0
                vip15_monto /= 2.0
                vip30_monto /= 2.0

            total_bruto = sueldo_base + extras
            total_pagar = total_bruto - vales_emp - transf_emp - descuento_emp
            
            res_grupo.append({
                "ID": emp_id,
                "Nombre": nombre, 
                "Puesto": emp['tipo'],
                "Total a Pagar": total_pagar,
                "Sueldo Base": sueldo_base,
                "Vales": vales_emp,
                "Transferencia": transf_emp,
                "Descuento": descuento_emp,
                "Comisiones": extras, 
                "Boons": f"{int(boons_cant)} (${boons_monto:,.2f})",
                "Copa Lady": f"{int(copa_cant)} (${copa_monto:,.2f})",
                "Strongbow": f"{int(strong_cant)} (${strong_monto:,.2f})",
                "VIP 3": f"{int(vip3_cant)} (${vip3_monto:,.2f})",
                "VIP 5 / Priv / Artista": f"{int(vip5_priv_art_cant)} (${vip5_priv_art_monto:,.2f})",
                "VIP 15": f"{int(vip15_cant)} (${vip15_monto:,.2f})",
                "VIP 30": f"{int(vip30_cant)} (${vip30_monto:,.2f})",
                "_b_cant": boons_cant, "_b_m": boons_monto,
                "_c_cant": copa_cant, "_c_m": copa_monto,
                "_s_cant": strong_cant, "_s_m": strong_monto,
                "_v3_cant": vip3_cant, "_v3_m": vip3_monto,
                "_v5_art_cant": vip5_priv_art_cant, "_v5_art_m": vip5_priv_art_monto,
                "_v15_cant": vip15_cant, "_v15_m": vip15_monto,
                "_v30_cant": vip30_cant, "_v30_m": vip30_monto
            })
        
        df_res = pd.DataFrame(res_grupo)
        cols_mostrar = [c for c in df_res.columns if not c.startswith("_")]
        altura_tabla = min(max(len(df_res) * 45 + 40, 150), 900)

        def resaltar_filas(row):
            return ['background-color: #1A2634; color: #FFFFFF;' if row.name % 2 == 0 else 'background-color: #141D26; color: #FFFFFF;'] * len(row)

        def pintar_negativos(val):
            if isinstance(val, (int, float)) and val < 0:
                return 'color: #FF5252; font-weight: bold;'
            return ''

        df_estilizado = df_res[cols_mostrar].style.apply(resaltar_filas, axis=1).map(
            pintar_negativos, subset=['Total a Pagar']
        )

        editor_key = f"editor_sueldos_{key_sufijo}"
        df_editado = st.data_editor(
            df_estilizado,
            height=altura_tabla,
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "Total a Pagar": st.column_config.NumberColumn("Total a Pagar ($)", format="$%.2f", disabled=True),
                "Sueldo Base": st.column_config.NumberColumn("Sueldo Base ($)", format="$%.2f", required=True),
                "Vales": st.column_config.NumberColumn("Vales ($)", format="$%.2f", required=True),
                "Transferencia": st.column_config.NumberColumn("Transferencia ($)", format="$%.2f", required=True),
                "Descuento": st.column_config.NumberColumn("Descuento ($)", format="$%.2f", required=True),
                "Comisiones": st.column_config.NumberColumn("Comisiones ($)", format="$%.2f", disabled=True),
            },
            disabled=[c for c in cols_mostrar if c not in ["Sueldo Base", "Vales", "Transferencia", "Descuento"]],
            use_container_width=True,
            key=editor_key
        )

        actualizado_flag = False
        if editor_key in st.session_state:
            cambios = st.session_state[editor_key].get("edited_rows", {})
            for row_idx, edits in cambios.items():
                fila_modificada = df_res.iloc[int(row_idx)]
                e_id = int(fila_modificada['ID'])
                nuevo_sb = float(edits["Sueldo Base"]) if "Sueldo Base" in edits else float(fila_modificada['Sueldo Base'])
                nuevo_vales = float(edits["Vales"]) if "Vales" in edits else float(fila_modificada['Vales'])
                nueva_transf = float(edits["Transferencia"]) if "Transferencia" in edits else float(fila_modificada['Transferencia'])
                nuevo_desc = float(edits["Descuento"]) if "Descuento" in edits else float(fila_modificada['Descuento'])
                puesto_emp = fila_modificada['Puesto']
                penalizada_bd = bool(empleados_df[empleados_df['id'] == e_id]['penalizada'].values[0])
                
                actualizar_empleado(e_id, puesto_emp, nuevo_sb, nuevo_vales, penalizada_bd, nuevo_desc, nueva_transf)
                actualizado_flag = True

        if actualizado_flag:
            st.rerun()

        subtotal = float(df_res['Total a Pagar'].sum())
        return df_editado, subtotal

    def procesar_grupo_general(df_subgrupo, nombre_pestana, key_sufijo):
        if df_subgrupo.empty:
            st.info(f"No hay registros en {nombre_pestana}.")
            return 0.0

        chicas_con_descuento_count = 0
        if not empleados_df.empty:
            df_chicas_todas = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)]
            chicas_con_descuento_count = len(df_chicas_todas[df_chicas_todas['descuento_nomina'] > 0.0]) if 'descuento_nomina' in df_chicas_todas.columns else len(df_chicas_todas)

        res_general = []
        for _, emp in df_subgrupo.iterrows():
            emp_id = emp['id']
            nombre = emp['nombre']
            tipo = emp['tipo']
            sueldo_base = float(emp['sueldo_base'])
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            
            puesto_upper_check = tipo.upper()
            comisiones_prod = 0.0
            
            if any(p in puesto_upper_check for p in ["DJ", "ANIMADOR"]):
                porcentaje_propina = 0.0
                comisiones_prod = chicas_con_descuento_count * 40.0
            elif "SEGURIDAD" in puesto_upper_check:
                porcentaje_propina = 0.0
            elif "BARMAN" in puesto_upper_check:
                porcentaje_propina = 10.0
            elif "AYUDANTE" in puesto_upper_check:
                porcentaje_propina = 5.0
            elif any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                porcentaje_propina = 8.0
            else:
                porcentaje_propina = 50.0

            propinas = 0.0
            if not ventas_totales.empty and porcentaje_propina > 0.0:
                prop_tarj = (ventas_totales['propina_tarjeta'].sum() if 'propina_tarjeta' in ventas_totales.columns else 0.0) * 0.84
                prop_efec = ventas_totales['propina_efectivo'].sum() if 'propina_efectivo' in ventas_totales.columns else 0.0
                prop_vale = ventas_totales['propina_vales'].sum() if 'propina_vales' in ventas_totales.columns else 0.0
                total_propinaable = prop_tarj + prop_efec + prop_vale
                propinas = total_propinaable * (porcentaje_propina / 100.0)

            if any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                if not chicas_totales.empty:
                    for _, f_prod in chicas_totales.iterrows():
                        comisiones_prod += float(f_prod['cantidad']) * calcular_comision_gerencia_caja(f_prod['descripcion'])

            total_bruto = sueldo_base + propinas + comisiones_prod
            total_pagar = total_bruto - vales_emp - transf_emp
            propina_str = f"↑ {porcentaje_propina:.1f}% (${propinas:,.2f})"

            res_general.append({
                "ID": emp_id, "Nombre": nombre, "Puesto": tipo,
                "Total a Pagar": total_pagar, "Sueldo Base": sueldo_base,
                "Vales": vales_emp, "Transferencia": transf_emp,
                "Propina (%)": propina_str, "Comisiones": comisiones_prod,
                "_propinas_num": propinas
            })

        df_res_general = pd.DataFrame(res_general)
        cols_mostrar_gen = ["ID", "Nombre", "Puesto", "Total a Pagar", "Sueldo Base", "Vales", "Transferencia", "Propina (%)", "Comisiones"]
        altura_tabla_gen = min(max(len(df_res_general) * 45 + 40, 150), 900)
        editor_key_gen = f"editor_sueldos_gen_{key_sufijo}"

        def resaltar_filas_gen(row):
            return ['background-color: #1A2634; color: #FFFFFF;' if row.name % 2 == 0 else 'background-color: #141D26; color: #FFFFFF;'] * len(row)

        def pintar_negativos_gen(val):
            if isinstance(val, (int, float)) and val < 0:
                return 'color: #FF5252; font-weight: bold;'
            return ''

        df_estilizado_gen = df_res_general[cols_mostrar_gen].style.apply(resaltar_filas_gen, axis=1).map(
            pintar_negativos_gen, subset=['Total a Pagar']
        )
        
        df_editado_gen = st.data_editor(
            df_estilizado_gen,
            height=altura_tabla_gen,
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "Total a Pagar": st.column_config.NumberColumn("Total a Pagar ($)", format="$%.2f", disabled=True),
                "Sueldo Base": st.column_config.NumberColumn("Sueldo Base ($)", format="$%.2f", required=True),
                "Vales": st.column_config.NumberColumn("Vales ($)", format="$%.2f", required=True),
                "Transferencia": st.column_config.NumberColumn("Transferencia ($)", format="$%.2f", required=True),
                "Propina (%)": st.column_config.TextColumn("Propina (%)", disabled=True),
                "Comisiones": st.column_config.NumberColumn("Comisiones ($)", format="$%.2f", disabled=True),
            },
            disabled=["ID", "Nombre", "Puesto", "Propina (%)", "Comisiones", "Total a Pagar"],
            use_container_width=True,
            key=editor_key_gen
        )

        actualizado_gen_flag = False
        if editor_key_gen in st.session_state:
            cambios_gen = st.session_state[editor_key_gen].get("edited_rows", {})
            for row_idx, edits in cambios_gen.items():
                fila_mod_gen = df_res_general.iloc[int(row_idx)]
                e_id = int(fila_mod_gen['ID'])
                nuevo_sb = float(edits["Sueldo Base"]) if "Sueldo Base" in edits else float(fila_mod_gen['Sueldo Base'])
                nuevo_vales = float(edits["Vales"]) if "Vales" in edits else float(fila_mod_gen['Vales'])
                nueva_transf = float(edits["Transferencia"]) if "Transferencia" in edits else float(fila_mod_gen['Transferencia'])
                puesto_emp = fila_mod_gen['Puesto']
                penalizada_bd = bool(empleados_df[empleados_df['id'] == e_id]['penalizada'].values[0])
                descuento_bd = float(empleados_df[empleados_df['id'] == e_id]['descuento_nomina'].values[0]) if 'descuento_nomina' in empleados_df.columns else 100.0
                
                actualizar_empleado(e_id, puesto_emp, nuevo_sb, nuevo_vales, penalizada_bd, descuento_bd, nueva_transf)
                actualizado_gen_flag = True

        if actualizado_gen_flag:
            st.rerun()

        return float(df_res_general['Total a Pagar'].sum())

    with tab_bailarinas:
        df_chicas_nomina = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)] if not empleados_df.empty else pd.DataFrame()
        procesar_grupo_chicas(df_chicas_nomina, "Bailarinas y Chicas", "bailarinas_chicas")

    with tab_meseros:
        if not empleados_df.empty:
            mask_meseros = (empleados_df['tipo'].astype(str).str.upper().str.contains("MESERO") & ~empleados_df['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN")) | empleados_df['tipo'].astype(str).str.upper().str.contains("AYUDANTE")
            df_meseros = empleados_df[mask_meseros]
        else:
            df_meseros = pd.DataFrame()
        procesar_grupo_general(df_meseros, "Meseros y Ayudantes", "meseros_ayudantes")

    with tab_seguridad:
        df_seguridad = empleados_df[empleados_df['tipo'].astype(str).str.upper().str.contains("SEGURIDAD")] if not empleados_df.empty else pd.DataFrame()
        procesar_grupo_general(df_seguridad, "Seguridad", "seguridad")

    with tab_general:
        if not empleados_df.empty:
            mask_general = (~empleados_df['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina) & ~empleados_df['tipo'].astype(str).str.upper().str.contains("SEGURIDAD|AYUDANTE") & ~(empleados_df['tipo'].astype(str).str.upper().str.contains("MESERO") & ~empleados_df['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN")))
            df_general_otros = empleados_df[mask_general]
        else:
            df_general_otros = pd.DataFrame()
        procesar_grupo_general(df_general_otros, "Personal General y Fijo", "general_otros")

# --- SECCIÓN 4: CIERRE DE CAJA DIARIO (DASHBOARD) ---
elif opcion == "4. Cierre de Caja Diario (Dashboard)":
    st.subheader(f"📊 Dashboard y Resumen de Cierre - Fecha: {fecha_activa}")

    ventas_acumuladas = cargar_ventas_df(fecha_activa)
    chicas_acumuladas = cargar_chicas_df(fecha_activa)
    empleados_dashboard_df = cargar_empleados_df()

    nomina_personal_p_total = 0.0
    vales_personal_total = 0.0
    transferencia_personal_total = 0.0
    
    if not empleados_dashboard_df.empty:
        df_operativo_dash = empleados_dashboard_df[~empleados_dashboard_df['tipo'].apply(es_chica_o_bailarina)]
        for _, emp in df_operativo_dash.iterrows():
            sueldo_base = float(emp['sueldo_base'])
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            vales_personal_total += vales_emp
            transferencia_personal_total += transf_emp
            nomina_personal_p_total += sueldo_base

    nomina_chicas_calc = 0.0
    vales_chicas_total = 0.0
    transferencia_chicas_total = 0.0
    conteo_penalizadas = 0
    conteo_con_sueldo = 0
    conteo_sin_sueldo = 0

    if not empleados_dashboard_df.empty:
        df_chicas_lista = empleados_dashboard_df[empleados_dashboard_df['tipo'].apply(es_chica_o_bailarina)]
        for _, emp in df_chicas_lista.iterrows():
            emp_id = emp['id']
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            descuento_emp = float(emp.get('descuento_nomina', 100.0))
            vales_chicas_total += vales_emp
            transferencia_chicas_total += transf_emp
            
            penalizada_chica = bool(emp.get('penalizada', False))
            if penalizada_chica: conteo_penalizadas += 1
            if float(emp['sueldo_base']) > 0.0: conteo_con_sueldo += 1
            else: conteo_sin_sueldo += 1
            
            sus_filas = chicas_acumuladas[chicas_acumuladas['empleado_id'] == emp_id] if not chicas_acumuladas.empty else pd.DataFrame()
            comisiones_chica_ind = 0.0
            for _, r in sus_filas.iterrows():
                desc = str(r['descripcion']).upper()
                cant = float(r['cantidad']) if pd.notna(r['cantidad']) else 0.0
                com = 300.0 if 'PRIVADO ARTISTA' in desc else (1000.0 if 'BOONS ARTISTA' in desc else (700.0 if 'BOONS' in desc else float(r['comision_unitaria'])))
                comisiones_chica_ind += cant * com
            
            if penalizada_chica: comisiones_chica_ind /= 2.0
            nomina_chicas_calc += (float(emp['sueldo_base']) + comisiones_chica_ind - descuento_emp)

    st.markdown("### 📥 Registro de Gastos y Datos del Día")
    gasto_previo = cargar_gastos_hoy(fecha_activa)
    
    g_cocina_val = float(gasto_previo.gasto_cocina) if gasto_previo else 0.0
    g_compras_val = float(gasto_previo.gasto_compras) if gasto_previo else 0.0
    g_vales_val = float(gasto_previo.gasto_vales) if gasto_previo else 0.0

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        gasto_cocina = st.number_input("Gastos - Cocina ($)", value=g_cocina_val, format="%.2f", key="input_gasto_cocina")
    with col_g2:
        gasto_compras = st.number_input("Gastos - Compras ($)", value=g_compras_val, format="%.2f", key="input_gasto_compras")
    with col_g3:
        gasto_vales = st.number_input("Vales / Otros ($)", value=g_vales_val, format="%.2f", key="input_gasto_vales")

    if st.button("Guardar Gastos del Día"):
        guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales, fecha_corte=fecha_activa)
        st.success(f"¡Gastos guardados correctamente para el día {fecha_activa}!")
        st.rerun()

    st.markdown("---")
    
    # --- CÁLCULO SEGURO DE VENTAS (EVITA KEYERROR) ---
    efectivo_ventas = tarjeta_ventas = transferencia_ventas = ventas_por_cobrar = 0.0

    if not ventas_acumuladas.empty:
        col_efec = ventas_acumuladas['efectivo'] if 'efectivo' in ventas_acumuladas.columns else 0.0
        col_pefec = ventas_acumuladas['propina_efectivo'] if 'propina_efectivo' in ventas_acumuladas.columns else 0.0
        efectivo_ventas = float((col_efec + col_pefec).sum())

        col_tarj = ventas_acumuladas['tarjeta'] if 'tarjeta' in ventas_acumuladas.columns else 0.0
        col_ptarj = ventas_acumuladas['propina_tarjeta'] if 'propina_tarjeta' in ventas_acumuladas.columns else 0.0
        tarjeta_ventas = float((col_tarj + col_ptarj).sum())

        col_val = ventas_acumuladas['vales'] if 'vales' in ventas_acumuladas.columns else 0.0
        col_pval = ventas_acumuladas['propina_vales'] if 'propina_vales' in ventas_acumuladas.columns else 0.0
        transferencia_ventas = float((col_val + col_pval).sum())

        col_otros = ventas_acumuladas['otros'] if 'otros' in ventas_acumuladas.columns else 0.0
        col_pcred = ventas_acumuladas['propinacredito'] if 'propinacredito' in ventas_acumuladas.columns else 0.0
        ventas_por_cobrar = float((col_otros + col_pcred).sum())

    ventas_totales_con_propinas = efectivo_ventas + tarjeta_ventas + transferencia_ventas + ventas_por_cobrar
    nomina_personal_efectivo = nomina_personal_p_total - vales_personal_total - transferencia_personal_total
    nomina_chicas_efectivo = nomina_chicas_calc - vales_chicas_total - transferencia_chicas_total
    
    total_gastos_nomina_efectivo = nomina_personal_efectivo + nomina_chicas_efectivo + gasto_cocina + gasto_compras + gasto_vales
    efectivo_entregado = efectivo_ventas - total_gastos_nomina_efectivo
    
    utilidad_monto = ventas_totales_con_propinas - ((nomina_personal_p_total + nomina_chicas_calc) + gasto_cocina)
    utilidad_porcentaje = (utilidad_monto / ventas_totales_con_propinas * 100.0) if ventas_totales_con_propinas > 0 else 0.0

    st.markdown("#### 💰 Resumen de Ventas y Efectivo")
    col_d1, col_d2, col_d3, col_d4, col_d5 = st.columns(5)
    for col, (tit, val) in zip([col_d1, col_d2, col_d3, col_d4, col_d5], [
        ("VENTAS TOTALES", ventas_totales_con_propinas),
        ("VENTAS EFECTIVO", efectivo_ventas),
        ("VENTAS TERMINALES", tarjeta_ventas),
        ("VENTAS TRANSFERENCIAS", transferencia_ventas),
        ("VENTAS POR COBRAR", ventas_por_cobrar)
    ]):
        col.markdown(f"""<div style="background-color: #141D26; padding: 14px; border-radius: 10px; border: 1px solid #1F2937; text-align: center;"><div style="color: #90A4AE; font-size: 10px; font-weight: bold;">{tit}</div><div style="color: #FFFFFF; font-size: 18px; font-weight: bold; margin-top: 6px;">${val:,.2f}</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_e1, col_e2 = st.columns(2)
    col_e1.markdown(f"""<div style="background-color: #1A2634; padding: 18px; border-radius: 12px; border-left: 5px solid #00E676;"><div style="color: #90A4AE; font-size: 11px; font-weight: bold;">EFECTIVO ENTREGADO</div><div style="color: #FFFFFF; font-size: 26px; font-weight: bold; margin-top: 5px;">${efectivo_entregado:,.2f}</div></div>""", unsafe_allow_html=True)
    col_e2.markdown(f"""<div style="background-color: #1A2634; padding: 18px; border-radius: 12px; border-left: 5px solid #29B6F6;"><div style="color: #90A4AE; font-size: 11px; font-weight: bold;">UTILIDAD ({utilidad_porcentaje:.1f}%)</div><div style="color: #FFFFFF; font-size: 26px; font-weight: bold; margin-top: 5px;">${utilidad_monto:,.2f}</div></div>""", unsafe_allow_html=True)

    st.markdown("---")
    tabla_gastos = pd.DataFrame([
        {"Concepto": "Nómina - Personal (P)", "Monto": nomina_personal_efectivo},
        {"Concepto": "Nómina - Comisiones Chicas (CH)", "Monto": nomina_chicas_efectivo},
        {"Concepto": "Cocina", "Monto": gasto_cocina},
        {"Concepto": "Compras", "Monto": gasto_compras},
        {"Concepto": "Vales (Gastos / Otros)", "Monto": gasto_vales},
        {"Concepto": "TOTAL GASTOS / NÓMINA", "Monto": total_gastos_nomina_efectivo}
    ])
    st.dataframe(tabla_gastos, use_container_width=True)

    resumen_meseros = pd.DataFrame()
    if not ventas_acumuladas.empty and not empleados_dashboard_df.empty:
        df_vm = pd.merge(ventas_acumuladas, empleados_dashboard_df[['id', 'nombre']], left_on='idmesero', right_on='id', how='left')
        for c in ['efectivo', 'propina_efectivo', 'tarjeta', 'propina_tarjeta', 'vales', 'propina_vales', 'otros', 'propinacredito']:
            if c not in df_vm.columns: df_vm[c] = 0.0
        resumen_meseros = df_vm.groupby('nombre').agg({'efectivo': 'sum', 'propina_efectivo': 'sum', 'tarjeta': 'sum', 'propina_tarjeta': 'sum', 'vales': 'sum', 'propina_vales': 'sum', 'otros': 'sum', 'propinacredito': 'sum'}).reset_index()
        resumen_meseros['importe_total'] = resumen_meseros['efectivo'] + resumen_meseros['propina_efectivo'] + resumen_meseros['tarjeta'] + resumen_meseros['propina_tarjeta'] + resumen_meseros['vales'] + resumen_meseros['propina_vales'] + resumen_meseros['otros'] + resumen_meseros['propinacredito']

    def generar_pdf():
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
        elementos = []
        styles = getSampleStyleSheet()
        
        titulo_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor("#1A2634"), spaceAfter=4, alignment=1, fontName='Helvetica-Bold')
        sub_style = ParagraphStyle('ST', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor("#1A2634"), spaceBefore=8, spaceAfter=3, fontName='Helvetica-Bold')

        elementos.append(Paragraph(f"ZULLYS MENS CLUB - REPORTE DE CIERRE ({fecha_activa})", titulo_style))
        elementos.append(Spacer(1, 6))
        
        elementos.append(Paragraph("1. Resumen de Ventas y Flujo Principal", sub_style))
        datos_ventas = [
            ["Concepto", "Monto"],
            ["Ventas Totales", f"${ventas_totales_con_propinas:,.2f}"],
            ["Efectivo Entregado", f"${efectivo_entregado:,.2f}"],
            ["Utilidad", f"${utilidad_monto:,.2f} ({utilidad_porcentaje:.1f}%)"]
        ]
        t_ventas = Table(datos_ventas, colWidths=[270, 270])
        t_ventas.setStyle(TableStyle([('BACKGROUND', (0, 0), (1, 0), colors.HexColor("#1A2634")), ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")), ('FONTSIZE', (0, 0), (-1, -1), 8)]))
        elementos.append(t_ventas)
        
        doc.build(elementos)
        buffer.seek(0)
        return buffer

    st.markdown("---")
    st.download_button(
        label=f"📄 Descargar Reporte en PDF ({fecha_activa})",
        data=generar_pdf(),
        file_name=f"Cierre_Caja_{fecha_activa}.pdf",
        mime="application/pdf",
        use_container_width=True
    )