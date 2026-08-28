import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
import io
import base64
import os
from sqlalchemy import text

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm

from models import (
    cargar_empleados_df, agregar_empleado, actualizar_empleado, eliminar_empleado_por_id,
    guardar_corte_ventas, guardar_corte_chicas,
    cargar_ventas_df, cargar_chicas_df,
    guardar_gastos_del_dia, cargar_gastos_hoy, sumar_consumo_cocina_dia,
    reiniciar_base_de_datos, obtener_fechas_disponibles,
    validar_login, cargar_usuarios_df, crear_usuario, actualizar_credenciales,
    cambiar_fecha_corte, verificar_corte_bloqueado, bloquear_corte_fecha, desbloquear_corte_fecha,
    get_session, CorteVenta, ProductoChica, NominaDiaria, Asistencia,
    cargar_empleados_rango_df, cargar_chicas_rango_df, cargar_ventas_rango_df,
    obtener_penalizaciones_rango, diagnosticar_dias_rango, reparar_nomina_faltante_rango,
    verificar_pin_empleado, establecer_pin_empleado, generar_pin_aleatorio,
    agregar_empleado_catalogo, agregar_empleados_catalogo_bulk, registrar_asistencia_lista_empleados,
    exportar_base_datos_excel, importar_base_datos_excel,
    cargar_vales_df, actualizar_estado_vale, cargar_catalogo_empleados, actualizar_estatus_empleado,
    generar_vales_desde_nomina,
    agregar_producto_boutique, actualizar_producto_boutique, cargar_productos_boutique_df,
    registrar_venta_boutique, cargar_ventas_boutique_df,
    cargar_saldos_boutique_df, registrar_abono_boutique, cargar_abonos_boutique_df,
    eliminar_datos_boutique
)
from comisiones import (
    calcular_comision_chica, calcular_comision_gerencia_caja, calcular_comisiones_detalle,
    calcular_bono_dj_animador, calcular_propina_ventas_propias, CATEGORIAS_CHICAS
)

st.set_page_config(layout="wide")

PUESTOS_CATALOGO = {
    "Chicas / Bailarinas (Comisiones)": 600.0,
    "Mesero (Comisiones)": 300.0,
    "Barman (Fijo)": 300.0,
    "Seguridad (Fijo)": 500.0,
    "DJ (Fijo)": 600.0,
    "Animador (Fijo)": 400.0,
    "Gerente (Fijo)": 500.0,
    "Capitán de Mesero (Fijo)": 400.0,
    "Ayudante de Mesero (Fijo)": 300.0,
    "Cajero (Fijo)": 400.0
}

# --- MODO KIOSKO / ASISTENCIA PÚBLICA (ACCESO DIRECTO PARA EMPLEADOS) ---
query_params = st.query_params
if query_params.get("modo") == "asistencia":
    st.title("Zullys Mens Club — Registro de Asistencia")
    fecha_hoy_kiosko = datetime.now(ZoneInfo("America/Mazatlan")).strftime('%Y-%m-%d')

    st.info(f"Fecha Activa: **{fecha_hoy_kiosko}**. Selecciona tu nombre e ingresa tu PIN de asistencia.\n* **Personal General:** Límite hasta las **6:30 PM**.\n* **Bailarinas / Chicas:** Límite hasta las **7:30 PM**.")

    def registrar_asistencia_individual_publico(empleado_id, nombre_emp, tipo_puesto, fecha_str, hora_actual_obj):
        if ('CHICA' in str(tipo_puesto).upper()) or ('BAILARINA' in str(tipo_puesto).upper()):
            limite_retardo = time(19, 30, 0)
        else:
            limite_retardo = time(18, 30, 0)

        estado = "Presente" if hora_actual_obj <= limite_retardo else "Retardo"
        comentarios = f"Check-in a las {hora_actual_obj.strftime('%H:%M:%S')}"

        session = get_session()
        try:
            f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            
            session.execute(
                text("""
                INSERT INTO asistencias (empleado_id, nombre_empleado, fecha, estado, comentarios) 
                VALUES (:emp_id, :nombre_emp, :fecha, :estado, :comentarios)
                ON CONFLICT (empleado_id, fecha) 
                DO UPDATE SET estado = :estado, comentarios = :comentarios
                """),
                {"emp_id": empleado_id, "nombre_emp": nombre_emp, "fecha": f_date, "estado": estado, "comentarios": comentarios}
            )
            
            sueldo_default = PUESTOS_CATALOGO.get(tipo_puesto, 300.0)
            session.execute(
                text("""
                INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada)
                VALUES (:fecha, :emp_id, :sueldo, 0.0, 100.0, 0.0, 0.0, FALSE)
                ON CONFLICT DO NOTHING
                """),
                {"fecha": f_date, "emp_id": empleado_id, "sueldo": sueldo_default}
            )

            session.commit()
            return True, estado, hora_actual_obj.strftime('%H:%M:%S'), None
        except Exception as e:
            session.rollback()
            return False, "", "", str(e)
        finally:
            session.close()

    session_kiosko = get_session()
    empleados_activos_df = pd.DataFrame()
    try:
        res_emps = session_kiosko.execute(
            text("SELECT id, nombre, tipo FROM public.empleados")
        ).fetchall()
        if res_emps:
            empleados_activos_df = pd.DataFrame(res_emps, columns=["id", "nombre", "tipo"])
    except Exception as e:
        st.error(f"Error crítico al conectar con la base de datos: {e}")
    finally:
        session_kiosko.close()

    if not empleados_activos_df.empty:
        with st.form("form_auto_asistencia_publico"):
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
                    exito, estado_asignado, hora_str, error_sql = registrar_asistencia_individual_publico(
                        empleado_id=emp_id, nombre_emp=emp_seleccionado,
                        tipo_puesto=tipo_puesto_emp, fecha_str=fecha_hoy_kiosko,
                        hora_actual_obj=hora_actual_sistema
                    )
                    if exito:
                        color_est = "green" if estado_asignado == "Presente" else "orange"
                        st.markdown(f"### 🎉 ¡Asistencia registrada con éxito!")
                        st.markdown(f"- **Empleado:** {emp_seleccionado}")
                        st.markdown(f"- **Hora Local de Registro:** {hora_str}")
                        st.markdown(f"- **Estado Asignado:** :{color_est}[**{estado_asignado}**]")
                    else:
                        st.error(f"❌ Error al guardar en la base de datos: {error_sql}")
                else:
                    st.error("❌ Código PIN incorrecto o el empleado aún no tiene un PIN configurado. Pide a un administrador que te asigne uno en '2. Gestión de Empleados'.")
    else:
        st.warning("No hay empleados configurados en el sistema o la base de datos consultada está vacía.")

    st.stop()

# --- CONTROL DE SESIÓN Y LOGIN ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "usuario_actual" not in st.session_state:
    st.session_state["usuario_actual"] = ""
if "rol_actual" not in st.session_state:
    st.session_state["rol_actual"] = ""

if not st.session_state["autenticado"]:
    _, col_login, _ = st.columns([1, 1.2, 1])
    with col_login:
        st.title("Control de Acceso")
        st.subheader("Iniciar Sesión")

        with st.form("form_login"):
            usuario_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            btn_login = st.form_submit_button("Entrar")

            if btn_login:
                user_data = validar_login(usuario_input, pass_input)
                if user_data:
                    st.session_state["autenticado"] = True
                    if isinstance(user_data, dict):
                        st.session_state["usuario_actual"] = user_data.get("username", "admin")
                        st.session_state["rol_actual"] = user_data.get("rol", "admin")
                    else:
                        st.session_state["usuario_actual"] = getattr(user_data, "username", "admin")
                        st.session_state["rol_actual"] = getattr(user_data, "rol", "admin")

                    st.success("¡Bienvenido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

    st.stop()

col_titulo, col_sesion = st.columns([3, 1])
with col_titulo:
    st.title("Sistema Integral: Nómina, Ventas y Cierre de Caja - Restaurante")
with col_sesion:
    st.markdown(
        f"<div style='text-align:right; margin-top:1.5rem;'>Sesión activa: "
        f"<b>{st.session_state['usuario_actual']} ({st.session_state['rol_actual'].upper()})</b></div>",
        unsafe_allow_html=True,
    )
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state["autenticado"] = False
        st.session_state["usuario_actual"] = ""
        st.session_state["rol_actual"] = ""
        st.rerun()

# --- NAVEGACIÓN DE SECCIONES (BARRA LATERAL) ---
rol_actual_lower = st.session_state["rol_actual"].lower()
es_gerente = rol_actual_lower == "gerente"

if "seccion_activa" not in st.session_state:
    st.session_state["seccion_activa"] = "1. Subir Cortes Diarios (Excel)"

nombres_secciones = [
    "1. Subir Cortes Diarios (Excel)",
    "2. Gestión de Empleados",
    "Nómina del día",
    "4. Cierre de Caja (Dashboard)",
    "Registro de Vales",
    "Boutique / Tienda",
    "5. Reportes",
    "Registro de Asistencia"
]
if rol_actual_lower == "admin":
    nombres_secciones.append("6. Usuarios y Accesos")
if es_gerente:
    nombres_secciones = [
        "2. Gestión de Empleados", "Nómina del día", "4. Cierre de Caja (Dashboard)",
        "Registro de Vales", "Boutique / Tienda", "5. Reportes"
    ]
if st.session_state["seccion_activa"] not in nombres_secciones:
    st.session_state["seccion_activa"] = nombres_secciones[0]

iconos_secciones = {
    "1. Subir Cortes Diarios (Excel)": ":material/upload_file:",
    "2. Gestión de Empleados": ":material/group:",
    "Nómina del día": ":material/payments:",
    "Registro de Vales": ":material/receipt_long:",
    "Boutique / Tienda": ":material/storefront:",
    "4. Cierre de Caja (Dashboard)": ":material/dashboard:",
    "5. Reportes": ":material/analytics:",
    "Registro de Asistencia": ":material/assignment_turned_in:",
    "6. Usuarios y Accesos": ":material/admin_panel_settings:",
}

st.sidebar.markdown("---")
st.sidebar.header("Secciones")
for idx, sec in enumerate(nombres_secciones):
    activo = (st.session_state["seccion_activa"] == sec)
    if st.sidebar.button(
        sec, use_container_width=True, key=f"toolbar_btn_{idx}",
        icon=iconos_secciones.get(sec), type="primary" if activo else "secondary"
    ):
        st.session_state["seccion_activa"] = sec
        st.rerun()
st.sidebar.markdown("---")

opcion = st.session_state["seccion_activa"]

def es_chica_o_bailarina(tipo_str):
    t = str(tipo_str).upper()
    return ('CHICA' in t) or ('BAILARINA' in t)

def registrar_asistencia_individual(empleado_id, nombre_emp, tipo_puesto, fecha_str, hora_actual_obj):
    if es_chica_o_bailarina(tipo_puesto):
        limite_retardo = time(19, 30, 0)
    else:
        limite_retardo = time(18, 30, 0)

    estado = "Presente" if hora_actual_obj <= limite_retardo else "Retardo"
    comentarios = f"Check-in a las {hora_actual_obj.strftime('%H:%M:%S')}"

    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        session.execute(
            text("""
            INSERT INTO asistencias (empleado_id, nombre_empleado, fecha, estado, comentarios) 
            VALUES (:emp_id, :nombre_emp, :fecha, :estado, :comentarios)
            ON CONFLICT (empleado_id, fecha) 
            DO UPDATE SET estado = :estado, comentarios = :comentarios
            """),
            {"emp_id": empleado_id, "nombre_emp": nombre_emp, "fecha": f_date, "estado": estado, "comentarios": comentarios}
        )
        
        sueldo_default = PUESTOS_CATALOGO.get(tipo_puesto, 300.0)
        session.execute(
            text("""
            INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada)
            VALUES (:fecha, :emp_id, :sueldo, 0.0, 100.0, 0.0, 0.0, FALSE)
            ON CONFLICT DO NOTHING
            """),
            {"fecha": f_date, "emp_id": empleado_id, "sueldo": sueldo_default}
        )

        session.commit()
        return True, estado, hora_actual_obj.strftime('%H:%M:%S'), None
    except Exception as e:
        session.rollback()
        return False, "", "", str(e)
    finally:
        session.close()

def registrar_asistencias_automaticas_dia(fecha_str):
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        empleados_activos = session.execute(
            text("SELECT id, nombre, tipo, sueldo_base FROM empleados WHERE activo = TRUE")
        ).fetchall()
        
        for emp in empleados_activos:
            emp_id = int(emp[0])
            nombre_emp = emp[1] if emp[1] else "Desconocido"
            sueldo_emp = float(emp[3]) if emp[3] is not None else 300.0

            session.execute(
                text("""
                INSERT INTO asistencias (empleado_id, nombre_empleado, fecha, estado, comentarios) 
                VALUES (:emp_id, :nombre_emp, :fecha, 'Presente', 'Automático por sistema')
                ON CONFLICT (empleado_id, fecha) DO NOTHING
                """),
                {"emp_id": emp_id, "nombre_emp": nombre_emp, "fecha": f_date}
            )

            session.execute(
                text("""
                INSERT INTO nomina_diaria (fecha, empleado_id, sueldo_base, vales_nomina, descuento_nomina, transferencia_nomina, consumo_cocina, penalizada)
                VALUES (:fecha, :emp_id, :sueldo, 0.0, 100.0, 0.0, 0.0, FALSE)
                ON CONFLICT DO NOTHING
                """),
                {"fecha": f_date, "emp_id": emp_id, "sueldo": sueldo_emp}
            )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error registrando asistencias automáticas: {e}")
    finally:
        session.close()

def obtener_mapa_asistencias(f_ini, f_fin):
    session = get_session()
    mapa = {}
    try:
        query = text("""
            SELECT empleado_id, COUNT(DISTINCT fecha) as total
            FROM asistencias
            WHERE fecha BETWEEN :f_ini AND :f_fin
            GROUP BY empleado_id
        """)
        res = session.execute(query, {"f_ini": f_ini, "f_fin": f_fin}).fetchall()
        for row in res:
            mapa[int(row[0])] = int(row[1])
    except Exception as e:
        print(f"Error al obtener mapa de asistencias: {e}")
    finally:
        session.close()
    return mapa

def limpiar_cortes_dia(fecha_str):
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        session.query(CorteVenta).filter(CorteVenta.fecha == f_date).delete()
        session.query(ProductoChica).filter(ProductoChica.fecha == f_date).delete()
        session.query(NominaDiaria).filter(NominaDiaria.fecha == f_date).delete()
        session.execute(text("DELETE FROM asistencias WHERE fecha = :fecha AND comentarios LIKE 'Automático%'"), {"fecha": f_date})
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def generar_pdf_corte(fecha_str, ventas_t, efectivo_v, tarjeta_v, transferencia_v, cobrar_v, efectivo_entregado, utilidad_m, nomina_p, nomina_ch, g_cocina, g_compras, g_vales, total_gastos, df_ventas_meseros, df_empleados_pdf, df_chicas_pdf):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    story = []
    
    PRIMARY_COLOR = colors.HexColor("#111827")
    ALT_BG = colors.HexColor("#F9FAFB")
    BORDER_COLOR = colors.HexColor("#E5E7EB")
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=PRIMARY_COLOR, alignment=0, fontName='Helvetica-Bold', spaceAfter=2)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Heading2'], fontSize=9, textColor=colors.HexColor("#6B7280"), alignment=0, fontName='Helvetica', spaceAfter=0)
    section_heading = ParagraphStyle('SectionHeading', parent=styles['Heading3'], fontSize=11, textColor=PRIMARY_COLOR, fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=6)
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor("#374151"))
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=PRIMARY_COLOR)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=colors.whitesmoke)

    ruta_logo = "LogoSinBailarina.png"
    if os.path.exists(ruta_logo):
        try:
            with open(ruta_logo, "rb") as image_file:
                img_bytes = image_file.read()
            logo_flowable = Image(io.BytesIO(img_bytes), width=110, height=42)
        except Exception:
            logo_flowable = Paragraph("<b>[ZULLYS]</b>", cell_style)
    else:
        logo_flowable = Paragraph("<b>[ZULLYS]</b>", cell_style)

    texto_cabecera = [
        Paragraph("ZULLYS MENS CLUB", title_style),
        Paragraph(f"REPORTE GENERAL DE CIERRE DE CAJA — FECHA: {fecha_str}", subtitle_style)
    ]

    tabla_header = Table([[logo_flowable, texto_cabecera]], colWidths=[120, 410])
    tabla_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    story.append(tabla_header)
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceBefore=6, spaceAfter=10))

    story.append(Paragraph("1. Resumen Financiero y Operativo", section_heading))
    
    data_finanzas = [
        [Paragraph("<b>Concepto Financiero</b>", cell_header), Paragraph("<b>Monto</b>", cell_header)],
        [Paragraph("Ventas Totales (con propinas)", cell_style), Paragraph(f"${ventas_t:,.2f}", cell_style)],
        [Paragraph("Ventas en Efectivo", cell_style), Paragraph(f"${efectivo_v:,.2f}", cell_style)],
        [Paragraph("Ventas en Terminales / Tarjeta", cell_style), Paragraph(f"${tarjeta_v:,.2f}", cell_style)],
        [Paragraph("Ventas en Transferencias / Vales", cell_style), Paragraph(f"${transferencia_v:,.2f}", cell_style)],
        [Paragraph("Ventas Por Cobrar", cell_style), Paragraph(f"${cobrar_v:,.2f}", cell_style)],
        [Paragraph("<b>Efectivo Entregado</b>", cell_bold), Paragraph(f"<b>${efectivo_entregado:,.2f}</b>", cell_bold)],
        [Paragraph("<b>Utilidad Antes de Costos</b>", cell_bold), Paragraph(f"<b>${utilidad_m:,.2f}</b>", cell_bold)]
    ]
    
    data_gastos_pdf = [
        [Paragraph("<b>Desglose de Gastos y Nómina</b>", cell_header), Paragraph("<b>Monto</b>", cell_header)],
        [Paragraph("Nómina Personal Operativo", cell_style), Paragraph(f"${nomina_p:,.2f}", cell_style)],
        [Paragraph("Nómina Comisiones Bailarinas / Chicas", cell_style), Paragraph(f"${nomina_ch:,.2f}", cell_style)],
        [Paragraph("Gastos de Cocina", cell_style), Paragraph(f"${g_cocina:,.2f}", cell_style)],
        [Paragraph("Gastos de Compras", cell_style), Paragraph(f"${g_compras:,.2f}", cell_style)],
        [Paragraph("Vales / Otros Gastos", cell_style), Paragraph(f"${g_vales:,.2f}", cell_style)],
        [Paragraph("<b>TOTAL GASTOS / NÓMINA</b>", cell_bold), Paragraph(f"<b>${total_gastos:,.2f}</b>", cell_bold)]
    ]

    t_fin = Table(data_finanzas, colWidths=[160, 95])
    t_fin.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
    ]))

    t_gas = Table(data_gastos_pdf, colWidths=[160, 95])
    t_gas.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
    ]))

    tabla_doble = Table([[t_fin, t_gas]], colWidths=[265, 265])
    tabla_doble.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    
    story.append(tabla_doble)
    story.append(Spacer(1, 10))

    story.append(Paragraph("2. Resumen de Ventas por Mesero", section_heading))
    if not df_ventas_meseros.empty:
        header_m = [Paragraph("<b>Mesero</b>", cell_header), Paragraph("<b>Efectivo</b>", cell_header), Paragraph("<b>Tarjeta</b>", cell_header), Paragraph("<b>Transf.</b>", cell_header), Paragraph("<b>Por Cobrar</b>", cell_header), Paragraph("<b>Total</b>", cell_header)]
        rows_m = [header_m]
        for _, rm in df_ventas_meseros.iterrows():
            ef = rm['efectivo'] + rm['propina_efectivo']
            tj = rm['tarjeta'] + rm['propina_tarjeta']
            tr = rm['vales'] + rm['propina_vales']
            cb = rm['otros'] + rm['propinacredito']
            tot = rm['importe_total']
            rows_m.append([
                Paragraph(str(rm['nombre']), cell_style),
                Paragraph(f"${ef:,.2f}", cell_style),
                Paragraph(f"${tj:,.2f}", cell_style),
                Paragraph(f"${tr:,.2f}", cell_style),
                Paragraph(f"${cb:,.2f}", cell_style),
                Paragraph(f"<b>${tot:,.2f}</b>", cell_bold)
            ])
        t_mes = Table(rows_m, colWidths=[120, 80, 80, 80, 80, 90])
        t_mes.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ]))
        story.append(t_mes)
    else:
        story.append(Paragraph("No hay registros de ventas de meseros en esta fecha.", cell_style))
    
    story.append(Spacer(1, 10))

    story.append(Paragraph("3. Control de Bailarinas / Chicas (Sueldos y Penalizaciones)", section_heading))
    if not df_empleados_pdf.empty:
        df_chicas_only = df_empleados_pdf[df_empleados_pdf['tipo'].apply(es_chica_o_bailarina)]
        if not df_chicas_only.empty:
            header_ch = [
                Paragraph("<b>Bailarina / Chica</b>", cell_header), 
                Paragraph("<b>Sueldo Base</b>", cell_header), 
                Paragraph("<b>Penalizada (Multa)</b>", cell_header), 
                Paragraph("<b>Descuento</b>", cell_header)
            ]
            rows_ch = [header_ch]
            for _, rc in df_chicas_only.iterrows():
                multa_txt = "SÍ (50% Comisiones)" if bool(rc.get('penalizada', False)) else "NO"
                rows_ch.append([
                    Paragraph(str(rc['nombre']), cell_style),
                    Paragraph(f"${float(rc['sueldo_base']):,.2f}", cell_style),
                    Paragraph(multa_txt, cell_style),
                    Paragraph(f"${float(rc.get('descuento_nomina', 100.0)):,.2f}", cell_style)
                ])
            t_ch = Table(rows_ch, colWidths=[160, 120, 130, 120])
            t_ch.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]),
                ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
            ]))
            story.append(t_ch)
        else:
            story.append(Paragraph("No hay registros de bailarinas registradas.", cell_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


# --- TICKETS DE NÓMINA PARA IMPRESORA TÉRMICA (80mm) ---
TICKET_ANCHO = 80 * mm
TICKET_MARGEN = 3 * mm
TICKET_MARGEN_SUPERIOR = 1 * mm
PRODUCTOS_TICKET_GERENCIA = ["COPA", "MINI", "JARRA IMP", "BOONS", "ESPECIAL", "CHANDON", "MOET"]


def _estilos_ticket():
    styles = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle('TicketTitulo', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, alignment=1, leading=13),
        "nombre": ParagraphStyle('TicketNombre', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, alignment=1, leading=13),
        "subtitulo": ParagraphStyle('TicketSubtitulo', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1, leading=10),
        "etiqueta": ParagraphStyle('TicketEtiqueta', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10),
        "etiqueta_b": ParagraphStyle('TicketEtiquetaBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10),
        "etiqueta_d": ParagraphStyle('TicketEtiquetaDestacada', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=13),
        "monto": ParagraphStyle('TicketMonto', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=2),
        "monto_b": ParagraphStyle('TicketMontoBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=2),
        "monto_d": ParagraphStyle('TicketMontoDestacado', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=13, alignment=2),
        "cant": ParagraphStyle('TicketCantidad', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1),
        "cant_header": ParagraphStyle('TicketCantidadHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=1),
    }


def _tabla_ticket(filas, estilos):
    """filas: lista de (etiqueta, cantidad_str, monto_str, estilo) -> Table
    de 3 columnas angosta para 80mm (concepto | cant. | monto), con una fila
    de encabezado "CANT." arriba y una línea separadora bajo cada concepto.
    estilo: "normal" | "negrita" (TOTAL/VALE) | "destacado" (EFECTIVO, con
    fondo y recuadro para que resalte más)."""
    data = [[Paragraph("", estilos["etiqueta_b"]), Paragraph("CANT.", estilos["cant_header"]), Paragraph("MONTO", estilos["monto_b"])]]
    filas_destacadas = []
    for idx, (etiqueta, cant_str, monto_str, estilo) in enumerate(filas):
        if estilo == "destacado":
            est_e, est_m = estilos["etiqueta_d"], estilos["monto_d"]
            filas_destacadas.append(idx + 1)
        elif estilo == "negrita":
            est_e, est_m = estilos["etiqueta_b"], estilos["monto_b"]
        else:
            est_e, est_m = estilos["etiqueta"], estilos["monto"]
        data.append([Paragraph(etiqueta, est_e), Paragraph(cant_str, estilos["cant"]), Paragraph(monto_str, est_m)])

    tabla = Table(data, colWidths=[36 * mm, 10 * mm, 26 * mm])
    estilo_tabla = [
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
    ]
    for idx in filas_destacadas:
        estilo_tabla += [
            ('BACKGROUND', (0, idx), (-1, idx), colors.HexColor("#EDEDED")),
            ('LINEABOVE', (0, idx), (-1, idx), 1.0, colors.black),
            ('LINEBELOW', (0, idx), (-1, idx), 1.0, colors.black),
            ('TOPPADDING', (0, idx), (-1, idx), 4),
            ('BOTTOMPADDING', (0, idx), (-1, idx), 4),
        ]
    tabla.setStyle(TableStyle(estilo_tabla))
    return tabla


def _encabezado_ticket(subtitulo, fecha_str, estilos):
    return [
        Paragraph("ZULLY'S MEN'S CLUB", estilos["titulo"]),
        Paragraph(subtitulo, estilos["nombre"]),
        Paragraph(fecha_str, estilos["subtitulo"]),
        Spacer(1, 3 * mm),
    ]


def _flowables_ticket_chica(fila, fecha_str, estilos, folios_vale=""):
    """Ticket de Bailarinas y Chicas: sueldo + una línea por categoría de
    producto + descuento/multa (restados ANTES del total) + vale/transferencia
    (restados del total para dar el efectivo) + cocina informativa."""
    nombre = fila["Nombre"]
    sueldo = float(fila["Sueldo Base"])
    descuento = float(fila["Descuento"])
    multa = float(fila.get("Multa", 0.0))
    vale = float(fila["Vales"])
    transferencia = float(fila["Transferencia"])
    cocina = float(fila["Cocina"])

    filas_prod = []
    bruto = sueldo
    for cat in CATEGORIAS_CHICAS:
        cant = fila.get(f"_{cat}_cant", 0.0)
        monto = fila.get(f"_{cat}_m", 0.0)
        bruto += monto
        filas_prod.append((cat.upper(), str(int(cant)), f"${monto:,.2f}", "normal"))

    total = bruto - descuento - multa
    efectivo = total - vale - transferencia
    etiqueta_vale = f"VALE ({folios_vale})" if folios_vale else "VALE"

    filas = [("SUELDO", "", f"${sueldo:,.2f}", "normal")] + filas_prod + [
        ("DESCUENTO", "", f"-${descuento:,.2f}", "normal"),
        ("MULTA", "", f"-${multa:,.2f}", "normal"),
        ("TOTAL", "", f"${total:,.2f}", "negrita"),
        (etiqueta_vale, "", f"-${vale:,.2f}", "negrita"),
        ("TRANSFERENCIA", "", f"-${transferencia:,.2f}", "normal"),
        ("EFECTIVO", "", f"${efectivo:,.2f}", "destacado"),
        ("COCINA", "", f"-${cocina:,.2f}", "normal"),
    ]
    return _encabezado_ticket(nombre, fecha_str, estilos) + [_tabla_ticket(filas, estilos)]


def _flowables_ticket_simple(fila, fecha_str, estilos, propina, comision_cant, comision_monto, folios_vale=""):
    """Ticket de Mesero, Ayudante de Mesero, Seguridad, DJ y Animador: sin
    desglose de producto, solo sueldo + propina/comisión + deducciones."""
    nombre = fila["Nombre"]
    puesto = fila["Puesto"]
    sueldo = float(fila["Sueldo Base"])
    vale = float(fila["Vales"])
    transferencia = float(fila["Transferencia"])
    retencion = float(fila.get("Retención", 0.0))
    cocina = float(fila["Cocina"])

    total = sueldo + propina + comision_monto
    efectivo = total - transferencia - vale - retencion
    etiqueta_vale = f"VALE ({folios_vale})" if folios_vale else "VALE"

    filas = [
        ("SUELDO", "", f"${sueldo:,.2f}", "normal"),
        ("PROPINA", "", f"${propina:,.2f}", "normal"),
        ("COMISIÓN", str(int(comision_cant)), f"${comision_monto:,.2f}", "normal"),
        ("TOTAL", "", f"${total:,.2f}", "negrita"),
        ("TRANSFERENCIA", "", f"-${transferencia:,.2f}", "normal"),
        (etiqueta_vale, "", f"-${vale:,.2f}", "negrita"),
        ("RETENCIÓN", "", f"-${retencion:,.2f}", "normal"),
        ("EFECTIVO", "", f"${efectivo:,.2f}", "destacado"),
        ("COCINA", "", f"-${cocina:,.2f}", "normal"),
    ]
    return _encabezado_ticket(f"{nombre} — {puesto}", fecha_str, estilos) + [_tabla_ticket(filas, estilos)]


def _desglose_productos_gerencia(chicas_totales_dia):
    """Cantidad y monto de cada uno de los 7 productos del ticket de
    Capitán/Gerente/Cajero, calculados igual que ya calcula 'comisiones_prod'
    en procesar_grupo_general: sobre el total de productos vendidos en el bar
    ese día (no por empleado), usando calcular_comision_gerencia_caja."""
    resultado = {p: {"cant": 0.0, "monto": 0.0} for p in PRODUCTOS_TICKET_GERENCIA}
    if chicas_totales_dia is None or chicas_totales_dia.empty:
        return resultado
    for _, fila_prod in chicas_totales_dia.iterrows():
        desc = str(fila_prod['descripcion']).upper()
        cant = float(fila_prod['cantidad']) if pd.notna(fila_prod['cantidad']) else 0.0
        for etiqueta in PRODUCTOS_TICKET_GERENCIA:
            if etiqueta in desc:
                resultado[etiqueta]["cant"] += cant
                resultado[etiqueta]["monto"] += cant * calcular_comision_gerencia_caja(desc)
                break
    return resultado


def _flowables_ticket_gerencia(fila, fecha_str, estilos, propina, productos_dia, folios_vale=""):
    """Ticket de Capitán de Mesero, Gerente y Cajero: sueldo + las 7 líneas
    fijas de producto + propina."""
    nombre = fila["Nombre"]
    puesto = fila["Puesto"]
    sueldo = float(fila["Sueldo Base"])
    vale = float(fila["Vales"])
    transferencia = float(fila["Transferencia"])
    retencion = float(fila.get("Retención", 0.0))
    cocina = float(fila["Cocina"])

    filas_prod = []
    suma_prod = 0.0
    for etiqueta in PRODUCTOS_TICKET_GERENCIA:
        cant = productos_dia[etiqueta]["cant"]
        monto = productos_dia[etiqueta]["monto"]
        suma_prod += monto
        filas_prod.append((etiqueta, str(int(cant)), f"${monto:,.2f}", "normal"))

    total = sueldo + suma_prod + propina
    efectivo = total - transferencia - vale - retencion
    etiqueta_vale = f"VALE ({folios_vale})" if folios_vale else "VALE"

    filas = [("SUELDO", "", f"${sueldo:,.2f}", "normal")] + filas_prod + [
        ("PROPINA", "", f"${propina:,.2f}", "normal"),
        ("TOTAL", "", f"${total:,.2f}", "negrita"),
        ("TRANSFERENCIA", "", f"-${transferencia:,.2f}", "normal"),
        (etiqueta_vale, "", f"-${vale:,.2f}", "negrita"),
        ("RETENCIÓN", "", f"-${retencion:,.2f}", "normal"),
        ("EFECTIVO", "", f"${efectivo:,.2f}", "destacado"),
        ("COCINA", "", f"-${cocina:,.2f}", "normal"),
    ]
    return _encabezado_ticket(f"{nombre} — {puesto}", fecha_str, estilos) + [_tabla_ticket(filas, estilos)]


def _folios_vale_dia(vales_dia_df, empleado_id):
    """Folios del historial de Registro de Vales de un empleado para la
    fecha ya cargada en vales_dia_df, unidos con coma (vacío si no hay
    ninguno todavía, ej. si el corte no se ha cerrado)."""
    if vales_dia_df is None or vales_dia_df.empty or "empleado_id" not in vales_dia_df.columns:
        return ""
    filas = vales_dia_df[vales_dia_df["empleado_id"] == empleado_id]
    if filas.empty:
        return ""
    return ", ".join(sorted(filas["folio"].tolist()))


def _flowables_ticket_general_dispatch(fila, fecha_str, estilos, productos_dia_gerencia, folios_vale=""):
    """Elige el formato de ticket (simple o de gerencia) según el puesto de
    la fila — para grupos como 'Personal General y Fijo' que mezclan roles."""
    tipo_up = str(fila["Puesto"]).upper()
    propina = float(fila.get("_propinas_num", 0.0))
    comision_monto = float(fila.get("Comisiones", 0.0))
    if any(p in tipo_up for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
        return _flowables_ticket_gerencia(fila, fecha_str, estilos, propina, productos_dia_gerencia, folios_vale)
    return _flowables_ticket_simple(fila, fecha_str, estilos, propina, 0, comision_monto, folios_vale)


def generar_pdf_tickets(lista_flowables_por_ticket, alto_pagina_mm=160):
    """lista_flowables_por_ticket: lista de listas de flowables (una por
    ticket). Un solo PDF a 80mm de ancho, un ticket por página."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=(TICKET_ANCHO, alto_pagina_mm * mm),
        leftMargin=TICKET_MARGEN, rightMargin=TICKET_MARGEN,
        topMargin=TICKET_MARGEN_SUPERIOR, bottomMargin=TICKET_MARGEN
    )
    story = []
    for idx, flowables_ticket in enumerate(lista_flowables_por_ticket):
        if idx > 0:
            story.append(PageBreak())
        story.extend(flowables_ticket)
    doc.build(story)
    buffer.seek(0)
    return buffer


# --- MENÚ LATERAL: CONTROL DE FECHA ---
st.sidebar.header("Menú de Control")

fechas_disponibles = obtener_fechas_disponibles()
hoy_str = datetime.now(ZoneInfo("America/Mazatlan")).strftime('%Y-%m-%d')

if rol_actual_lower in ["admin", "cajero", "gerente"]:
    opciones_modo_fecha = ["📅 Día Actual", "🔍 Buscar Corte Histórico"] if es_gerente else ["📅 Día Actual / Nuevo Corte", "🔍 Buscar Corte Histórico"]
    modo_fecha = st.sidebar.radio("Modo de Operación", opciones_modo_fecha)
    fecha_activa_obj = None
    if modo_fecha == "🔍 Buscar Corte Histórico":
        if fechas_disponibles:
            fecha_activa_obj = st.sidebar.selectbox("Selecciona la fecha del reporte", fechas_disponibles)
            st.sidebar.warning(f"⚠️ Visualizando histórico: {fecha_activa_obj}")
        else:
            st.sidebar.info("No hay cortes históricos registrados aún.")
            fecha_activa_obj = datetime.now(ZoneInfo("America/Mazatlan")).strftime('%Y-%m-%d')
    elif es_gerente:
        fecha_activa_obj = datetime.now(ZoneInfo("America/Mazatlan")).date()
    else:
        if "fecha_corte_confirmada" not in st.session_state:
            st.session_state["fecha_corte_confirmada"] = datetime.now(ZoneInfo("America/Mazatlan")).date()

        fecha_seleccionada = st.sidebar.date_input(
            "Fecha para el Corte Actual",
            value=st.session_state["fecha_corte_confirmada"],
            key="fecha_corte_actual_picker"
        )
        if fecha_seleccionada != st.session_state["fecha_corte_confirmada"]:
            st.sidebar.warning(f"Fecha elegida: {fecha_seleccionada}. Presiona **Confirmar fecha** para aplicarla.")
            if st.sidebar.button("✅ Confirmar fecha", use_container_width=True):
                st.session_state["fecha_corte_confirmada"] = fecha_seleccionada
                st.rerun()

        fecha_activa_obj = st.session_state["fecha_corte_confirmada"]
else:
    fecha_activa_obj = datetime.now(ZoneInfo("America/Mazatlan")).date()
    st.sidebar.info(f"Fecha de Operación: **{fecha_activa_obj.strftime('%Y-%m-%d')}**")

fecha_activa = fecha_activa_obj.strftime('%Y-%m-%d') if hasattr(fecha_activa_obj, 'strftime') else str(fecha_activa_obj)
es_dia_actual = (fecha_activa == hoy_str)

# --- GESTIÓN DE ESTADO: ABRIR, CERRAR Y MODIFICAR CORTE ---
st.sidebar.markdown("---")
st.sidebar.subheader("🔒 Estado del Corte")

corte_esta_bloqueado = verificar_corte_bloqueado(fecha_activa)

if corte_esta_bloqueado:
    st.sidebar.error(f"El corte del {fecha_activa} está **CERRADO**.")
    if rol_actual_lower == "admin":
        if st.sidebar.button("🔓 Abrir / Desbloquear Corte", key="btn_abrir_corte"):
            desbloquear_corte_fecha(fecha_activa)
            st.sidebar.success(f"¡Corte del {fecha_activa} abierto correctamente!")
            st.rerun()
    else:
        st.sidebar.info("Corte cerrado (Solo lectura). Contacte al administrador.")
else:
    st.sidebar.success(f"El corte del {fecha_activa} está **ABIERTO**.")
    if rol_actual_lower in ["admin", "cajero"]:
        if st.sidebar.button("🔒 Cerrar Corte Actual", key="btn_cerrar_corte"):
            generar_vales_desde_nomina(fecha_activa)
            bloquear_corte_fecha(fecha_activa, st.session_state["usuario_actual"])
            st.sidebar.warning(f"¡Corte del {fecha_activa} cerrado y bloqueado!")
            st.rerun()

if rol_actual_lower == "admin":
    puede_modificar = not corte_esta_bloqueado
elif es_gerente:
    puede_modificar = False
else:
    puede_modificar = es_dia_actual and (not corte_esta_bloqueado)

if not es_gerente:
    # --- RESPALDO DE BASE DE DATOS (EXPORTAR / IMPORTAR) ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Respaldo de Base de Datos")

    try:
        buffer_respaldo = exportar_base_datos_excel()
        st.sidebar.download_button(
            label="📥 Descargar Respaldo Completo (Excel)",
            data=buffer_respaldo,
            file_name=f"Respaldo_ZullysDB_{datetime.now(ZoneInfo('America/Mazatlan')).strftime('%Y-%m-%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Descarga TODAS las tablas (empleados, ventas, comisiones, nómina, asistencias, usuarios) en un solo Excel."
        )
    except Exception as e:
        st.sidebar.error(f"No se pudo generar el respaldo: {e}")

    if "mostrar_form_restaurar" not in st.session_state:
        st.session_state["mostrar_form_restaurar"] = False

    if not st.session_state["mostrar_form_restaurar"]:
        if st.sidebar.button("📤 Restaurar desde Respaldo"):
            st.session_state["mostrar_form_restaurar"] = True
            st.rerun()
    else:
        with st.sidebar.form("form_confirmar_restaurar"):
            st.warning(
                "⚠️ Esto REEMPLAZA TODOS los datos actuales (empleados, ventas, "
                "comisiones, nóminas, usuarios) con lo que traiga el archivo. "
                "Úsalo para recuperar un respaldo después de un reinicio."
            )
            archivo_restaurar = st.file_uploader("Sube el archivo de respaldo (.xlsx)", type=["xlsx"], key="subir_respaldo_restaurar")
            pass_admin_restaurar = st.text_input("Contraseña de Admin", type="password", key="pass_admin_restaurar")
            texto_confirmacion_restaurar = st.text_input('Escribe exactamente "RESTAURAR" para confirmar', key="texto_confirmar_restaurar")
            confirmar_check_restaurar = st.checkbox("Entiendo que esto reemplaza todos los datos actuales", key="check_confirmar_restaurar")

            col_r1, col_r2 = st.columns(2)
            btn_ejecutar_restaurar = col_r1.form_submit_button("Sí, Restaurar")
            btn_cancelar_restaurar = col_r2.form_submit_button("Cancelar")

            if btn_ejecutar_restaurar:
                if archivo_restaurar is None:
                    st.error("Sube un archivo de respaldo primero.")
                elif not confirmar_check_restaurar or texto_confirmacion_restaurar.strip() != "RESTAURAR":
                    st.error('Marca la casilla y escribe exactamente "RESTAURAR" para continuar.')
                else:
                    usuario_actual_limpio = st.session_state["usuario_actual"].strip().lower()
                    user_val = validar_login(usuario_actual_limpio, pass_admin_restaurar)
                    if not user_val and usuario_actual_limpio == "admin":
                        user_val = validar_login("admin", pass_admin_restaurar)

                    if user_val and user_val.get("rol") == "admin":
                        try:
                            resultado_restaurar = importar_base_datos_excel(archivo_restaurar)
                            resumen_restaurar = ", ".join(f"{k}: {v}" for k, v in resultado_restaurar.items())
                            st.session_state["mostrar_form_restaurar"] = False
                            st.sidebar.success(f"¡Base de datos restaurada! {resumen_restaurar}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al restaurar: {e}")
                    else:
                        st.error("Contraseña incorrecta o permisos insuficientes.")

            if btn_cancelar_restaurar:
                st.session_state["mostrar_form_restaurar"] = False
                st.rerun()

    # --- ZONA DE PELIGRO EN BARRA LATERAL ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚠️ Zona de Peligro")

    if "mostrar_form_reinicio" not in st.session_state:
        st.session_state["mostrar_form_reinicio"] = False

    if not st.session_state["mostrar_form_reinicio"]:
        if st.sidebar.button("🗑️ Reiniciar Base de Datos"):
            st.session_state["mostrar_form_reinicio"] = True
            st.rerun()
    else:
        with st.sidebar.form("form_confirmar_reinicio"):
            st.warning("⚠️ Esta acción borrará TODO (empleados, ventas, comisiones, nóminas, usuarios). No se puede deshacer.")
            pass_admin = st.text_input("Contraseña de Admin", type="password")
            texto_confirmacion = st.text_input('Escribe exactamente "BORRAR TODO" para confirmar')
            confirmar_check = st.checkbox("Entiendo que esta acción es irreversible")
        
            col_f1, col_f2 = st.columns(2)
            btn_ejecutar = col_f1.form_submit_button("Sí, Borrar")
            btn_cancelar = col_f2.form_submit_button("Cancelar")
        
            if btn_ejecutar:
                if confirmar_check and texto_confirmacion.strip() == "BORRAR TODO":
                    usuario_actual_limpio = st.session_state["usuario_actual"].strip().lower()
                    user_val = validar_login(usuario_actual_limpio, pass_admin)
                    if not user_val and usuario_actual_limpio == "admin":
                        user_val = validar_login("admin", pass_admin)

                    if user_val and user_val.get("rol") == "admin":
                        reiniciar_base_de_datos()
                        st.session_state["mostrar_form_reinicio"] = False
                        st.sidebar.success("¡Base de datos limpiada con éxito!")
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta o permisos insuficientes.")
                elif not confirmar_check:
                    st.error("Debes marcar la casilla de confirmación.")
                else:
                    st.error('Debes escribir exactamente "BORRAR TODO" para continuar.')
        
            if btn_cancelar:
                st.session_state["mostrar_form_reinicio"] = False
                st.rerun()

st.markdown("---")

# --- SECCIÓN 1: SUBIR ARCHIVOS DIARIOS ---
if opcion == "1. Subir Cortes Diarios (Excel)":
    st.subheader(f"Carga de Archivos Diarios para la fecha: {fecha_activa}")
    if not puede_modificar:
        st.warning("🔒 Modo de solo lectura: El corte está cerrado o es histórico.")
    else:
        st.info("Sube los archivos correspondientes al corte del día seleccionado.")
        
        if "mostrar_form_borrar_dia" not in st.session_state:
            st.session_state["mostrar_form_borrar_dia"] = False

        if not st.session_state["mostrar_form_borrar_dia"]:
            if st.button("🗑️ Borrar / Restablecer Todo el Corte de este Día", type="secondary"):
                st.session_state["mostrar_form_borrar_dia"] = True
                st.rerun()
        else:
            with st.form("form_confirmar_borrar_dia"):
                st.warning(f"⚠️ ¿Estás seguro de eliminar todas las ventas y registros de este día?")
                conf_borrar = st.checkbox("Sí, deseo borrar toda la información de este día")
                
                col_b1, col_b2 = st.columns(2)
                btn_ejec_borrar = col_b1.form_submit_button("Confirmar Borrado")
                btn_canc_borrar = col_b2.form_submit_button("Cancelar")
                
                if btn_ejec_borrar:
                    if conf_borrar:
                        limpiar_cortes_dia(fecha_activa)
                        st.session_state["mostrar_form_borrar_dia"] = False
                        st.success(f"¡Se han eliminado todos los registros del día {fecha_activa}!")
                        st.rerun()
                    else:
                        st.error("Debes marcar la casilla de confirmación.")
                
                if btn_canc_borrar:
                    st.session_state["mostrar_form_borrar_dia"] = False
                    st.rerun()

        st.markdown("---")
        st.info(":material/group_add: ¿Buscas dar de alta personal nuevo? Se movió a **'2. Gestión de Empleados'** (pestaña 'Alta y PIN').")

        st.markdown("### 🧾 Ventas, Propinas y Comisiones")

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

            # Normaliza encabezados (quita espacios y homogeneiza mayúsculas)
            # por si el Excel exportado trae variaciones menores de formato,
            # en vez de tronar con un KeyError críptico.
            df_v.columns = [str(c).strip().lower() for c in df_v.columns]
            df_p.columns = [str(c).strip().lower() for c in df_p.columns]

            columnas_faltantes = []
            if 'idmesero' not in df_v.columns:
                columnas_faltantes.append(f"'{up_ventas.name}' (columnas encontradas: {list(df_v.columns)})")
            if 'idmesero' not in df_p.columns:
                columnas_faltantes.append(f"'{up_propinas.name}' (columnas encontradas: {list(df_p.columns)})")

            if columnas_faltantes:
                st.error(
                    "❌ No se encontró la columna 'idmesero' en: " + " | ".join(columnas_faltantes) +
                    ". Revisa que el archivo sea el reporte correcto exportado desde Soft Restaurant."
                )
            else:
                df_v['idmesero'] = pd.to_numeric(df_v['idmesero'], errors='coerce').fillna(0).astype(int)
                df_p['idmesero'] = pd.to_numeric(df_p['idmesero'], errors='coerce').fillna(0).astype(int)

                st.success("¡Archivos de ventas y propinas cargados correctamente!")
                st.dataframe(df_v.head(), width=700)

                if st.button("Guardar corte de Meseros", key="btn_guardar_corte_meseros"):
                    ids_con_actividad, filas_omitidas = guardar_corte_ventas(df_v, df_p, archivo_origen=up_ventas.name, fecha_corte=fecha_activa, usuario_nombre=st.session_state["usuario_actual"])
                    # Solo se marca asistencia a quien tuvo ventas/propinas
                    # reales ese día — no a todo el personal activo del
                    # sistema (Soft Restaurant exporta el reporte con todos
                    # los meseros/cajeros en $0 aunque no hayan trabajado).
                    registrar_asistencia_lista_empleados(ids_con_actividad, fecha_activa)
                    mensaje_omitidos = f" Se omitieron {filas_omitidas} registro(s) sin actividad (todo en $0)." if filas_omitidas else ""
                    st.toast(f"¡Corte de meseros guardado! Asistencia registrada para {len(ids_con_actividad)} persona(s) con actividad real el {fecha_activa}.{mensaje_omitidos}", icon="✅")
                    st.rerun()

        if up_chicas is not None:
            df_c = pd.read_excel(up_chicas, skiprows=4)
            st.success("¡Archivo de productos cargado!")

            if st.button("Procesar y Guardar Comisiones del Día", key="btn_guardar_chicas"):
                if len(df_c.columns) >= 5:
                    df_c.columns = ['CLAVE', 'DESCRIPCION', 'GRUPO', 'PRECIO', 'CANTIDAD'] + list(df_c.columns[5:])
                    filas_chicas = df_c[df_c['DESCRIPCION'].astype(str).str.contains('>')].copy()

                    nuevas_detectadas, ids_con_actividad = guardar_corte_chicas(
                        filas_chicas, calcular_comision_chica, archivo_origen=up_chicas.name, fecha_corte=fecha_activa, usuario_nombre=st.session_state["usuario_actual"]
                    )
                    registrar_asistencia_lista_empleados(ids_con_actividad, fecha_activa)
                    st.toast(f"¡Corte procesado y asistencias registradas! Se registraron {len(nuevas_detectadas)} personas nuevas.", icon="✅")
                    st.rerun()
                else:
                    st.error("El archivo no tiene el formato esperado.")

# --- SECCIÓN 2: GESTIÓN Y EDICIÓN DE EMPLEADOS ---
elif opcion == "2. Gestión de Empleados":
    st.subheader(":material/group: Directorio de personal")
    st.caption("Todos los empleados dados de alta, activos e inactivos. Desactiva a quien ya no trabaja aquí en vez de borrarlo.")

    catalogo_df = cargar_catalogo_empleados()

    def tabla_directorio_empleados(df_grupo, sufijo_key):
        if df_grupo.empty:
            st.info("No hay empleados en este grupo.")
            return

        vista = df_grupo[["id", "nombre", "tipo", "sueldo_base", "activo"]].copy()
        vista.columns = ["ID", "Nombre", "Puesto", "Sueldo base", "Activo"]
        vista = vista.sort_values("Nombre").reset_index(drop=True)

        if es_gerente:
            st.dataframe(vista.drop(columns=["ID"]), hide_index=True, use_container_width=True)
            return

        version_key = f"editor_directorio_{sufijo_key}_version"
        if version_key not in st.session_state:
            st.session_state[version_key] = 0
        editor_key = f"editor_directorio_{sufijo_key}_v{st.session_state[version_key]}"

        if st.session_state.get(editor_key, {}).get("edited_rows", {}):
            st.warning("⚠️ Hay cambios sin guardar. Usa 'Descartar cambios' para regresar a los valores guardados.")

        with st.form(f"form_directorio_{sufijo_key}"):
            editado = st.data_editor(
                vista,
                hide_index=True,
                use_container_width=True,
                disabled=["ID", "Nombre", "Puesto", "Sueldo base"],
                column_config={
                    "Sueldo base": st.column_config.NumberColumn("Sueldo base ($)", format="$%.2f"),
                    "Activo": st.column_config.CheckboxColumn("Activo"),
                },
                key=editor_key
            )
            col_g, col_d = st.columns(2)
            with col_g:
                guardar = st.form_submit_button("💾 Guardar cambios", use_container_width=True)
            with col_d:
                descartar = st.form_submit_button("↩️ Descartar cambios", use_container_width=True)
        if guardar:
            with st.spinner("Guardando cambios..."):
                for _, fila in editado.iterrows():
                    original = vista[vista["ID"] == fila["ID"]].iloc[0]
                    if bool(fila["Activo"]) != bool(original["Activo"]):
                        actualizar_estatus_empleado(int(fila["ID"]), bool(fila["Activo"]))
            st.session_state[version_key] += 1
            st.success("Cambios guardados.")
            st.rerun()
        elif descartar:
            st.session_state[version_key] += 1
            st.rerun()

    if es_gerente:
        tab_gest_chicas, tab_gest_general = st.tabs([
            "Bailarinas y chicas de salón",
            "Personal operativo y general"
        ])
        tab_alta_pin = None
        tab_exportar = None
    else:
        tab_gest_chicas, tab_gest_general, tab_alta_pin, tab_exportar = st.tabs([
            "Bailarinas y chicas de salón",
            "Personal operativo y general",
            "➕ Alta y PIN",
            "📥 Exportar"
        ])
    with tab_gest_chicas:
        df_chicas_dir = catalogo_df[catalogo_df['tipo'].apply(es_chica_o_bailarina)] if not catalogo_df.empty else pd.DataFrame()
        tabla_directorio_empleados(df_chicas_dir, "chicas")
    with tab_gest_general:
        df_general_dir = catalogo_df[~catalogo_df['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina)] if not catalogo_df.empty else pd.DataFrame()
        tabla_directorio_empleados(df_general_dir, "general")

    if tab_alta_pin is not None:
        with tab_alta_pin:
            st.subheader(":material/key: Reasignar PIN de asistencia")
            if not catalogo_df.empty:
                nombres_emps_pin = catalogo_df.sort_values("nombre")["nombre"].tolist()
                emp_pin_sel = st.selectbox("Selecciona empleado", nombres_emps_pin, key="sel_emp_pin")
                emp_pin_actual = catalogo_df[catalogo_df["nombre"] == emp_pin_sel].iloc[0]
                nuevo_pin_reset = st.text_input(
                    "Nuevo PIN (4-6 dígitos)", value=generar_pin_aleatorio(),
                    max_chars=6, key="pin_reset_input"
                )
                if st.button("Guardar nuevo PIN", key="btn_pin_reset"):
                    if nuevo_pin_reset.strip():
                        establecer_pin_empleado(int(emp_pin_actual["id"]), nuevo_pin_reset.strip())
                        st.success(f"¡Nuevo PIN para {emp_pin_sel}: **{nuevo_pin_reset.strip()}** (anótalo, no se volverá a mostrar).")
                    else:
                        st.error("El PIN no puede estar vacío.")

                puesto_actual_pin = emp_pin_actual['tipo']
                with st.form("form_puesto_pin"):
                    nuevo_puesto_pin = st.selectbox(
                        "Puesto oficial", list(PUESTOS_CATALOGO.keys()),
                        index=list(PUESTOS_CATALOGO.keys()).index(puesto_actual_pin) if puesto_actual_pin in PUESTOS_CATALOGO else 0,
                    )
                    guardar_puesto_pin = st.form_submit_button("Guardar puesto")

                if guardar_puesto_pin:
                    actualizar_empleado(int(emp_pin_actual["id"]), nuevo_puesto_pin, float(emp_pin_actual["sueldo_base"]), fecha_str=fecha_activa)
                    st.success(f"¡Puesto oficial de {emp_pin_sel} actualizado a {nuevo_puesto_pin}!")
                    st.rerun()
            else:
                st.info("No hay empleados registrados todavía.")

            st.subheader(f":material/person_add: Agregar empleado manual ({fecha_activa})")
            with st.form("form_empleado"):
                nuevo_nombre = st.text_input("Nombre completo")
                nuevo_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()), key="form_puesto")
                nuevo_sueldo = st.number_input("Sueldo base ($)", value=PUESTOS_CATALOGO[nuevo_tipo], format="%.2f", key="form_sueldo_input")
                nuevo_pin = st.text_input(
                    "Código PIN de asistencia (4 dígitos, único para este empleado)",
                    value=generar_pin_aleatorio(), max_chars=6
                )

                if st.form_submit_button("Guardar empleado"):
                    if nuevo_nombre.strip():
                        agregar_empleado(nuevo_nombre, nuevo_tipo, nuevo_sueldo, fecha_str=fecha_activa, pin=nuevo_pin.strip())
                        registrar_asistencias_automaticas_dia(fecha_activa)
                        st.success(f"¡Guardado con éxito! PIN asignado a {nuevo_nombre}: **{nuevo_pin.strip()}** (anótalo, no se volverá a mostrar).")
                        st.rerun()
                    else:
                        st.error("El nombre no puede estar vacío.")

            st.subheader(":material/group_add: Alta masiva de personal (Excel)")
            st.caption(
                "Da de alta varios empleados nuevos al catálogo de una sola vez (nombre, puesto, sueldo, PIN) — "
                "útil para no capturarlos uno por uno al empezar a usar el sistema. Esto NO les registra la "
                "asistencia del día: para que un empleado aparezca en 'Nómina del día' debe registrar su entrada "
                "normalmente (Registro de Asistencia)."
            )
            with st.expander("📂 Alta Masiva por Excel", expanded=False):
                filas_plantilla = []
                for idx, (puesto, sueldo) in enumerate(PUESTOS_CATALOGO.items(), start=1):
                    filas_plantilla.append({"Nombre": f"Ejemplo Empleado {idx}", "Puesto": puesto, "Sueldo Base": sueldo, "PIN": f"100{idx}"})
                df_plantilla = pd.DataFrame(filas_plantilla)

                buffer_plantilla = io.BytesIO()
                with pd.ExcelWriter(buffer_plantilla, engine='openpyxl') as writer:
                    df_plantilla.to_excel(writer, index=False, sheet_name='Plantilla_Personal')
                buffer_plantilla.seek(0)

                st.download_button(
                    label="📥 Descargar Plantilla de Excel con Todos los Puestos y PIN",
                    data=buffer_plantilla,
                    file_name="Plantilla_Alta_Empleados_PIN.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                st.markdown("---")
                up_excel_personal = st.file_uploader("Sube tu archivo Excel de empleados", type=["xls", "xlsx"], key="subir_excel_personal")

                if up_excel_personal is not None:
                    df_subido = pd.read_excel(up_excel_personal)
                    st.dataframe(df_subido.head(), use_container_width=True)

                    if st.button("Procesar e Importar Personal"):
                        columnas_necesarias = {'Nombre', 'Puesto', 'Sueldo Base'}
                        if not columnas_necesarias.issubset(df_subido.columns):
                            st.error("El archivo Excel debe contener las columnas: Nombre, Puesto y Sueldo Base.")
                        else:
                            filas_para_importar = []
                            for _, row in df_subido.iterrows():
                                nombre_emp = str(row['Nombre']).strip()
                                puesto_emp = str(row['Puesto']).strip()
                                sueldo_emp = float(row['Sueldo Base']) if pd.notna(row['Sueldo Base']) else 0.0
                                pin_emp = str(row['PIN']).strip() if 'PIN' in df_subido.columns and pd.notna(row.get('PIN')) else None

                                if not nombre_emp:
                                    continue
                                if puesto_emp not in PUESTOS_CATALOGO:
                                    puesto_emp = "Mesero (Comisiones)"

                                filas_para_importar.append({
                                    "nombre": nombre_emp, "tipo": puesto_emp,
                                    "sueldo_base": sueldo_emp, "pin": pin_emp
                                })

                            # Una sola conexión para todo el archivo, en vez de una
                            # por cada empleado — mucho más rápido con listas largas.
                            ids_procesados = agregar_empleados_catalogo_bulk(filas_para_importar)

                            st.success(
                                f"¡Importación completada! Empleados agregados al catálogo: {len(ids_procesados)}. "
                                "Deben registrar su entrada para aparecer en la nómina del día."
                            )
                            st.rerun()

    if tab_exportar is not None:
        with tab_exportar:
            st.subheader(":material/download: Exportar alta de trabajadores")
            if catalogo_df.empty:
                st.info("No hay empleados registrados todavía.")
            else:
                df_export = catalogo_df[["id", "nombre", "tipo", "creado_en", "activo"]].copy()
                df_export.columns = ["ID", "Nombre", "Puesto", "Fecha de registro", "Activo"]
                df_export = df_export.sort_values("Nombre")

                st.dataframe(df_export, hide_index=True, use_container_width=True)

                buffer_export = io.BytesIO()
                with pd.ExcelWriter(buffer_export, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Alta_Trabajadores')
                buffer_export.seek(0)

                st.download_button(
                    label="📥 Descargar Excel de alta de trabajadores",
                    data=buffer_export,
                    file_name=f"Alta_Trabajadores_{datetime.now(ZoneInfo('America/Mazatlan')).strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# --- SECCIÓN 3: CORTE Y NÓMINA FINAL ---
elif opcion == "Nómina del día":
    st.subheader(f"Cálculo de nómina semanal por categorías — fecha: {fecha_activa}")

    tab_bailarinas, tab_meseros, tab_seguridad, tab_general = st.tabs([
        "💃 Bailarinas y Chicas",
        "👥 Meseros y Ayudantes",
        "🛡️ Seguridad",
        "📋 Personal General y Fijo"
    ])

    empleados_df = cargar_empleados_df(fecha_activa)
    ventas_totales = cargar_ventas_df(fecha_activa)
    chicas_totales = cargar_chicas_df(fecha_activa)

    def procesar_grupo_chicas(df_subgrupo, nombre_pestana, key_sufijo):
        if df_subgrupo.empty:
            st.info(f"No hay registros en {nombre_pestana} para la fecha {fecha_activa}.")
            return pd.DataFrame(), 0.0

        st.caption(":material/info: Marca la casilla junto al nombre para aplicar penalización (mitad de comisiones):")
        checkboxes_penalizacion = {}
        cols_penalizacion = st.columns(4)
        for idx_chk, (_, emp_chk) in enumerate(df_subgrupo.iterrows()):
            with cols_penalizacion[idx_chk % 4]:
                checkboxes_penalizacion[emp_chk['id']] = st.checkbox(
                    emp_chk['nombre'],
                    value=bool(emp_chk.get('penalizada', False)),
                    key=f"pen_{key_sufijo}_{emp_chk['id']}",
                    disabled=not puede_modificar
                )

        res_grupo = []
        for _, emp in df_subgrupo.iterrows():
            emp_id = emp['id']
            nombre = emp['nombre']
            sueldo_base = float(emp['sueldo_base'])
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            descuento_emp = float(emp.get('descuento_nomina', 100.0))
            cocina_emp = float(emp.get('consumo_cocina', 0.0))
            multa_emp = float(emp.get('retencion_nomina', 0.0))
            peinado_emp = float(emp.get('peinado_maquillaje', 0.0))
            dulceria_emp = float(emp.get('dulceria', 0.0))
            penalizada_actual = bool(emp.get('penalizada', False))

            penalizada_cambiada = checkboxes_penalizacion[emp_id]

            if puede_modificar and (penalizada_cambiada != penalizada_actual):
                actualizar_empleado(emp_id, emp['tipo'], sueldo_base, vales_emp, penalizada_cambiada, descuento_emp, transf_emp, cocina_emp, fecha_str=fecha_activa, nuevo_retencion=multa_emp)
                st.rerun()

            sus_filas = pd.DataFrame()
            if not chicas_totales.empty and 'empleado_id' in chicas_totales.columns:
                sus_filas = chicas_totales[chicas_totales['empleado_id'] == emp_id]

            detalle = calcular_comisiones_detalle(sus_filas, penalizada=penalizada_cambiada)
            extras = detalle["total"]

            total_bruto = sueldo_base + extras
            total_pagar = total_bruto - vales_emp - transf_emp - descuento_emp - multa_emp

            fila_resultado = {
                "ID": emp_id,
                "Nombre": nombre,
                "Puesto": emp['tipo'],
                "Total a Pagar": total_pagar,
                "Sueldo Base": sueldo_base,
                "Vales": vales_emp,
                "Transferencia": transf_emp,
                "Descuento": descuento_emp,
                "Cocina": cocina_emp,
                "Multa": multa_emp,
                "Peinado y maquillaje": peinado_emp,
                "Dulcería": dulceria_emp,
                "Comisiones": extras,
            }
            for cat in CATEGORIAS_CHICAS:
                cant = detalle[f"{cat}_cant"]
                monto = detalle[f"{cat}_monto"]
                fila_resultado[cat] = f"{int(cant)} (${monto:,.2f})"
                fila_resultado[f"_{cat}_cant"] = cant
                fila_resultado[f"_{cat}_m"] = monto

            res_grupo.append(fila_resultado)
        
        df_res = pd.DataFrame(res_grupo)
        cols_mostrar = [c for c in df_res.columns if not c.startswith("_")]
        altura_tabla = min(max(len(df_res) * 45 + 40, 150), 900)

        def resaltar_filas(row):
            return ['background-color: #1A2634; color: #FFFFFF;' if row.name % 2 == 0 else 'background-color: #141D26; color: #FFFFFF;'] * len(row)

        def pintar_negativos(val):
            if isinstance(val, (int, float)) and val < 0:
                return 'color: #FF5252; font-weight: bold;'
            return ''

        df_estilizado = df_res[cols_mostrar].style.apply(resaltar_filas, axis=1).map(pintar_negativos, subset=['Total a Pagar'])
        editor_key_base = f"editor_sueldos_{key_sufijo}"
        version_key = f"{editor_key_base}_version"
        if version_key not in st.session_state:
            st.session_state[version_key] = 0
        editor_key = f"{editor_key_base}_v{st.session_state[version_key]}"

        columnas_deshabilitadas = [c for c in cols_mostrar if c not in ["Sueldo Base", "Vales", "Transferencia", "Descuento", "Cocina", "Multa", "Peinado y maquillaje", "Dulcería"]]
        if not puede_modificar:
            columnas_deshabilitadas = cols_mostrar

        cambios_sin_guardar = st.session_state.get(editor_key, {}).get("edited_rows", {})
        if cambios_sin_guardar:
            st.warning("⚠️ Hay cambios sin guardar en esta tabla. Se pierden si cambias de pestaña sin presionar 'Guardar cambios'; usa 'Descartar cambios' para regresar a los valores guardados.")

        with st.form(f"form_nomina_{key_sufijo}"):
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
                    "Cocina": st.column_config.NumberColumn("Cocina ($)", format="$%.2f", required=True),
                    "Multa": st.column_config.NumberColumn("Multa ($)", format="$%.2f", required=True),
                    "Peinado y maquillaje": st.column_config.NumberColumn("Peinado y maquillaje ($)", format="$%.2f", required=True),
                    "Dulcería": st.column_config.NumberColumn("Dulcería ($)", format="$%.2f", required=True),
                    "Comisiones": st.column_config.NumberColumn("Comisiones ($)", format="$%.2f", disabled=True),
                },
                disabled=columnas_deshabilitadas,
                use_container_width=True,
                key=editor_key
            )
            col_guardar, col_descartar = st.columns(2)
            with col_guardar:
                guardar_nomina = st.form_submit_button("💾 Guardar cambios", disabled=not puede_modificar, use_container_width=True)
            with col_descartar:
                descartar_nomina = st.form_submit_button("↩️ Descartar cambios", use_container_width=True)

        actualizado_flag = False
        if guardar_nomina and puede_modificar and (editor_key in st.session_state):
            with st.spinner("Guardando cambios..."):
                cambios = st.session_state[editor_key].get("edited_rows", {})
                for row_idx, edits in cambios.items():
                    fila_modificada = df_res.iloc[int(row_idx)]
                    e_id = int(fila_modificada['ID'])

                    nuevo_sb = float(edits["Sueldo Base"]) if "Sueldo Base" in edits else float(fila_modificada['Sueldo Base'])
                    nuevo_vales = float(edits["Vales"]) if "Vales" in edits else float(fila_modificada['Vales'])
                    nueva_transf = float(edits["Transferencia"]) if "Transferencia" in edits else float(fila_modificada['Transferencia'])
                    nuevo_desc = float(edits["Descuento"]) if "Descuento" in edits else float(fila_modificada['Descuento'])
                    nueva_cocina = float(edits["Cocina"]) if "Cocina" in edits else float(fila_modificada['Cocina'])
                    nueva_multa = float(edits["Multa"]) if "Multa" in edits else float(fila_modificada['Multa'])
                    nuevo_peinado = float(edits["Peinado y maquillaje"]) if "Peinado y maquillaje" in edits else float(fila_modificada['Peinado y maquillaje'])
                    nueva_dulceria = float(edits["Dulcería"]) if "Dulcería" in edits else float(fila_modificada['Dulcería'])
                    puesto_emp = fila_modificada['Puesto']
                    penalizada_bd = bool(empleados_df[empleados_df['id'] == e_id]['penalizada'].values[0])

                    actualizar_empleado(
                        e_id, puesto_emp, nuevo_sb, nuevo_vales, penalizada_bd, nuevo_desc, nueva_transf, nueva_cocina,
                        fecha_str=fecha_activa, nuevo_retencion=nueva_multa,
                        nuevo_peinado_maquillaje=nuevo_peinado, nuevo_dulceria=nueva_dulceria
                    )
                    actualizado_flag = True

        if actualizado_flag:
            st.session_state[version_key] += 1
            st.toast("✅ Cambios guardados correctamente.", icon="✅")
            st.rerun()
        elif descartar_nomina:
            st.session_state[version_key] += 1
            st.rerun()

        st.subheader(":material/inventory_2: Resumen general de productos vendidos")

        productos_resumen = [
            (cat, df_res[f"_{cat}_cant"].sum(), df_res[f"_{cat}_m"].sum())
            for cat in CATEGORIAS_CHICAS
        ]

        with st.container(horizontal=True):
            for nombre_p, cant_p, monto_p in productos_resumen:
                st.metric(nombre_p, int(cant_p), f"${monto_p:,.2f}", border=True, delta_color="off")
        st.subheader(f":material/query_stats: Totales de nómina — {nombre_pestana}")

        subtotal = float(df_res['Total a Pagar'].sum())
        total_vales_grupo = float(df_res['Vales'].sum())
        total_transf_grupo = float(df_res['Transferencia'].sum())
        total_descuento_grupo = float(df_res['Descuento'].sum())
        total_cocina_grupo = float(df_res['Cocina'].sum())
        total_sueldos_grupo = float(df_res['Sueldo Base'].sum())
        total_comisiones_grupo = float(df_res['Comisiones'].sum())
        total_multa_grupo = float(df_res['Multa'].sum())
        total_peinado_grupo = float(df_res['Peinado y maquillaje'].sum())
        total_dulceria_grupo = float(df_res['Dulcería'].sum())

        with st.container(horizontal=True):
            st.metric("Subtotal nómina", f"${subtotal:,.2f}", border=True)
            st.metric("Total vales", f"${total_vales_grupo:,.2f}", border=True)
            st.metric("Total transferencias", f"${total_transf_grupo:,.2f}", border=True)
            st.metric("Total descuentos", f"${total_descuento_grupo:,.2f}", border=True)

        with st.container(horizontal=True):
            st.metric("Total sueldos base", f"${total_sueldos_grupo:,.2f}", border=True)
            st.metric("Total comisiones", f"${total_comisiones_grupo:,.2f}", border=True)
            st.metric("Total cocina", f"${total_cocina_grupo:,.2f}", border=True)
            st.metric("Total multas", f"${total_multa_grupo:,.2f}", border=True)

        with st.container(horizontal=True):
            st.metric("Total peinado y maquillaje", f"${total_peinado_grupo:,.2f}", border=True)
            st.metric("Total dulcería", f"${total_dulceria_grupo:,.2f}", border=True)

        st.subheader(":material/print: Imprimir tickets (80mm)")
        vales_dia_df = cargar_vales_df(fecha_activa)
        col_ticket_ind, col_ticket_masivo = st.columns(2)
        with col_ticket_ind:
            nombre_ticket_sel = st.selectbox("Empleado", df_res["Nombre"].tolist(), key=f"sel_ticket_{key_sufijo}")
            fila_ticket = df_res[df_res["Nombre"] == nombre_ticket_sel].iloc[0]
            folios_ticket = _folios_vale_dia(vales_dia_df, int(fila_ticket["ID"]))
            pdf_ticket_individual = generar_pdf_tickets(
                [_flowables_ticket_chica(fila_ticket, fecha_activa, _estilos_ticket(), folios_ticket)], alto_pagina_mm=180
            )
            st.download_button(
                "Descargar ticket individual", data=pdf_ticket_individual,
                file_name=f"Ticket_{nombre_ticket_sel}_{fecha_activa}.pdf", mime="application/pdf",
                icon=":material/receipt_long:", key=f"btn_ticket_ind_{key_sufijo}"
            )
        with col_ticket_masivo:
            st.write("")
            pdf_tickets_masivo = generar_pdf_tickets(
                [_flowables_ticket_chica(fila_r, fecha_activa, _estilos_ticket(), _folios_vale_dia(vales_dia_df, int(fila_r["ID"])))
                 for _, fila_r in df_res.iterrows()],
                alto_pagina_mm=180
            )
            st.download_button(
                f"Descargar todos los tickets ({len(df_res)})", data=pdf_tickets_masivo,
                file_name=f"Tickets_{nombre_pestana}_{fecha_activa}.pdf", mime="application/pdf",
                icon=":material/print:", key=f"btn_ticket_masivo_{key_sufijo}"
            )

        return df_editado, subtotal

    def procesar_grupo_general(df_subgrupo, nombre_pestana, key_sufijo):
        if df_subgrupo.empty:
            st.info(f"No hay registros en {nombre_pestana} para la fecha {fecha_activa}.")
            return 0.0

        chicas_con_descuento_count = 0
        if not empleados_df.empty:
            df_chicas_todas = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)]
            if 'descuento_nomina' in df_chicas_todas.columns:
                chicas_con_descuento_count = len(df_chicas_todas[df_chicas_todas['descuento_nomina'] > 0.0])
            else:
                chicas_con_descuento_count = len(df_chicas_todas)

        res_general = []
        for _, emp in df_subgrupo.iterrows():
            emp_id = emp['id']
            nombre = emp['nombre']
            tipo = emp['tipo']
            puesto_dia_actual = emp.get('puesto_dia', "") or ""
            tipo_efectivo = emp.get('tipo_efectivo', tipo) or tipo
            sueldo_base = float(emp['sueldo_base'])
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            cocina_emp = float(emp.get('consumo_cocina', 0.0))
            retencion_emp = float(emp.get('retencion_nomina', 0.0))
            dulceria_emp = float(emp.get('dulceria', 0.0))

            puesto_upper_check = str(tipo_efectivo).upper()
            comisiones_prod = 0.0
            if any(p in puesto_upper_check for p in ["DJ", "ANIMADOR"]):
                porcentaje_propina = 0.0
                comisiones_prod = calcular_bono_dj_animador(chicas_con_descuento_count)
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
            propina_propia_rol = 0.0
            if not ventas_totales.empty and porcentaje_propina > 0.0:
                if any(p in puesto_upper_check for p in ["AYUDANTE", "BARMAN", "GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                    p_tarj_tot = (ventas_totales['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in ventas_totales.columns else 0.0
                    p_efec_tot = ventas_totales['propina_efectivo'].sum() if 'propina_efectivo' in ventas_totales.columns else 0.0
                    p_vale_tot = ventas_totales['propina_vales'].sum() if 'propina_vales' in ventas_totales.columns else 0.0
                    p_cred_tot = ventas_totales['propinacredito'].sum() if 'propinacredito' in ventas_totales.columns else 0.0
                    total_propinas_restaurante = p_tarj_tot + p_efec_tot + p_vale_tot + p_cred_tot
                    propinas = total_propinas_restaurante * (porcentaje_propina / 100.0)

                    # Gerente/Capitán/Cajero a veces atienden mesas directamente
                    # (aparecen como "idmesero" en el Excel). Se les suma su
                    # propina personal completa para pagarles todo de una vez.
                    if any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                        propina_propia_rol = calcular_propina_ventas_propias(ventas_totales, emp_id)
                        propinas += propina_propia_rol
                else:
                    filas_mesero = ventas_totales[ventas_totales['idmesero'] == emp_id]
                    if not filas_mesero.empty:
                        p_tarj = (filas_mesero['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in filas_mesero.columns else 0.0
                        p_efec = filas_mesero['propina_efectivo'].sum() if 'propina_efectivo' in filas_mesero.columns else 0.0
                        p_vale = filas_mesero['propina_vales'].sum() if 'propina_vales' in filas_mesero.columns else 0.0
                        p_cred = filas_mesero['propinacredito'].sum() if 'propinacredito' in filas_mesero.columns else 0.0
                        total_prop_mesero = p_tarj + p_efec + p_vale + p_cred
                        propinas = total_prop_mesero * (porcentaje_propina / 100.0)

            if any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                if not chicas_totales.empty:
                    for _, f_prod in chicas_totales.iterrows():
                        desc = str(f_prod['descripcion'])
                        cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                        comisiones_prod += cant * calcular_comision_gerencia_caja(desc)

            total_bruto = sueldo_base + propinas + comisiones_prod
            total_pagar = total_bruto - vales_emp - transf_emp - retencion_emp

            if propina_propia_rol > 0:
                etiqueta_propina = f"↑ {porcentaje_propina:.1f}% pool + ${propina_propia_rol:,.2f} propia (${propinas:,.2f})"
            else:
                etiqueta_propina = f"↑ {porcentaje_propina:.1f}% (${propinas:,.2f})"

            res_general.append({
                "ID": emp_id, "Nombre": nombre, "Puesto": tipo,
                "Puesto del día": puesto_dia_actual if puesto_dia_actual else "(mismo puesto)",
                "Total a Pagar": total_pagar, "Sueldo Base": sueldo_base,
                "Vales": vales_emp, "Transferencia": transf_emp, "Cocina": cocina_emp,
                "Retención": retencion_emp, "Dulcería": dulceria_emp,
                "Propina (%)": etiqueta_propina,
                "Comisiones": comisiones_prod, "_propinas_num": propinas
            })

        df_res_general = pd.DataFrame(res_general)
        cols_mostrar_gen = ["ID", "Nombre", "Puesto", "Puesto del día", "Total a Pagar", "Sueldo Base", "Vales", "Transferencia", "Cocina", "Retención", "Dulcería", "Propina (%)", "Comisiones"]
        opciones_puesto_dia = ["(mismo puesto)"] + [p for p in PUESTOS_CATALOGO.keys() if p != "Chicas / Bailarinas (Comisiones)"]
        editor_key_gen_base = f"editor_sueldos_gen_{key_sufijo}"
        version_key_gen = f"{editor_key_gen_base}_version"
        if version_key_gen not in st.session_state:
            st.session_state[version_key_gen] = 0
        editor_key_gen = f"{editor_key_gen_base}_v{st.session_state[version_key_gen]}"

        def resaltar_filas_gen(row):
            return ['background-color: #1A2634; color: #FFFFFF;' if row.name % 2 == 0 else 'background-color: #141D26; color: #FFFFFF;'] * len(row)

        def pintar_negativos_gen(val):
            if isinstance(val, (int, float)) and val < 0:
                return 'color: #FF5252; font-weight: bold;'
            return ''

        df_estilizado_gen = df_res_general[cols_mostrar_gen].style.apply(resaltar_filas_gen, axis=1).map(pintar_negativos_gen, subset=['Total a Pagar'])
        cols_disabled_gen = ["ID", "Nombre", "Puesto", "Propina (%)", "Comisiones", "Total a Pagar"]
        if not puede_modificar:
            cols_disabled_gen = cols_mostrar_gen

        cambios_gen_sin_guardar = st.session_state.get(editor_key_gen, {}).get("edited_rows", {})
        if cambios_gen_sin_guardar:
            st.warning("⚠️ Hay cambios sin guardar en esta tabla. Se pierden si cambias de pestaña sin presionar 'Guardar cambios'; usa 'Descartar cambios' para regresar a los valores guardados.")

        with st.form(f"form_nomina_gen_{key_sufijo}"):
            df_editado_gen = st.data_editor(
                df_estilizado_gen,
                height=min(max(len(df_res_general) * 45 + 40, 150), 900),
                column_config={
                    "ID": st.column_config.NumberColumn("ID", disabled=True),
                    "Total a Pagar": st.column_config.NumberColumn("Total a Pagar ($)", format="$%.2f", disabled=True),
                    "Sueldo Base": st.column_config.NumberColumn("Sueldo Base ($)", format="$%.2f", required=True),
                    "Vales": st.column_config.NumberColumn("Vales ($)", format="$%.2f", required=True),
                    "Transferencia": st.column_config.NumberColumn("Transferencia ($)", format="$%.2f", required=True),
                    "Cocina": st.column_config.NumberColumn("Cocina ($)", format="$%.2f", required=True),
                    "Retención": st.column_config.NumberColumn("Retención ($)", format="$%.2f", required=True),
                    "Dulcería": st.column_config.NumberColumn("Dulcería ($)", format="$%.2f", required=True),
                    "Propina (%)": st.column_config.TextColumn("Propina (%)", disabled=True),
                    "Comisiones": st.column_config.NumberColumn("Comisiones ($)", format="$%.2f", disabled=True),
                    "Puesto del día": st.column_config.SelectboxColumn(
                        "Puesto del día", options=opciones_puesto_dia, required=True,
                        help="Si cubrió otro puesto hoy (ej. Barra), elígelo aquí: su propina/comisión de HOY se calcula con las reglas de ese puesto, sin cambiar su puesto permanente."
                    ),
                },
                disabled=cols_disabled_gen,
                use_container_width=True,
                key=editor_key_gen
            )
            col_guardar_gen, col_descartar_gen = st.columns(2)
            with col_guardar_gen:
                guardar_nomina_gen = st.form_submit_button("💾 Guardar cambios", disabled=not puede_modificar, use_container_width=True)
            with col_descartar_gen:
                descartar_nomina_gen = st.form_submit_button("↩️ Descartar cambios", use_container_width=True)

        actualizado_gen_flag = False
        if guardar_nomina_gen and puede_modificar and (editor_key_gen in st.session_state):
            with st.spinner("Guardando cambios..."):
                cambios_gen = st.session_state[editor_key_gen].get("edited_rows", {})
                for row_idx, edits in cambios_gen.items():
                    fila_mod_gen = df_res_general.iloc[int(row_idx)]
                    e_id = int(fila_mod_gen['ID'])

                    nuevo_sb = float(edits["Sueldo Base"]) if "Sueldo Base" in edits else float(fila_mod_gen['Sueldo Base'])
                    nuevo_vales = float(edits["Vales"]) if "Vales" in edits else float(fila_mod_gen['Vales'])
                    nueva_transf = float(edits["Transferencia"]) if "Transferencia" in edits else float(fila_mod_gen['Transferencia'])
                    nueva_cocina = float(edits["Cocina"]) if "Cocina" in edits else float(fila_mod_gen['Cocina'])
                    nueva_retencion = float(edits["Retención"]) if "Retención" in edits else float(fila_mod_gen['Retención'])
                    nueva_dulceria = float(edits["Dulcería"]) if "Dulcería" in edits else float(fila_mod_gen['Dulcería'])
                    nuevo_puesto_dia_sel = str(edits["Puesto del día"]) if "Puesto del día" in edits else str(fila_mod_gen['Puesto del día'])
                    nuevo_puesto_dia = "" if nuevo_puesto_dia_sel == "(mismo puesto)" else nuevo_puesto_dia_sel
                    puesto_emp = fila_mod_gen['Puesto']
                    penalizada_bd = bool(empleados_df[empleados_df['id'] == e_id]['penalizada'].values[0])
                    descuento_bd = float(empleados_df[empleados_df['id'] == e_id]['descuento_nomina'].values[0]) if 'descuento_nomina' in empleados_df.columns else 100.0

                    actualizar_empleado(
                        e_id, puesto_emp, nuevo_sb, nuevo_vales, penalizada_bd, descuento_bd, nueva_transf, nueva_cocina,
                        fecha_str=fecha_activa, nuevo_puesto_dia=nuevo_puesto_dia, nuevo_retencion=nueva_retencion,
                        nuevo_dulceria=nueva_dulceria
                    )
                    actualizado_gen_flag = True

        if actualizado_gen_flag:
            st.session_state[version_key_gen] += 1
            st.toast("✅ Cambios guardados correctamente.", icon="✅")
            st.rerun()
        elif descartar_nomina_gen:
            st.session_state[version_key_gen] += 1
            st.rerun()

        st.subheader(f":material/query_stats: Totales de nómina — {nombre_pestana}")
        tot_sb = float(df_res_general['Sueldo Base'].sum())
        tot_prop = float(df_res_general['_propinas_num'].sum())
        tot_com = float(df_res_general['Comisiones'].sum())
        sub_g = float(df_res_general['Total a Pagar'].sum())
        total_vales_gen = float(df_res_general['Vales'].sum())
        total_transf_gen = float(df_res_general['Transferencia'].sum())
        total_cocina_gen = float(df_res_general['Cocina'].sum())
        total_retencion_gen = float(df_res_general['Retención'].sum())
        total_dulceria_gen = float(df_res_general['Dulcería'].sum())

        with st.container(horizontal=True):
            st.metric("Total sueldos base", f"${tot_sb:,.2f}", border=True)
            st.metric("Total propinas", f"${tot_prop:,.2f}", border=True)
            st.metric("Total comisiones", f"${tot_com:,.2f}", border=True)
            st.metric("Subtotal", f"${sub_g:,.2f}", border=True)

        with st.container(horizontal=True):
            st.metric("Total vales", f"${total_vales_gen:,.2f}", border=True)
            st.metric("Total transferencias", f"${total_transf_gen:,.2f}", border=True)
            st.metric("Total cocina", f"${total_cocina_gen:,.2f}", border=True)
            st.metric("Total retenciones", f"${total_retencion_gen:,.2f}", border=True)
            st.metric("Total dulcería", f"${total_dulceria_gen:,.2f}", border=True)

        st.subheader(":material/print: Imprimir tickets (80mm)")
        productos_dia_gerencia = _desglose_productos_gerencia(chicas_totales)
        vales_dia_gen_df = cargar_vales_df(fecha_activa)
        col_ticket_ind_gen, col_ticket_masivo_gen = st.columns(2)
        with col_ticket_ind_gen:
            nombre_ticket_gen_sel = st.selectbox("Empleado", df_res_general["Nombre"].tolist(), key=f"sel_ticket_gen_{key_sufijo}")
            fila_ticket_gen = df_res_general[df_res_general["Nombre"] == nombre_ticket_gen_sel].iloc[0]
            folios_ticket_gen = _folios_vale_dia(vales_dia_gen_df, int(fila_ticket_gen["ID"]))
            pdf_ticket_gen_individual = generar_pdf_tickets(
                [_flowables_ticket_general_dispatch(fila_ticket_gen, fecha_activa, _estilos_ticket(), productos_dia_gerencia, folios_ticket_gen)],
                alto_pagina_mm=140
            )
            st.download_button(
                "Descargar ticket individual", data=pdf_ticket_gen_individual,
                file_name=f"Ticket_{nombre_ticket_gen_sel}_{fecha_activa}.pdf", mime="application/pdf",
                icon=":material/receipt_long:", key=f"btn_ticket_ind_gen_{key_sufijo}"
            )
        with col_ticket_masivo_gen:
            st.write("")
            pdf_tickets_gen_masivo = generar_pdf_tickets(
                [_flowables_ticket_general_dispatch(
                    fila_r, fecha_activa, _estilos_ticket(), productos_dia_gerencia,
                    _folios_vale_dia(vales_dia_gen_df, int(fila_r["ID"]))
                 ) for _, fila_r in df_res_general.iterrows()],
                alto_pagina_mm=140
            )
            st.download_button(
                f"Descargar todos los tickets ({len(df_res_general)})", data=pdf_tickets_gen_masivo,
                file_name=f"Tickets_{nombre_pestana}_{fecha_activa}.pdf", mime="application/pdf",
                icon=":material/print:", key=f"btn_ticket_masivo_gen_{key_sufijo}"
            )

        return float(df_res_general['Total a Pagar'].sum())

    with tab_bailarinas:
        st.markdown(f"### Nómina: Bailarinas y Chicas ({fecha_activa})")
        df_chicas_nomina = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)] if not empleados_df.empty else pd.DataFrame()
        procesar_grupo_chicas(df_chicas_nomina, "Bailarinas y Chicas", "bailarinas_chicas")

    with tab_meseros:
        st.markdown(f"### Nómina: Meseros y Ayudantes de Mesero ({fecha_activa})")
        if not empleados_df.empty:
            mask_meseros = (
                empleados_df['tipo'].astype(str).str.upper().str.contains("MESERO") &
                ~empleados_df['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN")
            ) | empleados_df['tipo'].astype(str).str.upper().str.contains("AYUDANTE")
            df_meseros = empleados_df[mask_meseros]
        else:
            df_meseros = pd.DataFrame()
        procesar_grupo_general(df_meseros, "Meseros y Ayudantes", "meseros_ayudantes")

    with tab_seguridad:
        st.markdown(f"### Nómina: Personal de Seguridad ({fecha_activa})")
        df_seguridad = empleados_df[empleados_df['tipo'].astype(str).str.upper().str.contains("SEGURIDAD")] if not empleados_df.empty else pd.DataFrame()
        procesar_grupo_general(df_seguridad, "Seguridad", "seguridad")

    with tab_general:
        st.markdown(f"### Nómina: Personal General, Gerencia y Capitanes ({fecha_activa})")
        if not empleados_df.empty:
            mask_general = (
                ~empleados_df['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina) &
                ~empleados_df['tipo'].astype(str).str.upper().str.contains("SEGURIDAD|AYUDANTE") &
                ~(empleados_df['tipo'].astype(str).str.upper().str.contains("MESERO") & ~empleados_df['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN"))
            )
            df_general_otros = empleados_df[mask_general]
        else:
            df_general_otros = pd.DataFrame()
        procesar_grupo_general(df_general_otros, "Personal General y Fijo", "general_otros")

    if not es_gerente:
        st.subheader(":material/edit: Modificar o eliminar empleado")
        if not empleados_df.empty:
            nombres_emps = empleados_df['nombre'].tolist()
            emp_a_editar = st.selectbox("Selecciona empleado a modificar o eliminar", nombres_emps, key="sel_emp_mod")

            emp_actual = empleados_df[empleados_df['nombre'] == emp_a_editar].iloc[0]
            nuevo_tipo_edit = st.selectbox(
                "Nuevo puesto", list(PUESTOS_CATALOGO.keys()),
                index=list(PUESTOS_CATALOGO.keys()).index(emp_actual['tipo']) if emp_actual['tipo'] in PUESTOS_CATALOGO else 0,
                key="sel_tipo_mod"
            )
            sueldo_sugerido = PUESTOS_CATALOGO.get(nuevo_tipo_edit, float(emp_actual['sueldo_base']))
            nuevo_sueldo_edit = st.number_input("Sueldo base ($)", value=sueldo_sugerido, format="%.2f", key="edit_sueldo_input")

            col_btn_1, col_btn_2 = st.columns(2)
            with col_btn_1:
                if st.button("Actualizar empleado"):
                    actualizar_empleado(int(emp_actual['id']), nuevo_tipo_edit, nuevo_sueldo_edit, fecha_str=fecha_activa)
                    st.success(f"¡Datos de {emp_a_editar} actualizados!")
                    st.rerun()
            with col_btn_2:
                if st.button("Eliminar empleado", icon=":material/delete:", type="secondary"):
                    exito_del, err_msg = eliminar_empleado_por_id(int(emp_actual['id']), fecha_activa)
                    if exito_del:
                        st.success(f"¡Empleado {emp_a_editar} eliminado correctamente!")
                        st.rerun()
                    else:
                        st.error(f"No se pudo eliminar el empleado. Detalle: {err_msg}")
        else:
            st.info("No hay empleados registrados en esta fecha.")

# --- SECCIÓN: VALES DIARIOS ---
elif opcion == "Registro de Vales":
    st.subheader(":material/receipt_long: Registro de vales — todos los cortes")
    st.info("Este historial junta los vales de TODOS los cortes (no solo la fecha activa). Se generan al 'Cerrar Corte Actual' (barra lateral): cada empleado con un monto en la columna 'Vales ($)' de Nómina recibe un folio nuevo aquí.")

    vales_df = cargar_vales_df()
    if vales_df.empty:
        st.info("No hay vales registrados todavía. Se generan al cerrar el corte del día.")
    else:
        catalogo_empleados_df = cargar_catalogo_empleados()
        vales_df = vales_df.merge(
            catalogo_empleados_df[["id", "tipo"]].rename(columns={"id": "empleado_id"}),
            on="empleado_id", how="left"
        )
        vales_df["es_chica"] = vales_df["tipo"].apply(
            lambda t: es_chica_o_bailarina(t) if pd.notna(t) else False
        )

        formas_pago = ["EFECTIVO", "TRANSFERENCIA", "EFECTIVO Y TRANSFERENCIA"]
        estados = ["PENDIENTE", "PAGADO", "YA NO PAGAR"]

        def tabla_vales_editable(df_subset, sufijo_key, texto_boton_guardar="💾 Guardar cambios"):
            vista = df_subset[["id", "folio", "fecha", "empleado_nombre", "importe", "estado", "forma_pago", "fecha_pago"]].copy()
            vista.columns = ["ID", "Folio", "Fecha", "Empleado", "Monto", "Estado", "Forma de pago", "Fecha de pago"]

            version_key = f"editor_vales_{sufijo_key}_version"
            if version_key not in st.session_state:
                st.session_state[version_key] = 0
            editor_key = f"editor_vales_{sufijo_key}_v{st.session_state[version_key]}"

            if st.session_state.get(editor_key, {}).get("edited_rows", {}):
                st.warning("⚠️ Hay cambios sin guardar. Usa 'Descartar cambios' para regresar a los valores guardados.")

            with st.form(f"form_vales_{sufijo_key}"):
                editado = st.data_editor(
                    vista,
                    hide_index=True,
                    use_container_width=True,
                    disabled=["ID", "Folio", "Fecha", "Empleado", "Monto", "Fecha de pago"],
                    column_config={
                        "Monto": st.column_config.NumberColumn("Monto ($)", format="$%.2f"),
                        "Estado": st.column_config.SelectboxColumn("Estado", options=estados, required=True),
                        "Forma de pago": st.column_config.SelectboxColumn("Forma de pago", options=formas_pago),
                    },
                    key=editor_key
                )
                col_g, col_d = st.columns(2)
                with col_g:
                    guardar = st.form_submit_button(texto_boton_guardar, use_container_width=True)
                with col_d:
                    descartar = st.form_submit_button("↩️ Descartar cambios", use_container_width=True)
            if guardar:
                folios_sin_forma_pago = [
                    str(fila["Folio"]) for _, fila in editado.iterrows()
                    if fila["Estado"] == "PAGADO" and (pd.isna(fila["Forma de pago"]) or not str(fila["Forma de pago"]).strip())
                ]
                if folios_sin_forma_pago:
                    st.error(
                        "Estos vales no tienen forma de pago; asígnales una antes de marcarlos como PAGADO: "
                        + ", ".join(folios_sin_forma_pago)
                    )
                else:
                    with st.spinner("Guardando cambios..."):
                        error_guardado = None
                        for _, fila in editado.iterrows():
                            original = vista[vista["ID"] == fila["ID"]].iloc[0]
                            forma_pago_nueva = "" if pd.isna(fila["Forma de pago"]) else str(fila["Forma de pago"])
                            forma_pago_original = "" if pd.isna(original["Forma de pago"]) else str(original["Forma de pago"])
                            if fila["Estado"] != original["Estado"] or forma_pago_nueva != forma_pago_original:
                                try:
                                    actualizar_estado_vale(int(fila["ID"]), str(fila["Estado"]), forma_pago_nueva or None)
                                except ValueError as error:
                                    error_guardado = str(error)
                                    break
                    if error_guardado:
                        st.error(error_guardado)
                    else:
                        st.session_state[version_key] += 1
                        st.success("Cambios guardados.")
                        st.rerun()
            elif descartar:
                st.session_state[version_key] += 1
                st.rerun()

        def tabla_vales_solo_lectura(df_subset):
            vista = df_subset[["folio", "fecha", "empleado_nombre", "importe", "estado", "forma_pago", "fecha_pago"]].copy()
            vista.columns = ["Folio", "Fecha", "Empleado", "Monto", "Estado", "Forma de pago", "Fecha de pago"]
            st.dataframe(vista, hide_index=True, use_container_width=True)

        def renderizar_vales_grupo(df_grupo, sufijo_key):
            pendientes_df = df_grupo[df_grupo["estado"] == "PENDIENTE"]
            pagados_df = df_grupo[df_grupo["estado"] == "PAGADO"]
            ya_no_pagar_df = df_grupo[df_grupo["estado"] == "YA NO PAGAR"]

            tab_pend, tab_pag, tab_np = st.tabs([
                f"🟡 Pendientes ({len(pendientes_df)})",
                f"✅ Pagados ({len(pagados_df)})",
                f"🚫 Ya no pagar ({len(ya_no_pagar_df)})",
            ])
            with tab_pend:
                if pendientes_df.empty:
                    st.info("No hay vales pendientes.")
                elif es_gerente:
                    tabla_vales_solo_lectura(pendientes_df)
                else:
                    tabla_vales_editable(pendientes_df, f"{sufijo_key}_pendientes")
            with tab_pag:
                if pagados_df.empty:
                    st.info("No hay vales pagados.")
                elif rol_actual_lower == "admin":
                    tabla_vales_editable(pagados_df, f"{sufijo_key}_pagados", texto_boton_guardar="💾 Guardar cambios (Pagados)")
                else:
                    tabla_vales_solo_lectura(pagados_df)
            with tab_np:
                if ya_no_pagar_df.empty:
                    st.info("No hay vales en 'Ya no pagar'.")
                elif rol_actual_lower == "admin":
                    tabla_vales_editable(ya_no_pagar_df, f"{sufijo_key}_yanopagar", texto_boton_guardar="💾 Guardar cambios (Ya no pagar)")
                else:
                    tabla_vales_solo_lectura(ya_no_pagar_df)

            st.metric("Total del grupo", f"${float(df_grupo['importe'].sum()):,.2f}")

        tab_bailarinas, tab_trabajadores = st.tabs(["🎀 Bailarinas y Chicas", "👥 Trabajadores"])
        with tab_bailarinas:
            renderizar_vales_grupo(vales_df[vales_df["es_chica"]], "bailarinas")
        with tab_trabajadores:
            renderizar_vales_grupo(vales_df[~vales_df["es_chica"]], "trabajadores")

        st.markdown("---")
        st.metric("Total del historial completo de vales", f"${float(vales_df['importe'].sum()):,.2f}")

# --- SECCIÓN: BOUTIQUE / TIENDA (independiente de nómina) ---
elif opcion == "Boutique / Tienda":
    st.subheader(":material/storefront: Boutique / tienda interna")
    st.caption("Módulo independiente: inventario y ventas al personal. No afecta nómina ni cortes.")

    CATEGORIAS_BOUTIQUE = ["Zapatillas", "Ropa", "Accesorios"]
    METODOS_PAGO_BOUTIQUE = ["Efectivo", "Transferencia"]

    tab_inventario, tab_venta, tab_cobros, tab_peligro_boutique = st.tabs([
        "Inventario de productos", "Registrar venta", "Cuentas por cobrar y pagos",
        "Zona de peligro"
    ])

    with tab_inventario:
        productos_df = cargar_productos_boutique_df()
        if productos_df.empty:
            st.info("No hay productos registrados todavía.")
        else:
            vista_prod = productos_df[["id", "codigo", "nombre", "categoria", "talla", "precio_venta", "stock", "activo"]].copy()
            vista_prod.columns = ["ID", "Código", "Nombre", "Categoría", "Talla", "Precio venta", "Stock", "Activo"]

            if es_gerente:
                st.dataframe(vista_prod.drop(columns=["ID"]), hide_index=True, use_container_width=True)
            else:
                version_key_prod = "editor_boutique_prod_version"
                if version_key_prod not in st.session_state:
                    st.session_state[version_key_prod] = 0
                editor_key_prod = f"editor_boutique_prod_v{st.session_state[version_key_prod]}"

                if st.session_state.get(editor_key_prod, {}).get("edited_rows", {}):
                    st.warning("⚠️ Hay cambios sin guardar. Usa 'Descartar cambios' para regresar a los valores guardados.")

                with st.form("form_boutique_productos"):
                    editado_prod = st.data_editor(
                        vista_prod,
                        hide_index=True,
                        use_container_width=True,
                        disabled=["ID", "Código"],
                        column_config={
                            "Categoría": st.column_config.SelectboxColumn("Categoría", options=CATEGORIAS_BOUTIQUE, required=True),
                            "Precio venta": st.column_config.NumberColumn("Precio venta ($)", format="$%.2f", required=True, min_value=0.0),
                            "Stock": st.column_config.NumberColumn("Stock", required=True, min_value=0, step=1),
                            "Activo": st.column_config.CheckboxColumn("Activo"),
                        },
                        key=editor_key_prod
                    )
                    col_g_prod, col_d_prod = st.columns(2)
                    with col_g_prod:
                        guardar_prod = st.form_submit_button("💾 Guardar cambios", use_container_width=True)
                    with col_d_prod:
                        descartar_prod = st.form_submit_button("↩️ Descartar cambios", use_container_width=True)
                if guardar_prod:
                    with st.spinner("Guardando cambios..."):
                        for _, fila in editado_prod.iterrows():
                            original = vista_prod[vista_prod["ID"] == fila["ID"]].iloc[0]
                            if list(fila) != list(original):
                                actualizar_producto_boutique(
                                    int(fila["ID"]), fila["Nombre"], fila["Categoría"], fila["Talla"],
                                    float(fila["Precio venta"]), int(fila["Stock"]), bool(fila["Activo"])
                                )
                    st.session_state[version_key_prod] += 1
                    st.success("Cambios guardados.")
                    st.rerun()
                elif descartar_prod:
                    st.session_state[version_key_prod] += 1
                    st.rerun()

        st.subheader(":material/add_box: Agregar producto nuevo")
        with st.form("form_boutique_nuevo_producto", clear_on_submit=True):
            nuevo_prod_nombre = st.text_input("Nombre")
            nuevo_prod_categoria = st.selectbox("Categoría", CATEGORIAS_BOUTIQUE, key="boutique_nueva_categoria")
            nuevo_prod_talla = st.text_input("Talla (opcional)")
            nuevo_prod_precio = st.number_input("Precio de venta ($)", min_value=0.0, format="%.2f", key="boutique_nuevo_precio")
            nuevo_prod_stock = st.number_input("Stock inicial", min_value=0, step=1, key="boutique_nuevo_stock")
            if st.form_submit_button("Guardar producto"):
                if nuevo_prod_nombre.strip():
                    codigo_generado = agregar_producto_boutique(
                        nuevo_prod_nombre.strip(), nuevo_prod_categoria, nuevo_prod_talla.strip() or None,
                        nuevo_prod_precio, int(nuevo_prod_stock)
                    )
                    st.success(f"¡Producto '{nuevo_prod_nombre.strip()}' agregado al inventario con código {codigo_generado}!")
                    st.rerun()
                else:
                    st.error("El nombre del producto no puede estar vacío.")

    with tab_venta:
        empleados_boutique_df = cargar_catalogo_empleados()
        if not empleados_boutique_df.empty:
            empleados_boutique_df = empleados_boutique_df[empleados_boutique_df["activo"]]
        productos_disponibles_df = cargar_productos_boutique_df(solo_con_stock=True)

        if empleados_boutique_df.empty:
            st.warning("No hay empleados activos en el catálogo.")
        elif productos_disponibles_df.empty:
            st.warning("No hay productos con stock disponible.")
        else:
            nombres_emp_venta = empleados_boutique_df.sort_values("nombre")["nombre"].tolist()
            emp_venta_sel = st.selectbox("Empleado", nombres_emp_venta, key="boutique_venta_empleado")
            emp_venta_fila = empleados_boutique_df[empleados_boutique_df["nombre"] == emp_venta_sel].iloc[0]

            etiquetas_prod = {
                f"{row['nombre']} (stock: {int(row['stock'])})": row['id']
                for _, row in productos_disponibles_df.iterrows()
            }
            prod_venta_sel_label = st.selectbox("Producto", list(etiquetas_prod.keys()), key="boutique_venta_producto")
            prod_venta_fila = productos_disponibles_df[productos_disponibles_df["id"] == etiquetas_prod[prod_venta_sel_label]].iloc[0]

            cantidad_venta = st.number_input(
                "Cantidad", min_value=1, max_value=int(prod_venta_fila["stock"]), step=1, key="boutique_venta_cantidad"
            )
            total_venta_preview = float(prod_venta_fila["precio_venta"]) * cantidad_venta
            st.metric("Total", f"${total_venta_preview:,.2f}", border=True)

            if st.button("Registrar venta", icon=":material/point_of_sale:", key="btn_boutique_registrar_venta"):
                try:
                    folio_venta = registrar_venta_boutique(int(emp_venta_fila["id"]), int(prod_venta_fila["id"]), int(cantidad_venta))
                    st.success(f"¡Venta registrada con folio {folio_venta}! Pendiente de cobro.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

    with tab_cobros:
        st.caption("Los abonos se aplican al saldo general del empleado (todas sus compras), no a un folio en particular.")
        saldos_boutique_df = cargar_saldos_boutique_df()

        subtab_saldos, subtab_abono, subtab_compras, subtab_abonos = st.tabs([
            "Saldo por empleado", "Registrar abono", "Historial de compras", "Historial de abonos"
        ])

        with subtab_saldos:
            if saldos_boutique_df.empty:
                st.info("No hay compras registradas todavía.")
            else:
                vista_saldos = saldos_boutique_df[["empleado_nombre", "total_comprado", "total_abonado", "saldo_pendiente"]].copy()
                vista_saldos.columns = ["Empleado", "Total comprado", "Total abonado", "Saldo pendiente"]

                def _pintar_saldo(val):
                    return 'color: #00E676; font-weight: bold;' if isinstance(val, (int, float)) and val <= 0 else ''

                st.dataframe(
                    vista_saldos.style.format({
                        "Total comprado": "${:,.2f}", "Total abonado": "${:,.2f}", "Saldo pendiente": "${:,.2f}"
                    }).map(_pintar_saldo, subset=["Saldo pendiente"]),
                    hide_index=True, use_container_width=True
                )

        with subtab_abono:
            if es_gerente:
                st.info("Solo lectura para este rol.")
            elif saldos_boutique_df.empty:
                st.info("No hay compras registradas todavía.")
            else:
                deudores_df = saldos_boutique_df[saldos_boutique_df["saldo_pendiente"] > 0]
                if deudores_df.empty:
                    st.info("Nadie tiene saldo pendiente en este momento.")
                else:
                    emp_abono_sel = st.selectbox(
                        "Empleado", deudores_df["empleado_nombre"].tolist(), key="boutique_abono_empleado"
                    )
                    fila_deudor = deudores_df[deudores_df["empleado_nombre"] == emp_abono_sel].iloc[0]
                    st.caption(f"Saldo pendiente actual: ${fila_deudor['saldo_pendiente']:,.2f}")
                    with st.form("form_boutique_abono"):
                        monto_abono = st.number_input(
                            "Monto del abono ($)", min_value=0.01, max_value=float(fila_deudor["saldo_pendiente"]),
                            format="%.2f", key="boutique_abono_monto"
                        )
                        metodo_abono_sel = st.selectbox("Método de pago", METODOS_PAGO_BOUTIQUE, key="boutique_abono_metodo")
                        if st.form_submit_button("Registrar abono"):
                            try:
                                registrar_abono_boutique(int(fila_deudor["empleado_id"]), monto_abono, metodo_abono_sel)
                                saldo_restante = float(fila_deudor["saldo_pendiente"]) - monto_abono
                                st.success(f"¡Abono registrado para {emp_abono_sel}! Saldo restante: ${saldo_restante:,.2f}")
                                st.rerun()
                            except ValueError as error:
                                st.error(str(error))

        with subtab_compras:
            historial_boutique_df = cargar_ventas_boutique_df()
            if historial_boutique_df.empty:
                st.info("No hay ventas registradas todavía.")
            else:
                vista_historial_boutique = historial_boutique_df[[
                    "folio", "empleado_nombre", "producto_nombre", "cantidad", "total", "fecha_venta"
                ]].copy()
                vista_historial_boutique.columns = ["Folio", "Empleado", "Producto", "Cantidad", "Total", "Fecha de venta"]
                st.dataframe(vista_historial_boutique, hide_index=True, use_container_width=True)

        with subtab_abonos:
            abonos_boutique_df = cargar_abonos_boutique_df()
            if abonos_boutique_df.empty:
                st.info("No hay abonos registrados todavía.")
            else:
                vista_abonos_boutique = abonos_boutique_df[["empleado_nombre", "monto", "metodo_pago", "fecha_pago"]].copy()
                vista_abonos_boutique.columns = ["Empleado", "Monto", "Método de pago", "Fecha de pago"]
                st.dataframe(vista_abonos_boutique, hide_index=True, use_container_width=True)

    with tab_peligro_boutique:
        if es_gerente:
            st.info("Solo lectura para este rol.")
        else:
            st.warning("⚠️ Esto borra TODO el inventario, ventas y abonos de Boutique. NO afecta nómina, empleados ni cortes. No se puede deshacer.")

            if "mostrar_form_reinicio_boutique" not in st.session_state:
                st.session_state["mostrar_form_reinicio_boutique"] = False

            if not st.session_state["mostrar_form_reinicio_boutique"]:
                if st.button("🗑️ Borrar datos de Boutique"):
                    st.session_state["mostrar_form_reinicio_boutique"] = True
                    st.rerun()
            else:
                with st.form("form_confirmar_reinicio_boutique"):
                    pass_admin_boutique = st.text_input("Contraseña de Admin", type="password")
                    texto_confirmacion_boutique = st.text_input('Escribe exactamente "BORRAR BOUTIQUE" para confirmar')
                    confirmar_check_boutique = st.checkbox("Entiendo que esta acción es irreversible")

                    col_fb1, col_fb2 = st.columns(2)
                    btn_ejecutar_boutique = col_fb1.form_submit_button("Sí, Borrar")
                    btn_cancelar_boutique = col_fb2.form_submit_button("Cancelar")

                    if btn_ejecutar_boutique:
                        if confirmar_check_boutique and texto_confirmacion_boutique.strip() == "BORRAR BOUTIQUE":
                            usuario_actual_limpio_bt = st.session_state["usuario_actual"].strip().lower()
                            user_val_bt = validar_login(usuario_actual_limpio_bt, pass_admin_boutique)
                            if not user_val_bt and usuario_actual_limpio_bt == "admin":
                                user_val_bt = validar_login("admin", pass_admin_boutique)

                            if user_val_bt and user_val_bt.get("rol") == "admin":
                                eliminar_datos_boutique()
                                st.session_state["mostrar_form_reinicio_boutique"] = False
                                st.success("¡Datos de Boutique borrados con éxito!")
                                st.rerun()
                            else:
                                st.error("Contraseña incorrecta o el usuario no es admin.")
                        else:
                            st.error('Debes marcar la casilla y escribir exactamente "BORRAR BOUTIQUE".')
                    if btn_cancelar_boutique:
                        st.session_state["mostrar_form_reinicio_boutique"] = False
                        st.rerun()

# --- SECCIÓN 4: CIERRE DE CAJA DIARIO (DASHBOARD) ---
elif opcion == "4. Cierre de Caja (Dashboard)":
    ruta_logo_local = "LogoSinBailarina.png"
    if os.path.exists(ruta_logo_local):
        with open(ruta_logo_local, "rb") as f_img:
            encoded_logo = base64.b64encode(f_img.read()).decode("utf-8")
        logo_dash_html = f'<img src="data:image/png;base64,{encoded_logo}" style="width: 260px; border-radius: 8px; margin-bottom: 10px;">'
    else:
        logo_dash_html = "<b>[ZULLYS]</b>"

    col_logo_dash, col_titulo_dash = st.columns([1.5, 5.5])
    with col_logo_dash:
        st.markdown(logo_dash_html, unsafe_allow_html=True)
    with col_titulo_dash:
        st.subheader(f"📊 Dashboard y Resumen de Cierre - Fecha: {fecha_activa}")
        st.info(f"Este panel consolida la información financiera correspondiente al día {fecha_activa}.")

    ventas_acumuladas = cargar_ventas_df(fecha_activa)
    chicas_acumuladas = cargar_chicas_df(fecha_activa)
    empleados_dashboard_df = cargar_empleados_df(fecha_activa)

    chicas_con_descuento_dash = 0
    if not empleados_dashboard_df.empty:
        df_chicas_dash = empleados_dashboard_df[empleados_dashboard_df['tipo'].apply(es_chica_o_bailarina)]
        chicas_con_descuento_dash = len(df_chicas_dash[df_chicas_dash['descuento_nomina'] > 0.0]) if 'descuento_nomina' in df_chicas_dash.columns else len(df_chicas_dash)

    nomina_personal_p_total = 0.0
    vales_personal_total = 0.0
    transferencia_personal_total = 0.0
    
    if not empleados_dashboard_df.empty:
        df_operativo_dash = empleados_dashboard_df[~empleados_dashboard_df['tipo'].apply(es_chica_o_bailarina)]
        for _, emp in df_operativo_dash.iterrows():
            emp_id = emp['id']
            tipo = emp['tipo']
            sueldo_base = float(emp['sueldo_base'])
            vales_emp = float(emp.get('vales_nomina', 0.0))
            transf_emp = float(emp.get('transferencia_nomina', 0.0)) if 'transferencia_nomina' in emp else 0.0
            vales_personal_total += vales_emp
            transferencia_personal_total += transf_emp
            
            puesto_upper_check = tipo.upper()
            comisiones_prod = 0.0
            if any(p in puesto_upper_check for p in ["DJ", "ANIMADOR"]):
                porcentaje_propina = 0.0
                comisiones_prod = calcular_bono_dj_animador(chicas_con_descuento_dash)
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
            if not ventas_acumuladas.empty and porcentaje_propina > 0.0:
                if any(p in puesto_upper_check for p in ["AYUDANTE", "BARMAN", "GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                    p_tarj_tot = (ventas_acumuladas['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in ventas_acumuladas.columns else 0.0
                    p_efec_tot = ventas_acumuladas['propina_efectivo'].sum() if 'propina_efectivo' in ventas_acumuladas.columns else 0.0
                    p_vale_tot = ventas_acumuladas['propina_vales'].sum() if 'propina_vales' in ventas_acumuladas.columns else 0.0
                    p_cred_tot = ventas_acumuladas['propinacredito'].sum() if 'propinacredito' in ventas_acumuladas.columns else 0.0
                    propinas = (p_tarj_tot + p_efec_tot + p_vale_tot + p_cred_tot) * (porcentaje_propina / 100.0)

                    # Gerente/Capitán/Cajero a veces atienden mesas directamente:
                    # se les suma su propina personal completa (ver comisiones.py).
                    if any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                        propinas += calcular_propina_ventas_propias(ventas_acumuladas, emp_id)
                else:
                    filas_emp = ventas_acumuladas[ventas_acumuladas['idmesero'] == emp_id]
                    if not filas_emp.empty:
                        p_tarj = (filas_emp['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in filas_emp.columns else 0.0
                        p_efec = filas_emp['propina_efectivo'].sum() if 'propina_efectivo' in filas_emp.columns else 0.0
                        p_vale = filas_emp['propina_vales'].sum() if 'propina_vales' in filas_emp.columns else 0.0
                        p_cred = filas_emp['propinacredito'].sum() if 'propinacredito' in filas_emp.columns else 0.0
                        propinas = (p_tarj + p_efec + p_vale + p_cred) * (porcentaje_propina / 100.0)

            if any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                if not chicas_acumuladas.empty:
                    for _, f_prod in chicas_acumuladas.iterrows():
                        desc = str(f_prod['descripcion'])
                        cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                        comisiones_prod += cant * calcular_comision_gerencia_caja(desc)

            nomina_personal_p_total += (sueldo_base + propinas + comisiones_prod)

    nomina_chicas_calc = 0.0
    vales_chicas_total = 0.0
    transferencia_chicas_total = 0.0
    cocina_chicas_total = 0.0
    multa_chicas_total = 0.0
    peinado_chicas_total = 0.0
    dulceria_chicas_total = 0.0
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
            cocina_emp = float(emp.get('consumo_cocina', 0.0))
            multa_emp = float(emp.get('retencion_nomina', 0.0))
            peinado_emp = float(emp.get('peinado_maquillaje', 0.0))
            dulceria_emp = float(emp.get('dulceria', 0.0))
            vales_chicas_total += vales_emp
            transferencia_chicas_total += transf_emp
            cocina_chicas_total += cocina_emp
            multa_chicas_total += multa_emp
            peinado_chicas_total += peinado_emp
            dulceria_chicas_total += dulceria_emp
            
            penalizada_chica = bool(emp.get('penalizada', False))
            if penalizada_chica:
                conteo_penalizadas += 1
            
            sueldo_chica = float(emp['sueldo_base'])
            if sueldo_chica > 0.0:
                conteo_con_sueldo += 1
            else:
                conteo_sin_sueldo += 1
            
            sus_filas = chicas_acumuladas[chicas_acumuladas['empleado_id'] == emp_id] if not chicas_acumuladas.empty else pd.DataFrame()
            comisiones_chica_ind = 0.0
            for _, r in sus_filas.iterrows():
                desc = str(r['descripcion']).upper()
                cant = float(r['cantidad']) if pd.notna(r['cantidad']) else 0.0
                com = 80.0 if 'PRIVADO PROMO' in desc else (300.0 if 'PRIVADO ARTISTA' in desc else (1000.0 if 'BOONS ARTISTA' in desc else (700.0 if 'BOONS' in desc else float(r['comision_unitaria']))))
                comisiones_chica_ind += cant * com
            
            if penalizada_chica:
                comisiones_chica_ind /= 2.0

            nomina_chicas_calc += ((sueldo_chica + comisiones_chica_ind) - descuento_emp)

    st.markdown("### 📥 Registro de Gastos y Datos del Día")
    if not puede_modificar:
        st.warning(f"🔒 Modo de solo lectura: El corte del {fecha_activa} está cerrado.")

    gasto_previo = cargar_gastos_hoy(fecha_activa)
    g_compras_val = float(gasto_previo.gasto_compras) if gasto_previo else 0.0
    g_vales_val = float(gasto_previo.gasto_vales) if gasto_previo else 0.0

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        gasto_cocina = sumar_consumo_cocina_dia(fecha_activa)
        st.metric("Gastos - Cocina ($)", f"${gasto_cocina:,.2f}", help="Se calcula solo, sumando la columna Cocina de todos los empleados en '3. Corte y Nómina Final' para esta fecha.")
    with col_g2:
        gasto_compras = st.number_input("Gastos - Compras ($)", value=g_compras_val, format="%.2f", disabled=not puede_modificar)
    with col_g3:
        gasto_vales = st.number_input("Vales / Otros ($)", value=g_vales_val, format="%.2f", disabled=not puede_modificar)

    if puede_modificar:
        if st.button("Guardar Gastos del Día"):
            guardar_gastos_del_dia(gasto_cocina, gasto_compras, gasto_vales, fecha_corte=fecha_activa, usuario_nombre=st.session_state["usuario_actual"])
            st.success(f"¡Gastos guardados para el día {fecha_activa}!")
            st.rerun()

    st.markdown("---")
    st.markdown("### 📋 Resumen Financiero del Día")

    efectivo_ventas, tarjeta_ventas, transferencia_ventas, ventas_por_cobrar = 0.0, 0.0, 0.0, 0.0
    if not ventas_acumuladas.empty:
        efectivo_ventas = float(((ventas_acumuladas['efectivo'] if 'efectivo' in ventas_acumuladas.columns else 0.0) + (ventas_acumuladas['propina_efectivo'] if 'propina_efectivo' in ventas_acumuladas.columns else 0.0)).sum())
        tarjeta_ventas = float(((ventas_acumuladas['tarjeta'] if 'tarjeta' in ventas_acumuladas.columns else 0.0) + (ventas_acumuladas['propina_tarjeta'] if 'propina_tarjeta' in ventas_acumuladas.columns else 0.0)).sum())
        transferencia_ventas = float(((ventas_acumuladas['vales'] if 'vales' in ventas_acumuladas.columns else 0.0) + (ventas_acumuladas['propina_vales'] if 'propina_vales' in ventas_acumuladas.columns else 0.0)).sum())
        ventas_por_cobrar = float(((ventas_acumuladas['otros'] if 'otros' in ventas_acumuladas.columns else 0.0) + (ventas_acumuladas['propinacredito'] if 'propinacredito' in ventas_acumuladas.columns else 0.0)).sum())

    ventas_totales_con_propinas = efectivo_ventas + tarjeta_ventas + transferencia_ventas + ventas_por_cobrar
    nomina_personal_efectivo = nomina_personal_p_total - vales_personal_total - transferencia_personal_total
    nomina_chicas_efectivo = (
        nomina_chicas_calc - vales_chicas_total - transferencia_chicas_total - multa_chicas_total
    )
    total_gastos_nomina_efectivo = nomina_personal_efectivo + nomina_chicas_efectivo + gasto_cocina + gasto_compras + gasto_vales
    efectivo_entregado = efectivo_ventas - total_gastos_nomina_efectivo
    
    utilidad_monto = ventas_totales_con_propinas - ((nomina_personal_p_total + nomina_chicas_calc) + gasto_cocina)
    utilidad_porcentaje = (utilidad_monto / ventas_totales_con_propinas * 100.0) if ventas_totales_con_propinas > 0 else 0.0

    resumen_meseros = pd.DataFrame()
    if not ventas_acumuladas.empty and not empleados_dashboard_df.empty:
        df_ventas_meseros = pd.merge(ventas_acumuladas, empleados_dashboard_df[['id', 'nombre']], left_on='idmesero', right_on='id', how='left')
        for col in ['efectivo', 'propina_efectivo', 'tarjeta', 'propina_tarjeta', 'vales', 'propina_vales', 'otros', 'propinacredito']:
            if col not in df_ventas_meseros.columns:
                df_ventas_meseros[col] = 0.0
        resumen_meseros = df_ventas_meseros.groupby('nombre').agg({
            'efectivo': 'sum', 'propina_efectivo': 'sum', 'tarjeta': 'sum',
            'propina_tarjeta': 'sum', 'vales': 'sum', 'propina_vales': 'sum',
            'otros': 'sum', 'propinacredito': 'sum'
        }).reset_index()
        resumen_meseros['importe_total'] = (
            resumen_meseros['efectivo'] + resumen_meseros['propina_efectivo'] +
            resumen_meseros['tarjeta'] + resumen_meseros['propina_tarjeta'] +
            resumen_meseros['vales'] + resumen_meseros['propina_vales'] +
            resumen_meseros['otros'] + resumen_meseros['propinacredito']
        )

    pdf_buffer = generar_pdf_corte(
        fecha_activa, ventas_totales_con_propinas, efectivo_ventas, tarjeta_ventas, 
        transferencia_ventas, ventas_por_cobrar, efectivo_entregado, utilidad_monto,
        nomina_personal_p_total, nomina_chicas_calc, gasto_cocina, gasto_compras, gasto_vales, 
        total_gastos_nomina_efectivo, resumen_meseros, empleados_dashboard_df, chicas_acumuladas
    )
    st.download_button(
        label="📥 Descargar Reporte Ejecutivo en PDF (Completo)",
        data=pdf_buffer,
        file_name=f"Reporte_Cierre_Ejecutivo_{fecha_activa}.pdf",
        mime="application/pdf",
        type="primary"
    )
    ventas_cards = [
        ("Ventas totales", ventas_totales_con_propinas),
        ("Ventas efectivo", efectivo_ventas),
        ("Ventas terminales", tarjeta_ventas),
        ("Ventas transferencias", transferencia_ventas),
        ("Ventas por cobrar", ventas_por_cobrar),
    ]
    with st.container(horizontal=True):
        for titulo, valor in ventas_cards:
            st.metric(titulo, f"${valor:,.2f}", border=True)

    with st.container(horizontal=True):
        st.metric("Efectivo entregado", f"${efectivo_entregado:,.2f}", border=True)
        st.metric(f"Utilidad antes de costos ({utilidad_porcentaje:.1f}%)", f"${utilidad_monto:,.2f}", border=True)

    st.subheader(":material/summarize: Resumen detallado de nómina y vales por grupo")
    nomina_cards = [
        ("Nómina - Personal general", nomina_personal_p_total),
        ("Nómina - Bailarinas / chicas", nomina_chicas_calc),
        ("Vales - Personal general", vales_personal_total),
        ("Vales - Bailarinas / chicas", vales_chicas_total),
    ]
    with st.container(horizontal=True):
        for titulo, valor in nomina_cards:
            st.metric(titulo, f"${valor:,.2f}", border=True)

    with st.container(horizontal=True):
        st.metric("Bailarinas penalizadas (multas)", f"{conteo_penalizadas}", border=True)
        st.metric("Bailarinas con sueldo base", f"{conteo_con_sueldo}", border=True)
        st.metric("Bailarinas sin sueldo ($0.00)", f"{conteo_sin_sueldo}", border=True)

    st.subheader(":material/receipt_long: Desglose de gastos y nómina en efectivo")
    tabla_gastos = pd.DataFrame([
        {"Concepto": "Nómina - Personal (P)", "Monto": nomina_personal_efectivo},
        {"Concepto": "Nómina - Comisiones Chicas (CH)", "Monto": nomina_chicas_efectivo},
        {"Concepto": "Cocina", "Monto": gasto_cocina},
        {"Concepto": "Compras", "Monto": gasto_compras},
        {"Concepto": "Vales (Gastos / Otros)", "Monto": gasto_vales},
        {"Concepto": "TOTAL GASTOS / NÓMINA", "Monto": total_gastos_nomina_efectivo}
    ])
    st.dataframe(tabla_gastos, use_container_width=True)

    st.subheader(f":material/groups: Resumen de ventas por mesero — {fecha_activa}")
    if not resumen_meseros.empty:
        for i in range(0, len(resumen_meseros), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(resumen_meseros):
                    row = resumen_meseros.iloc[i + j]
                    importe_total = row['importe_total']
                    efectivo_m = row['efectivo'] + row['propina_efectivo']
                    tarjeta_m = row['tarjeta'] + row['propina_tarjeta']
                    transferencia_m = row['vales'] + row['propina_vales']
                    cobrar_m = row['otros'] + row['propinacredito']

                    with cols[j]:
                        with st.container(border=True):
                            st.metric(f"Mesero: {row['nombre']}", f"${importe_total:,.2f}")
                            col_meta1, col_meta2 = st.columns(2)
                            with col_meta1:
                                st.caption(f"Efectivo: ${efectivo_m:,.2f}")
                                st.caption(f"Transferencia: ${transferencia_m:,.2f}")
                            with col_meta2:
                                st.caption(f"Tarjeta: ${tarjeta_m:,.2f}")
                                st.caption(f"Por cobrar: ${cobrar_m:,.2f}")
    else:
        st.info(f"No hay registros de ventas de meseros para la fecha {fecha_activa}.")

# --- SECCIÓN 5: REPORTES ---
elif opcion == "5. Reportes":
    st.subheader("📊 Módulo de Reportes")
    tipo_reporte = st.selectbox("Selecciona el tipo de reporte:", ["Reporte de Nómina por Periodo"])
    st.markdown("---")

    if tipo_reporte == "Reporte de Nómina por Periodo":
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            fecha_inicio_per = st.date_input("Fecha de Inicio", datetime.now(ZoneInfo("America/Mazatlan")), key="rango_ini_per")
        with col_p2:
            fecha_fin_per = st.date_input("Fecha de Fin", datetime.now(ZoneInfo("America/Mazatlan")), key="rango_fin_per")

        f_ini_str = fecha_inicio_per.strftime('%Y-%m-%d')
        f_fin_str = fecha_fin_per.strftime('%Y-%m-%d')

        if st.button("🔍 Consultar Periodo"):
            empleados_rango = cargar_empleados_rango_df(f_ini_str, f_fin_str)
            chicas_rango = cargar_chicas_rango_df(f_ini_str, f_fin_str)
            ventas_rango = cargar_ventas_rango_df(f_ini_str, f_fin_str)
            mapa_asistencias = obtener_mapa_asistencias(f_ini_str, f_fin_str)

            df_diagnostico = diagnosticar_dias_rango(f_ini_str, f_fin_str)
            if not df_diagnostico.empty:
                st.warning(
                    f"⚠️ Se detectaron {len(df_diagnostico)} empleado(s) con días de asistencia "
                    f"que NO tienen su registro de sueldo del día (por eso el 'Sueldo Base Acumulado' "
                    f"sale más bajo de lo esperado)."
                )
                with st.expander("🔍 Ver detalle de días afectados por empleado"):
                    st.dataframe(df_diagnostico, use_container_width=True)
                if st.button("🛠️ Reparar nómina faltante de este periodo", key="btn_reparar_nomina_periodo"):
                    creadas = reparar_nomina_faltante_rango(f_ini_str, f_fin_str)
                    st.success(
                        f"¡Reparado! Se crearon {creadas} registro(s) de nómina diaria faltantes. "
                        f"Vuelve a darle clic a 'Consultar Periodo' para ver el reporte actualizado."
                    )
                st.markdown("---")

            if empleados_rango.empty:
                st.warning(f"No se encontraron registros de nómina entre {f_ini_str} y {f_fin_str}.")
            else:
                tab_rep_bailarinas, tab_rep_meseros, tab_rep_seguridad, tab_rep_general = st.tabs([
                    "💃 Bailarinas y Chicas", "👥 Meseros y Ayudantes", "🛡️ Seguridad", "📋 Personal General y Fijo"
                ])

                with tab_rep_bailarinas:
                    mapa_penalizaciones = obtener_penalizaciones_rango(f_ini_str, f_fin_str)
                    df_bailarinas_rango = empleados_rango[empleados_rango['tipo'].apply(es_chica_o_bailarina)]
                    resumen_bailarinas = []
                    for _, emp in df_bailarinas_rango.iterrows():
                        emp_id = emp['id']
                        sueldo_base_acumulado = float(emp['sueldo_base'])
                        descuento = float(emp['descuento_nomina'])
                        dias_asistencia = mapa_asistencias.get(emp_id, 0)
                        sus_prods = chicas_rango[chicas_rango['empleado_id'] == emp_id] if not chicas_rango.empty else pd.DataFrame()

                        fechas_penalizadas_emp = mapa_penalizaciones.get(emp_id, set())
                        detalle = calcular_comisiones_detalle(sus_prods, fechas_penalizadas=fechas_penalizadas_emp)
                        total_comisiones = detalle["total"]

                        total_pagar = (sueldo_base_acumulado + total_comisiones) - descuento
                        resumen_bailarinas.append({
                            "ID": emp_id, "Nombre": emp['nombre'], "Asistencias (Días)": dias_asistencia,
                            "Días Penalizados": len(fechas_penalizadas_emp),
                            "Sueldo Base Acumulado": sueldo_base_acumulado, "Comisiones Acumuladas": total_comisiones,
                            "Descuentos Acumulados": descuento, "Total a Pagar": total_pagar
                        })
                    df_rep_b = pd.DataFrame(resumen_bailarinas)
                    st.dataframe(df_rep_b, use_container_width=True)

                with tab_rep_meseros:
                    mask_meseros_rango = (
                        empleados_rango['tipo'].astype(str).str.upper().str.contains("MESERO") &
                        ~empleados_rango['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN")
                    ) | empleados_rango['tipo'].astype(str).str.upper().str.contains("AYUDANTE")
                    df_meseros_rango = empleados_rango[mask_meseros_rango]
                    resumen_mes = []
                    for _, emp in df_meseros_rango.iterrows():
                        emp_id = emp['id']
                        tipo = emp['tipo'].upper()
                        sueldo_base_acumulado = float(emp['sueldo_base'])
                        dias_asistencia_m = mapa_asistencias.get(emp_id, 0)
                        porcentaje_propina = 5.0 if "AYUDANTE" in tipo else 50.0
                        propinas_acum = 0.0
                        if not ventas_rango.empty:
                            filas_m = ventas_rango[ventas_rango['idmesero'] == emp_id]
                            if not filas_m.empty:
                                p_tarj = (filas_m['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in filas_m.columns else 0.0
                                p_efec = filas_m['propina_efectivo'].sum() if 'propina_efectivo' in filas_m.columns else 0.0
                                propinas_acum = (p_tarj + p_efec) * (porcentaje_propina / 100.0)
                        resumen_mes.append({
                            "ID": emp_id, "Nombre": emp['nombre'], "Puesto": emp['tipo'],
                            "Asistencias (Días)": dias_asistencia_m, "Sueldo Base Acumulado": sueldo_base_acumulado,
                            "Propinas Acumuladas": propinas_acum, "Total a Pagar": sueldo_base_acumulado + propinas_acum
                        })
                    df_rep_m = pd.DataFrame(resumen_mes)
                    st.dataframe(df_rep_m, use_container_width=True)

                with tab_rep_seguridad:
                    df_seg_rango = empleados_rango[empleados_rango['tipo'].astype(str).str.upper().str.contains("SEGURIDAD")]
                    resumen_seg = []
                    for _, emp in df_seg_rango.iterrows():
                        resumen_seg.append({
                            "ID": emp['id'], "Nombre": emp['nombre'], "Puesto": emp['tipo'],
                            "Asistencias (Días)": mapa_asistencias.get(emp['id'], 0), "Sueldo Base Acumulado": float(emp['sueldo_base']),
                            "Total a Pagar": float(emp['sueldo_base'])
                        })
                    df_rep_s = pd.DataFrame(resumen_seg)
                    st.dataframe(df_rep_s, use_container_width=True)

                with tab_rep_general:
                    mask_gen_rango = (
                        ~empleados_rango['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina) &
                        ~empleados_rango['tipo'].astype(str).str.upper().str.contains("SEGURIDAD|AYUDANTE") &
                        ~(empleados_rango['tipo'].astype(str).str.upper().str.contains("MESERO") & ~empleados_rango['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN"))
                    )
                    df_gen_rango = empleados_rango[mask_gen_rango]
                    resumen_gen = []
                    # Mismo criterio que el corte diario: solo cuentan las chicas
                    # que tuvieron descuento_nomina acumulado > 0 en el periodo.
                    chicas_con_desc_count = len(df_bailarinas_rango[df_bailarinas_rango['descuento_nomina'] > 0.0]) if not df_bailarinas_rango.empty else 0

                    # Total de propinas del restaurante en TODO el periodo (para el
                    # 8% de rol de Gerente/Capitán/Cajero) — se calcula una sola vez.
                    total_propinas_pool_rango = 0.0
                    if not ventas_rango.empty:
                        p_tarj_pool = (ventas_rango['propina_tarjeta'].sum() * 0.84) if 'propina_tarjeta' in ventas_rango.columns else 0.0
                        p_efec_pool = ventas_rango['propina_efectivo'].sum() if 'propina_efectivo' in ventas_rango.columns else 0.0
                        p_vale_pool = ventas_rango['propina_vales'].sum() if 'propina_vales' in ventas_rango.columns else 0.0
                        p_cred_pool = ventas_rango['propinacredito'].sum() if 'propinacredito' in ventas_rango.columns else 0.0
                        total_propinas_pool_rango = p_tarj_pool + p_efec_pool + p_vale_pool + p_cred_pool

                    for _, emp in df_gen_rango.iterrows():
                        emp_id = emp['id']
                        tipo = emp['tipo'].upper()
                        sueldo_base_acumulado = float(emp['sueldo_base'])
                        propina_pool_rol = 0.0
                        propina_propia = 0.0
                        comision_producto = 0.0

                        if any(p in tipo for p in ["DJ", "ANIMADOR"]):
                            comision_producto = calcular_bono_dj_animador(chicas_con_desc_count)
                        elif any(p in tipo for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                            # 8% de rol sobre el total de propinas del periodo
                            propina_pool_rol = total_propinas_pool_rango * 0.08
                            # + 50% de sus propias propinas, si atendió mesas
                            # directamente (mismo % que un mesero normal)
                            propina_propia = calcular_propina_ventas_propias(ventas_rango, emp_id)
                            # + comisión por productos de gerencia/caja (Moët, etc.)
                            if not chicas_rango.empty:
                                for _, f_prod in chicas_rango.iterrows():
                                    cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                                    comision_producto += cant * calcular_comision_gerencia_caja(str(f_prod['descripcion']))

                        propinas_o_comis = propina_pool_rol + propina_propia + comision_producto
                        resumen_gen.append({
                            "ID": emp_id, "Nombre": emp['nombre'], "Puesto": emp['tipo'],
                            "Asistencias (Días)": mapa_asistencias.get(emp_id, 0),
                            "Sueldo Base Acumulado": sueldo_base_acumulado,
                            "Propina Pool (8%)": propina_pool_rol,
                            "Propina Propia (50%)": propina_propia,
                            "Comisión Productos": comision_producto,
                            "Comisiones Acumuladas": propinas_o_comis,
                            "Total a Pagar": sueldo_base_acumulado + propinas_o_comis
                        })
                    df_rep_g = pd.DataFrame(resumen_gen)
                    st.dataframe(df_rep_g, use_container_width=True)

                st.markdown("---")
                buffer_reporte_periodo = io.BytesIO()
                with pd.ExcelWriter(buffer_reporte_periodo, engine='openpyxl') as writer:
                    (df_rep_b if not df_rep_b.empty else pd.DataFrame([{"Info": "Sin registros"}])).to_excel(writer, index=False, sheet_name='Bailarinas y Chicas')
                    (df_rep_m if not df_rep_m.empty else pd.DataFrame([{"Info": "Sin registros"}])).to_excel(writer, index=False, sheet_name='Meseros y Ayudantes')
                    (df_rep_s if not df_rep_s.empty else pd.DataFrame([{"Info": "Sin registros"}])).to_excel(writer, index=False, sheet_name='Seguridad')
                    (df_rep_g if not df_rep_g.empty else pd.DataFrame([{"Info": "Sin registros"}])).to_excel(writer, index=False, sheet_name='General y Fijo')
                buffer_reporte_periodo.seek(0)

                st.download_button(
                    label="📥 Descargar Reporte del Periodo en Excel (todas las pestañas)",
                    data=buffer_reporte_periodo,
                    file_name=f"Reporte_Nomina_{f_ini_str}_a_{f_fin_str}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# --- SECCIÓN: REGISTRO DE ASISTENCIA ---
elif opcion == "Registro de Asistencia":
    st.subheader(f":material/edit_note: Módulo de autoregistro con código PIN — fecha activa: {fecha_activa}")
    empleados_activos_df = cargar_empleados_df(fecha_activa)

    if empleados_activos_df.empty:
        st.warning("No hay empleados registrados en el sistema para esta fecha.")
    else:
        with st.form("form_auto_asistencia"):
            lista_nombres_emp = sorted(empleados_activos_df['nombre'].dropna().unique().tolist())
            emp_seleccionado = st.selectbox("Selecciona tu Nombre", lista_nombres_emp)
            pin_ingresado = st.text_input("Ingresa tu Código PIN de Asistencia", type="password", max_chars=6)
            btn_registrar_asistencia = st.form_submit_button("✅ Registrar mi Asistencia Ahora", type="primary")

            if btn_registrar_asistencia:
                fila_emp = empleados_activos_df[empleados_activos_df['nombre'] == emp_seleccionado].iloc[0]
                if verificar_pin_empleado(int(fila_emp['id']), pin_ingresado):
                    hora_actual_sistema = datetime.now(ZoneInfo("America/Mazatlan")).time()
                    exito, estado_asignado, hora_str, error_sql = registrar_asistencia_individual(
                        empleado_id=int(fila_emp['id']), nombre_emp=emp_seleccionado,
                        tipo_puesto=str(fila_emp['tipo']), fecha_str=fecha_activa,
                        hora_actual_obj=hora_actual_sistema
                    )
                    if exito:
                        st.markdown(f"### 🎉 ¡Asistencia registrada con éxito! ({estado_asignado} a las {hora_str})")
                    else:
                        st.error(f"❌ Error al guardar: {error_sql}")
                else:
                    st.error("❌ Código PIN incorrecto o el empleado aún no tiene un PIN configurado.")

# --- SECCIÓN 6: GESTIÓN DE USUARIOS Y ACCESOS ---
elif opcion == "6. Usuarios y Accesos":
    st.subheader("🔐 Gestión de Usuarios y Accesos del Sistema")
    tab_ver_usuarios, tab_nuevo_usuario, tab_editar_usuario, tab_cambiar_fecha = st.tabs([
        "📋 Usuarios Registrados", "➕ Registrar Nuevo Usuario", "✏️ Modificar Credenciales", "📅 Reasignar Fecha de Corte"
    ])

    with tab_ver_usuarios:
        st.dataframe(cargar_usuarios_df(), use_container_width=True)

    with tab_nuevo_usuario:
        with st.form("form_nuevo_usuario"):
            nuevo_user = st.text_input("Nombre de Usuario")
            nuevo_pass = st.text_input("Contraseña", type="password")
            nuevo_rol = st.selectbox("Rol del Usuario", ["admin", "cajero", "gerente"])
            if st.form_submit_button("Crear Usuario"):
                if nuevo_user.strip() and nuevo_pass.strip():
                    crear_usuario(nuevo_user.strip(), nuevo_pass.strip(), nuevo_rol)
                    st.success("¡Usuario creado!")
                    st.rerun()

    with tab_editar_usuario:
        df_usuarios = cargar_usuarios_df()
        if not df_usuarios.empty:
            usuario_seleccionado = st.selectbox("Selecciona usuario", df_usuarios['username'].tolist())
            emp_info = df_usuarios[df_usuarios['username'] == usuario_seleccionado].iloc[0]
            with st.form("form_editar_usuario"):
                edit_user = st.text_input("Nuevo Nombre", value=emp_info['username'])
                edit_pass = st.text_input("Nueva Contraseña (en blanco para mantener)", type="password")
                edit_rol = st.selectbox("Rol", ["admin", "cajero", "gerente"])
                if st.form_submit_button("Guardar Cambios"):
                    actualizar_credenciales(int(emp_info['id']), edit_user.strip(), edit_pass.strip(), edit_rol)
                    st.success("¡Actualizado!")
                    st.rerun()

    with tab_cambiar_fecha:
        fechas_existentes = obtener_fechas_disponibles()
        if fechas_existentes:
            with st.form("form_cambiar_fecha"):
                fecha_origen = st.selectbox("Fecha Origen", fechas_existentes)
                fecha_destino_input = st.date_input("Fecha Nueva (Destino)")
                if st.form_submit_button("Actualizar Fecha del Corte"):
                    cambiar_fecha_corte(fecha_origen, fecha_destino_input.strftime('%Y-%m-%d'))
                    st.success("¡Reasignado con éxito!")
                    st.rerun()