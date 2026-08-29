"""
Servidor de kiosko de asistencia para la red local.

Script de Streamlit independiente -- NO tiene login ni ninguna otra
sección del sistema, solo esta pantalla. Se levanta en un puerto fijo,
escuchando en la red (0.0.0.0), para que las PCs "comandero" conectadas
por cable puedan registrar su entrada sin poder llegar a ninguna otra
parte de la app (porque, literalmente, no existe nada más en este
servidor). Usa la misma base de datos SQLite que el programa principal
(ver database.py).

El PIN se captura con un teclado numérico en pantalla (en vez de un
campo de texto normal) porque las PCs comandero son de pantalla táctil --
así no dependen de que el teclado virtual de Windows aparezca solo.
"""

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from models import cargar_catalogo_empleados, verificar_pin_empleado, registrar_asistencia

st.set_page_config(layout="centered", page_title="Registro de Asistencia")

st.title("Zully's Men's Club — Registro de Asistencia")
fecha_hoy_kiosko = datetime.now(ZoneInfo("America/Mazatlan")).strftime('%Y-%m-%d')

st.info(
    f"Fecha Activa: **{fecha_hoy_kiosko}**. Selecciona tu nombre y captura tu PIN de asistencia.\n"
    "* **Personal General:** Límite hasta las **6:30 PM**.\n"
    "* **Bailarinas / Chicas:** Límite hasta las **7:30 PM**."
)

if "pin_kiosko" not in st.session_state:
    st.session_state["pin_kiosko"] = ""

empleados_activos_df = cargar_catalogo_empleados()
if not empleados_activos_df.empty:
    empleados_activos_df = empleados_activos_df[empleados_activos_df['activo'] == True]

if empleados_activos_df.empty:
    st.warning("No hay empleados activos registrados en el sistema.")
else:
    lista_nombres_emp = sorted(empleados_activos_df['nombre'].dropna().unique().tolist())
    emp_seleccionado = st.selectbox("Selecciona tu Nombre", lista_nombres_emp)

    st.markdown("**Tu PIN:**")
    st.markdown(
        f"<h1 style='letter-spacing: 10px;'>{'●' * len(st.session_state['pin_kiosko'])}"
        f"{'○' * (6 - len(st.session_state['pin_kiosko']))}</h1>",
        unsafe_allow_html=True
    )

    filas_teclado = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["⌫", "0", "C"]]
    for fila in filas_teclado:
        cols = st.columns(3)
        for col, tecla in zip(cols, fila):
            with col:
                if st.button(tecla, use_container_width=True, key=f"tecla_{tecla}"):
                    if tecla == "⌫":
                        st.session_state["pin_kiosko"] = st.session_state["pin_kiosko"][:-1]
                    elif tecla == "C":
                        st.session_state["pin_kiosko"] = ""
                    elif len(st.session_state["pin_kiosko"]) < 6:
                        st.session_state["pin_kiosko"] += tecla
                    st.rerun()

    if st.button("✅ Registrar mi Asistencia Ahora", type="primary", use_container_width=True):
        fila_emp = empleados_activos_df[empleados_activos_df['nombre'] == emp_seleccionado].iloc[0]
        emp_id = int(fila_emp['id'])
        tipo_puesto_emp = str(fila_emp['tipo'])
        pin_ingresado = st.session_state["pin_kiosko"]

        if verificar_pin_empleado(emp_id, pin_ingresado):
            hora_actual_sistema = datetime.now(ZoneInfo("America/Mazatlan")).time()
            exito, estado_asignado, hora_str, error_sql = registrar_asistencia(
                empleado_id=emp_id, nombre_emp=emp_seleccionado,
                tipo_puesto=tipo_puesto_emp, fecha_str=fecha_hoy_kiosko,
                hora_actual_obj=hora_actual_sistema
            )
            st.session_state["pin_kiosko"] = ""
            if exito:
                color_est = "green" if estado_asignado == "Presente" else "orange"
                st.markdown("### 🎉 ¡Asistencia registrada con éxito!")
                st.markdown(f"- **Empleado:** {emp_seleccionado}")
                st.markdown(f"- **Hora Local de Registro:** {hora_str}")
                st.markdown(f"- **Estado Asignado:** :{color_est}[**{estado_asignado}**]")
            else:
                st.error(f"❌ Error al guardar en la base de datos: {error_sql}")
        else:
            st.session_state["pin_kiosko"] = ""
            st.error("❌ Código PIN incorrecto o el empleado aún no tiene un PIN configurado. Pide a un administrador que te asigne uno en '2. Gestión de Empleados'.")
