"""
Servidor de kiosko de asistencia para la red local.

Script de Streamlit independiente -- NO tiene login ni ninguna otra
sección del sistema, solo esta pantalla. Se levanta en un puerto fijo,
escuchando en la red (0.0.0.0), para que las PCs "comandero" conectadas
por cable puedan registrar su entrada sin poder llegar a ninguna otra
parte de la app (porque, literalmente, no existe nada más en este
servidor). Usa la misma base de datos SQLite que el programa principal
(ver database.py).
"""

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from models import cargar_catalogo_empleados, verificar_pin_empleado, registrar_asistencia

st.set_page_config(layout="centered", page_title="Registro de Asistencia")

st.title("Zully's Men's Club — Registro de Asistencia")
fecha_hoy_kiosko = datetime.now(ZoneInfo("America/Mazatlan")).strftime('%Y-%m-%d')

st.info(
    f"Fecha Activa: **{fecha_hoy_kiosko}**. Selecciona tu nombre e ingresa tu PIN de asistencia.\n"
    "* **Personal General:** Límite hasta las **6:30 PM**.\n"
    "* **Bailarinas / Chicas:** Límite hasta las **7:30 PM**."
)

empleados_activos_df = cargar_catalogo_empleados()
if not empleados_activos_df.empty:
    empleados_activos_df = empleados_activos_df[empleados_activos_df['activo'] == True]

if empleados_activos_df.empty:
    st.warning("No hay empleados activos registrados en el sistema.")
else:
    with st.form("form_kiosko_red"):
        lista_nombres_emp = sorted(empleados_activos_df['nombre'].dropna().unique().tolist())
        emp_seleccionado = st.selectbox("Selecciona tu Nombre", lista_nombres_emp)
        pin_ingresado = st.text_input("Ingresa tu Código PIN de Asistencia", type="password", max_chars=6)
        btn_registrar = st.form_submit_button("✅ Registrar mi Asistencia Ahora", type="primary")

        if btn_registrar:
            fila_emp = empleados_activos_df[empleados_activos_df['nombre'] == emp_seleccionado].iloc[0]
            emp_id = int(fila_emp['id'])
            tipo_puesto_emp = str(fila_emp['tipo'])

            if verificar_pin_empleado(emp_id, pin_ingresado):
                hora_actual_sistema = datetime.now(ZoneInfo("America/Mazatlan")).time()
                exito, estado_asignado, hora_str, error_sql = registrar_asistencia(
                    empleado_id=emp_id, nombre_emp=emp_seleccionado,
                    tipo_puesto=tipo_puesto_emp, fecha_str=fecha_hoy_kiosko,
                    hora_actual_obj=hora_actual_sistema
                )
                if exito:
                    color_est = "green" if estado_asignado == "Presente" else "orange"
                    st.markdown("### 🎉 ¡Asistencia registrada con éxito!")
                    st.markdown(f"- **Empleado:** {emp_seleccionado}")
                    st.markdown(f"- **Hora Local de Registro:** {hora_str}")
                    st.markdown(f"- **Estado Asignado:** :{color_est}[**{estado_asignado}**]")
                else:
                    st.error(f"❌ Error al guardar en la base de datos: {error_sql}")
            else:
                st.error("❌ Código PIN incorrecto o el empleado aún no tiene un PIN configurado. Pide a un administrador que te asigne uno en '2. Gestión de Empleados'.")
