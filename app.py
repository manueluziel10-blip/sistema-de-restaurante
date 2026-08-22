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
    if 'BOONS ARTISTA' in p:
        return 700.0
    elif 'BOONS' in p:
        return 700.0
    elif 'COPA LADY' in p:
        return 100.0
    elif 'MINI STRONGBOW' in p:
        return 250.0
    elif 'VIP 15' in p or 'VIP15' in p:
        return 1000.0
    elif 'VIP30' in p:
        return 1900.0
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
    st.subheader("Personal Registrado y Catálogo de Puestos")
    empleados_df = cargar_empleados_df()
    st.dataframe(empleados_df, use_container_width=True)

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
            nuevo_sueldo_edit = st.number_input("Sueldo Base ($)", value=sueldo_sugerido, format="%.2f")

            if st.button("Actualizar Empleado"):
                actualizar_empleado(emp_a_editar, nuevo_tipo_edit, nuevo_sueldo_edit)
                st.success(f"¡Datos de {emp_a_editar} actualizados!")
                st.rerun()

    with col_der:
        st.markdown("### Agregar Empleado Manual")
        with st.form("form_empleado"):
            nuevo_nombre = st.text_input("Nombre Completo")
            nuevo_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()))
            nuevo_sueldo = st.number_input("Sueldo Base ($)", value=PUESTOS_CATALOGO[nuevo_tipo], format="%.2f")

            if st.form_submit_button("Guardar Empleado"):
                if nuevo_nombre.strip():
                    agregar_empleado(nuevo_nombre, nuevo_tipo, nuevo_sueldo)
                    st.success("¡Guardado con éxito!")
                    st.rerun()
                else:
                    st.error("El nombre no puede estar vacío.")

# --- SECCIÓN 3: CORTE Y NÓMINA FINAL (UNIFICADO EN 2 PESTAÑAS) ---
elif opcion == "3. Corte y Nómina Final":
    st.subheader("Cálculo de Nómina Semanal por Categorías")

    tab_chicas_bailarinas, tab_general = st.tabs([
        "💃 Chicas y Bailarinas",
        "📋 Personal Operativo y General"
    ])

    empleados_df = cargar_empleados_df()
    ventas_totales = cargar_ventas_df()
    chicas_totales = cargar_chicas_df()

    # --- PESTAÑA 1: CHICAS Y BAILARINAS UNIFICADAS ---
    with tab_chicas_bailarinas:
        st.markdown("### Nómina: Chicas, Bailarinas y Detalle de Productos")
        df_grupo_chicas = empleados_df[
            empleados_df['tipo'].str.contains("Chicas / Bailarinas", case=False, na=False)
        ]

        if df_grupo_chicas.empty:
            st.info("No hay chicas o bailarinas registradas.")
        else:
            res_grupo_chicas = []
            for _, emp in df_grupo_chicas.iterrows():
                emp_id = emp['id']
                nombre = emp['nombre']
                sueldo_base = float(emp['sueldo_base'])

                penalizada = st.checkbox(
                    f"¿Aplicar mitad de comisiones (penalización) a {nombre}?",
                    key=f"pen_chicas_{emp_id}"
                )

                extras = 0.0
                boons_cant = 0.0
                copa_cant = 0.0
                strong_cant = 0.0
                vip_cant = 0.0

                if not chicas_totales.empty:
                    sus_filas = chicas_totales[chicas_totales['empleado_id'] == emp_id]
                    if not sus_filas.empty:
                        extras = float((sus_filas['comision_unitaria'] * sus_filas['cantidad']).sum())
                        
                        for _, f_prod in sus_filas.iterrows():
                            desc = str(f_prod['descripcion']).upper()
                            cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                            
                            # Validaciones exactas para evitar cruces de nombres (ej: BOONS vs BOONS ARTISTA)
                            if 'BOONS ARTISTA' in desc:
                                pass # O manejarlo si requiere columna separada, pero aquí sumamos a boons o dejamos separado
                            elif 'BOONS' in desc:
                                boons_cant += cant
                            elif 'COPA LADY' in desc:
                                copa_cant += cant
                            elif 'MINI STRONGBOW' in desc:
                                strong_cant += cant
                            elif ('VIP' in desc or 'PRIVADO' in desc) and 'ARTISTA' not in desc:
                                vip_cant += cant
                            elif 'VIP' in desc and 'ARTISTA' in desc:
                                vip_cant += cant

                if penalizada:
                    extras = extras / 2.0

                total_pagar = sueldo_base + extras
                res_grupo_chicas.append({
                    "ID": emp_id, 
                    "Nombre": nombre, 
                    "Puesto": emp['tipo'],
                    "Boons": int(boons_cant),
                    "Copa Lady": int(copa_cant),
                    "Strongbow": int(strong_cant),
                    "VIP / Privados": int(vip_cant),
                    "Sueldo Base": sueldo_base, 
                    "Comisiones": extras, 
                    "Total a Pagar": total_pagar
                })
            
            df_res_gc = pd.DataFrame(res_grupo_chicas)
            st.dataframe(df_res_gc, use_container_width=True)
            st.metric("Subtotal Nómina Chicas y Bailarinas", f"${df_res_gc['Total a Pagar'].sum():,.2f}")

    # --- PESTAÑA 2: PERSONAL GENERAL Y OPERATIVO ---
    with tab_general:
        st.markdown("### Nómina: Personal Operativo, Meseros y Gerencia")
        df_general_empleados = empleados_df[
            ~empleados_df['tipo'].str.contains("Chicas / Bailarinas", case=False, na=False)
        ]

        if df_general_empleados.empty:
            st.info("No hay personal general registrado.")
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
            st.metric("Subtotal Nómina Personal General", f"${df_res_general['Total a Pagar'].sum():,.2f}")

    st.markdown("---")
    total_chicas_g = df_res_gc['Total a Pagar'].sum() if 'df_res_gc' in locals() and not df_grupo_chicas.empty else 0
    total_gen = df_res_general['Total a Pagar'].sum() if 'df_res_general' in locals() and not df_general_empleados.empty else 0

    st.metric("💸 NÓMINA TOTAL GENERAL DE LA SEMANA", f"${(total_chicas_g + total_gen):,.2f}")

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