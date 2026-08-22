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

        if st.button("Procesar y Guardar Comisiones del Día", key="btn_guardar_chicas"):
            if len(df_c.columns) >= 5:
                df_c.columns = ['CLAVE', 'DESCRIPCION', 'GRUPO', 'PRECIO', 'CANTIDAD'] + list(df_c.columns[5:])
                filas_chicas = df_c[df_c['DESCRIPCION'].astype(str).str.contains('>')].copy()

                nuevas_detectadas = guardar_corte_chicas(
                    filas_chicas, calcular_comision_chica, archivo_origen=up_chicas.name
                )
                st.success(
                    f"¡Corte procesado y guardado! Se registraron {len(nuevas_detectadas)} "
                    f"personas nuevas automáticamente."
                )
            else:
                st.error("El archivo no tiene el formato esperado (menos de 5 columnas).")

# --- SECCIÓN 2: GESTIÓN Y EDICIÓN DE EMPLEADOS ---
elif opcion == "2. Gestión y Edición de Empleados":
    st.subheader("Gestión y Catálogo de Personal")
    
    empleados_df = cargar_empleados_df()

    tab_gest_chicas, tab_gest_general = st.tabs([
        "💃 Bailarinas y Chicas de Salón",
        "📋 Personal Operativo y General"
    ])

    def es_chica_o_bailarina(tipo_str):
        t = str(tipo_str).upper()
        return ('CHICA' in t) or ('BAILARINA' in t) or ('COMISIONES' in t and 'MESERO' not in t)

    with tab_gest_chicas:
        st.markdown("### Listado: Bailarinas y Chicas de Salón")
        if not empleados_df.empty:
            df_chicas_gen = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)]
            st.dataframe(df_chicas_gen, use_container_width=True)
        else:
            st.info("No hay registros.")

    with tab_gest_general:
        st.markdown("### Listado: Personal Operativo, Meseros y Fijos")
        if not empleados_df.empty:
            df_general_gen = empleados_df[~empleados_df['tipo'].apply(es_chica_o_bailarina)]
            st.dataframe(df_general_gen, use_container_width=True)
        else:
            st.info("No hay registros.")

    st.markdown("---")
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.markdown("### Modificar Empleado / Sueldo / Puesto")
        if not empleados_df.empty:
            nombres_emps = empleados_df['nombre'].tolist()
            emp_a_editar = st.selectbox("Selecciona empleado a modificar", nombres_emps)

            emp_actual = empleados_df[empleados_df['nombre'] == emp_a_editar].iloc[0]
            nuevo_tipo_edit = st.selectbox(
                "Nuevo Puesto", list(PUESTOS_CATALOGO.keys()),
                index=list(PUESTOS_CATALOGO.keys()).index(emp_actual['tipo'])
                if emp_actual['tipo'] in PUESTOS_CATALOGO else 0
            )
            sueldo_sugerido = PUESTOS_CATALOGO.get(nuevo_tipo_edit, float(emp_actual['sueldo_base']))
            nuevo_sueldo_edit = st.number_input("Sueldo Base ($)", value=sueldo_sugerido, format="%.2f", key="edit_sueldo_input")

            if st.button("Actualizar Empleado"):
                actualizar_empleado(emp_a_editar, nuevo_tipo_edit, nuevo_sueldo_edit)
                st.success(f"¡Datos de {emp_a_editar} actualizados!")
                st.rerun()

    with col_der:
        st.markdown("### Agregar Empleado Manual")
        with st.form("form_empleado"):
            nuevo_nombre = st.text_input("Nombre Completo")
            nuevo_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()))
            nuevo_sueldo = st.number_input("Sueldo Base ($)", value=PUESTOS_CATALOGO[nuevo_tipo], format="%.2f", key="form_sueldo_input")

            if st.form_submit_button("Guardar Empleado"):
                if nuevo_nombre.strip():
                    agregar_empleado(nuevo_nombre, nuevo_tipo, nuevo_sueldo)
                    st.success("¡Guardado con éxito!")
                    st.rerun()
                else:
                    st.error("El nombre no puede estar vacío.")

# --- SECCIÓN 3: CORTE Y NÓMINA FINAL (UNIFICADO EN PESTAÑAS) ---
elif opcion == "3. Corte y Nómina Final":
    st.subheader("Cálculo de Nómina Semanal por Categorías")

    tab_bailarinas, tab_general = st.tabs([
        "💃 Bailarinas y Chicas",
        "📋 Personal Operativo y General"
    ])

    empleados_df = cargar_empleados_df()
    ventas_totales = cargar_ventas_df()
    chicas_totales = cargar_chicas_df()

    def procesar_grupo_chicas(df_subgrupo, nombre_pestana, key_sufijo):
        if df_subgrupo.empty:
            st.info(f"No hay registros en {nombre_pestana}.")
            return pd.DataFrame(), 0.0

        res_grupo = []
        for _, emp in df_subgrupo.iterrows():
            emp_id = emp['id']
            nombre = emp['nombre']
            sueldo_base = float(emp['sueldo_base'])

            penalizada = st.checkbox(
                f"¿Aplicar mitad de comisiones (penalización) a {nombre}?",
                key=f"pen_{key_sufijo}_{emp_id}"
            )

            extras = 0.0
            boons_cant = 0.0
            copa_cant = 0.0
            strong_cant = 0.0
            vip3_cant = 0.0
            vip5_priv_cant = 0.0
            vip15_cant = 0.0
            vip30_cant = 0.0
            priv_artista_cant = 0.0

            if not chicas_totales.empty:
                sus_filas = chicas_totales[chicas_totales['empleado_id'] == emp_id]
                if not sus_filas.empty:
                    extras = float((sus_filas['comision_unitaria'] * sus_filas['cantidad']).sum())
                    
                    for _, f_prod in sus_filas.iterrows():
                        desc = str(f_prod['descripcion']).upper()
                        cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                        
                        if 'PRIVADO ARTISTA' in desc:
                            priv_artista_cant += cant
                        elif 'BOONS' in desc:
                            boons_cant += cant
                        elif 'COPA LADY' in desc:
                            copa_cant += cant
                        elif 'MINI STRONGBOW' in desc:
                            strong_cant += cant
                        elif 'VIP30' in desc:
                            vip30_cant += cant
                        elif 'VIP 15' in desc or 'VIP15' in desc:
                            vip15_cant += cant
                        elif 'VIP5' in desc or 'PRIVADO' in desc:
                            vip5_priv_cant += cant
                        elif 'VIP3' in desc:
                            vip3_cant += cant

            if penalizada:
                extras = extras / 2.0

            total_pagar = sueldo_base + extras
            res_grupo.append({
                "ID": emp_id, 
                "Nombre": nombre, 
                "Puesto": emp['tipo'],
                "Boons": int(boons_cant),
                "Copa Lady": int(copa_cant),
                "Strongbow": int(strong_cant),
                "VIP 3": int(vip3_cant),
                "VIP 5 / Privado": int(vip5_priv_cant),
                "VIP 15": int(vip15_cant),
                "VIP 30": int(vip30_cant),
                "Privado Artista": int(priv_artista_cant),
                "Sueldo Base": sueldo_base, 
                "Comisiones": extras, 
                "Total a Pagar": total_pagar
            })
        
        df_res = pd.DataFrame(res_grupo)
        
        df_editado = st.data_editor(
            df_res,
            column_config={
                "Sueldo Base": st.column_config.NumberColumn(
                    "Sueldo Base ($)",
                    help="Haz clic para modificar el sueldo base directamente",
                    min_value=0.0,
                    format="$%.2f",
                    required=True
                ),
                "Total a Pagar": st.column_config.NumberColumn(
                    "Total a Pagar ($)",
                    format="$%.2f",
                    disabled=True
                ),
                "Comisiones": st.column_config.NumberColumn(
                    "Comisiones ($)",
                    format="$%.2f",
                    disabled=True
                ),
            },
            disabled=["ID", "Nombre", "Puesto", "Boons", "Copa Lady", "Strongbow", "VIP 3", "VIP 5 / Privado", "VIP 15", "VIP 30", "Privado Artista", "Comisiones"],
            use_container_width=True,
            key=f"editor_sueldos_{key_sufijo}"
        )

        df_editado['Total a Pagar'] = df_editado['Sueldo Base'] + df_editado['Comisiones']

        for _, row_ed in df_editado.iterrows():
            e_id = row_ed['ID']
            nuevo_sb = float(row_ed['Sueldo Base'])
            original_sb = float(df_res[df_res['ID'] == e_id]['Sueldo Base'].values[0])
            if nuevo_sb != original_sb:
                actualizar_empleado(row_ed['Nombre'], row_ed['Puesto'], nuevo_sb)

        st.markdown(f"##### 📦 Totales de Productos Vendidos - {nombre_pestana}")
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
        c1.metric("Boons", int(df_editado['Boons'].sum()))
        c2.metric("Copa Lady", int(df_editado['Copa Lady'].sum()))
        c3.metric("Strongbow", int(df_editado['Strongbow'].sum()))
        c4.metric("VIP 3", int(df_editado['VIP 3'].sum()))
        c5.metric("VIP 5/Priv", int(df_editado['VIP 5 / Privado'].sum()))
        c6.metric("VIP 15", int(df_editado['VIP 15'].sum()))
        c7.metric("VIP 30", int(df_editado['VIP 30'].sum()))
        c8.metric("Priv. Artista", int(df_editado['Privado Artista'].sum()))

        subtotal = float(df_editado['Total a Pagar'].sum())
        st.metric(f"Subtotal Nómina {nombre_pestana}", f"${subtotal:,.2f}")
        return df_editado, subtotal

    def es_chica_o_bailarina(tipo_str):
        t = str(tipo_str).upper()
        return ('CHICA' in t) or ('BAILARINA' in t) or ('COMISIONES' in t and 'MESERO' not in t)

    # --- PESTAÑA 1: BAILARINAS Y CHICAS ---
    with tab_bailarinas:
        st.markdown("### Nómina: Bailarinas y Chicas")
        df_chicas_nomina = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)] if not empleados_df.empty else pd.DataFrame()
        df_editado_b, sub_b = procesar_grupo_chicas(df_chicas_nomina, "Bailarinas y Chicas", "bailarinas_chicas")

    # --- PESTAÑA 2: PERSONAL GENERAL Y OPERATIVO ---
    with tab_general:
        st.markdown("### Nómina: Personal Operativo, Meseros y Gerencia")
        df_general_empleados = empleados_df[~empleados_df['tipo'].apply(es_chica_o_bailarina)] if not empleados_df.empty else empleados_df

        if df_general_empleados.empty:
            st.info("No hay personal general registrado.")
            sub_g = 0.0
        else:
            res_general = []
            for _, emp in df_general_empleados.iterrows():
                emp_id = emp['id']
                nombre = emp['nombre']
                tipo = emp['tipo']
                sueldo_base = float(emp['sueldo_base'])
                extras = 0.0

                if "Mesero" in tipo:
                    if not ventas_totales.empty and 'idmesero' in ventas_totales.columns:
                        ventas_emp = ventas_totales[ventas_totales['idmesero'] == emp_id]
                        penalizado = st.checkbox(f"¿Penalizar a {nombre}?", key=f"pen_mesero_{emp_id}")
                        if not ventas_emp.empty and 'propina_tarjeta' in ventas_emp.columns:
                            total_propina = float(ventas_emp['propina_tarjeta'].sum() + ventas_emp['propina_efectivo'].sum())
                            tasa = 0.10 if not penalizado else 0.05
                            extras = total_propina * tasa

                total_pagar = sueldo_base + extras
                res_general.append({
                    "ID": emp_id, "Nombre": nombre, "Puesto": tipo,
                    "Sueldo Base": sueldo_base, "Comisiones / Extras": extras, "Total a Pagar": total_pagar
                })
            df_res_general = pd.DataFrame(res_general)
            st.dataframe(df_res_general, use_container_width=True)
            sub_g = float(df_res_general['Total a Pagar'].sum())
            st.metric("Subtotal Nómina Personal General", f"${sub_g:,.2f}")

    st.markdown("---")
    total_general_semana = sub_b + sub_g
    st.metric("💸 NÓMINA TOTAL GENERAL DE LA SEMANA", f"${total_general_semana:,.2f}")

# --- SECCIÓN 4: CIERRE DE CAJA DIARIO (DASHBOARD) ---
elif opcion == "4. Cierre de Caja Diario (Dashboard)":
    st.subheader("📊 Dashboard y Resumen de Cierre Diario")
    st.info("Este panel consolida las ventas totales, terminales, efectivo, propinas, gastos y nómina diaria basados en tus archivos cargados.")

    ventas_acumuladas = cargar_ventas_df()
    chicas_acumuladas = cargar_chicas_df()

    venta_total_calc = (
        float(ventas_acumuladas['importe'].sum())
        if not ventas_acumuladas.empty and 'importe' in ventas_acumuladas.columns else 0.0
    )

    nomina_chicas_calc = 0.0
    if not chicas_acumuladas.empty:
        nomina_chicas_calc = float(
            (chicas_acumuladas['comision_unitaria'] * chicas_acumuladas['cantidad']).sum()
        )

    st.markdown("### 📥 Registro de Gastos y Datos del Día")
    gasto_previo = cargar_gastos_hoy()
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        gasto_cocina = st.number_input(
            "Gastos - Cocina ($)",
            value=float(gasto_previo.gasto_cocina) if gasto_previo else 0.0, format="%.2f"
        )
    with col_g2:
        gasto_compras = st.number_input(
            "Gastos - Compras ($)",
            value=float(gasto_previo.gasto_compras) if gasto_previo else 0.0, format="%.2f"
        )
    with col_g3:
        gasto_vales = st.number_input(
            "Vales / Otros ($)",
            value=float(gasto_previo.gasto_vales) if gasto_previo else 0.0, format="%.2f"
        )

    if st.button("Guardar Gastos del Día"):
        guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales)
        st.success("¡Gastos del día guardados!")
        st.rerun()

    st.markdown("---")
    st.markdown("### 📋 Resumen Financiero del Día (Estilo Dashboard)")

    efectivo_ventas = 0.0
    tarjeta_ventas = 0.0
    if not ventas_acumuladas.empty:
        base_efectivo = float(ventas_acumuladas['efectivo'].sum()) if 'efectivo' in ventas_acumuladas.columns else 0.0
        prop_efectivo = float(ventas_acumuladas['propina_efectivo'].sum()) if 'propina_efectivo' in ventas_acumuladas.columns else 0.0
        efectivo_ventas = base_efectivo + prop_efectivo

        base_tarjeta = float(ventas_acumuladas['tarjeta'].sum()) if 'tarjeta' in ventas_acumuladas.columns else 0.0
        prop_tarjeta = float(ventas_acumuladas['propina_tarjeta'].sum()) if 'propina_tarjeta' in ventas_acumuladas.columns else 0.0
        prop_vales = float(ventas_acumuladas['propina_vales'].sum()) if 'propina_vales' in ventas_acumuladas.columns else 0.0
        tarjeta_ventas = base_tarjeta + prop_tarjeta + prop_vales

    ventas_totales_con_propinas = efectivo_ventas + tarjeta_ventas

    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.metric("VENTAS TOTALES (Inc. Propinas)", f"${ventas_totales_con_propinas:,.2f}")
    with col_d2:
        st.metric("VENTAS EFECTIVO (Inc. Propina)", f"${efectivo_ventas:,.2f}")
    with col_d3:
        st.metric("VENTAS TERMINALES (Inc. Propinas)", f"${tarjeta_ventas:,.2f}")

    st.markdown("#### Desglose de Gastos y Nómina")
    nomina_personal_fijo = float(gasto_previo.nomina_personal_fijo) if gasto_previo else 4483.66
    total_gastos_nomina = nomina_personal_fijo + nomina_chicas_calc + gasto_cocina + gasto_compras + gasto_vales

    tabla_gastos = pd.DataFrame([
        {"Concepto": "Nómina - Personal (P)", "Monto": nomina_personal_fijo},
        {"Concepto": "Nómina - Chicas (CH)", "Monto": nomina_chicas_calc},
        {"Concepto": "Cocina", "Monto": gasto_cocina},
        {"Concepto": "Compras", "Monto": gasto_compras},
        {"Concepto": "Vales", "Monto": gasto_vales},
        {"Concepto": "TOTAL GASTOS / NÓMINA", "Monto": total_gastos_nomina}
    ])
    st.dataframe(tabla_gastos, use_container_width=True)