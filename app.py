import streamlit as st
import pandas as pd
from datetime import datetime
import io
import base64
import os

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from models import (
    cargar_empleados_df, agregar_empleado, actualizar_empleado,
    guardar_corte_ventas, guardar_corte_chicas,
    cargar_ventas_df, cargar_chicas_df,
    guardar_gastos_del_dia, cargar_gastos_hoy,
    reiniciar_base_de_datos, obtener_fechas_disponibles,
    validar_login, cargar_usuarios_df, crear_usuario, actualizar_credenciales,
    cambiar_fecha_corte, verificar_corte_bloqueado, bloquear_corte_fecha, desbloquear_corte_fecha,
    get_session, CorteVenta, ProductoChica, NominaDiaria,
    cargar_empleados_rango_df, cargar_chicas_rango_df, cargar_ventas_rango_df
)

st.set_page_config(layout="wide")

# --- CONTROL DE SESIÓN Y LOGIN ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "usuario_actual" not in st.session_state:
    st.session_state["usuario_actual"] = ""
if "rol_actual" not in st.session_state:
    st.session_state["rol_actual"] = ""

if not st.session_state["autenticado"]:
    st.sidebar.title("Control de Acceso")
    st.sidebar.subheader("Iniciar Sesión")
    
    with st.sidebar.form("form_login"):
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

st.sidebar.markdown(f"Sesión activa: **{st.session_state['usuario_actual']} ({st.session_state['rol_actual'].upper()})**")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state["autenticado"] = False
    st.session_state["usuario_actual"] = ""
    st.session_state["rol_actual"] = ""
    st.rerun()

st.title("Sistema Integral: Nómina, Ventas y Cierre de Caja - Restaurante")

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
    if 'PRIVADO PROMO' in p:
        return 80.0
    elif 'PRIVADO ARTISTA' in p:
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

def limpiar_cortes_dia(fecha_str):
    session = get_session()
    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        session.query(CorteVenta).filter(CorteVenta.fecha == f_date).delete()
        session.query(ProductoChica).filter(ProductoChica.fecha == f_date).delete()
        session.query(NominaDiaria).filter(NominaDiaria.fecha == f_date).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def obtener_logo_flowable(fallback_style):
    ruta_logo = "LogoSinBailarina.png"
    if os.path.exists(ruta_logo):
        try:
            return Image(ruta_logo, width=110)
        except Exception:
            return Paragraph("<b>[ZULLYS]</b>", fallback_style)
    return Paragraph("<b>[ZULLYS]</b>", fallback_style)

def generar_pdf_corte(fecha_str, ventas_t, efectivo_v, tarjeta_v, transferencia_v, cobrar_v, efectivo_entregado, utilidad_m, nomina_p, nomina_ch, g_cocina, g_compras, g_vales, total_gastos, df_ventas_meseros, df_empleados_pdf, df_chicas_pdf):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    story = []
    
    PRIMARY_COLOR = colors.HexColor("#111827")
    ALT_BG = colors.HexColor("#F9FAFB")
    BORDER_COLOR = colors.HexColor("#E5E7EB")
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=PRIMARY_COLOR, fontName='Helvetica-Bold', spaceAfter=2)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Heading2'], fontSize=9, textColor=colors.HexColor("#6B7280"), fontName='Helvetica')
    section_heading = ParagraphStyle('SectionHeading', parent=styles['Heading3'], fontSize=11, textColor=PRIMARY_COLOR, fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=6)
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor("#374151"))
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=PRIMARY_COLOR)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=colors.whitesmoke)

    logo_flowable = obtener_logo_flowable(cell_style)

    texto_cabecera = [
        Paragraph("ZULLYS MENS CLUB", title_style),
        Paragraph(f"REPORTE GENERAL DE CIERRE DE CAJA — FECHA: {fecha_str}", subtitle_style)
    ]

    tabla_header = Table([[logo_flowable, texto_cabecera]], colWidths=[120, 410])
    tabla_header.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0)]))

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
    t_fin.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]), ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR)]))
    t_gas = Table(data_gastos_pdf, colWidths=[160, 95])
    t_gas.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]), ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR)]))

    story.append(Table([[t_fin, t_gas]], colWidths=[265, 265]))
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
        t_mes.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]), ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR)]))
        story.append(t_mes)
    
    story.append(Spacer(1, 10))
    doc.build(story)
    buffer.seek(0)
    return buffer

def generar_pdf_periodo(titulo_reporte, rango_str, df_resultados, total_general):
    buffer = io.BytesIO()
    # Cambiamos a formato horizontal (landscape) para evitar errores de diseño con múltiples columnas
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    PRIMARY_COLOR = colors.HexColor("#111827")
    ALT_BG = colors.HexColor("#F9FAFB")
    BORDER_COLOR = colors.HexColor("#E5E7EB")
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=PRIMARY_COLOR, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor("#6B7280"), fontName='Helvetica')
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#374151"))
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=PRIMARY_COLOR)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=colors.whitesmoke)

    logo_flowable = obtener_logo_flowable(cell_style)

    tabla_header = Table([[logo_flowable, [Paragraph("ZULLYS MENS CLUB", title_style), Paragraph(f"{titulo_reporte} — Periodo: {rango_str}", subtitle_style)]]], colWidths=[130, 600])
    tabla_header.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    
    story.append(tabla_header)
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceBefore=8, spaceAfter=12))

    if not df_resultados.empty:
        headers = [Paragraph(f"<b>{c}</b>", cell_header) for c in df_resultados.columns]
        rows = [headers]
        for _, row in df_resultados.iterrows():
            row_cells = []
            for val in row:
                val_txt = f"${val:,.2f}" if isinstance(val, (int, float)) else str(val)
                row_cells.append(Paragraph(val_txt, cell_style))
            rows.append(row_cells)
        
        # Ancho total disponible en horizontal (792 - 60 márgenes = 732 pts)
        num_cols = len(df_resultados.columns)
        col_width = 732 / num_cols
        
        t_rep = Table(rows, colWidths=[col_width] * num_cols)
        t_rep.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, ALT_BG]),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t_rep)
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>Total General a Pagar: ${total_general:,.2f}</b>", cell_bold))

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- MENÚ LATERAL: CONTROL DE FECHA ---
st.sidebar.header("Menú de Control")

fechas_disponibles = obtener_fechas_disponibles()
rol_actual_lower = st.session_state["rol_actual"].lower()
hoy_str = datetime.now().strftime('%Y-%m-%d')

if rol_actual_lower in ["admin", "cajero"]:
    modo_fecha = st.sidebar.radio("Modo de Operación", ["📅 Día Actual / Nuevo Corte", "🔍 Buscar Corte Histórico"])
    fecha_activa_obj = None
    if modo_fecha == "🔍 Buscar Corte Histórico":
        if fechas_disponibles:
            fecha_activa_obj = st.sidebar.selectbox("Selecciona la fecha del reporte", fechas_disponibles)
            st.sidebar.warning(f"⚠️ Visualizando histórico: {fecha_activa_obj}")
        else:
            st.sidebar.info("No hay cortes históricos registrados aún.")
            fecha_activa_obj = datetime.now().strftime('%Y-%m-%d')
    else:
        fecha_activa_obj = st.sidebar.date_input("Fecha para el Corte Actual", datetime.now())
else:
    fecha_activa_obj = datetime.now().date()
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
        st.sidebar.info("Corte cerrado (Solo lectura). Contacte al administrador para modificarlo.")
else:
    st.sidebar.success(f"El corte del {fecha_activa} está **ABIERTO**.")
    if rol_actual_lower in ["admin", "cajero"]:
        if st.sidebar.button("🔒 Cerrar Corte Actual", key="btn_cerrar_corte"):
            bloquear_corte_fecha(fecha_activa, st.session_state["usuario_actual"])
            st.sidebar.warning(f"¡Corte del {fecha_activa} cerrado y bloqueado!")
            st.rerun()

if rol_actual_lower == "admin":
    puede_modificar = not corte_esta_bloqueado
else:
    puede_modificar = es_dia_actual and (not corte_esta_bloqueado)

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
        st.warning("⚠️ Esta acción borrará TODO. Confirma tu identidad.")
        pass_admin = st.text_input("Contraseña de Admin", type="password")
        confirmar_check = st.checkbox("Estoy seguro de borrar la base de datos")
        
        col_f1, col_f2 = st.columns(2)
        btn_ejecutar = col_f1.form_submit_button("Sí, Borrar")
        btn_cancelar = col_f2.form_submit_button("Cancelar")
        
        if btn_ejecutar:
            if confirmar_check:
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
            else:
                st.error("Debes marcar la casilla de confirmación.")
        
        if btn_cancelar:
            st.session_state["mostrar_form_reinicio"] = False
            st.rerun()

# --- BARRA DE HERRAMIENTAS SUPERIOR ---
if "seccion_activa" not in st.session_state:
    st.session_state["seccion_activa"] = "1. Subir Cortes Diarios (Excel)"

nombres_secciones = [
    "1. Subir Cortes Diarios (Excel)",
    "2. Gestión de Empleados",
    "3. Corte y Nómina Final",
    "4. Cierre de Caja (Dashboard)",
    "5. Reporte de Nómina por Periodos"
]
if rol_actual_lower == "admin":
    nombres_secciones.append("6. Usuarios y Accesos")

cols_toolbar = st.columns(len(nombres_secciones))
for idx, sec in enumerate(nombres_secciones):
    with cols_toolbar[idx]:
        activo = (st.session_state["seccion_activa"] == sec)
        label_btn = f"📌 {sec}" if activo else sec
        if st.button(label_btn, use_container_width=True, key=f"toolbar_btn_{idx}"):
            st.session_state["seccion_activa"] = sec
            st.rerun()

opcion = st.session_state["seccion_activa"]
st.markdown("---")

# --- SECCIÓN 1: SUBIR ARCHIVOS DIARIOS ---
if opcion == "1. Subir Cortes Diarios (Excel)":
    st.subheader(f"Carga de Archivos Diarios para la fecha: {fecha_activa}")
    if not puede_modificar:
        st.warning("🔒 Modo de solo lectura: El corte está cerrado o es histórico. Ábralo previamente para subir archivos.")
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
                st.warning(f"⚠️ ¿Estás seguro de eliminar todas las ventas, productos de chicas y registros de nómina para el día **{fecha_activa}**?")
                conf_borrar = st.checkbox("Sí, deseo borrar toda la información de este día")
                
                col_b1, col_b2 = st.columns(2)
                btn_ejec_borrar = col_b1.form_submit_button("Confirmar Borrado")
                btn_canc_borrar = col_b2.form_submit_button("Cancelar")
                
                if btn_ejec_borrar:
                    if conf_borrar:
                        limpiar_cortes_dia(fecha_activa)
                        st.session_state["mostrar_form_borrar_dia"] = False
                        st.success(f"¡Se han eliminado todos los registros del día {fecha_activa} exitosamente!")
                        st.rerun()
                    else:
                        st.error("Debes marcar la casilla de confirmación.")
                
                if btn_canc_borrar:
                    st.session_state["mostrar_form_borrar_dia"] = False
                    st.rerun()

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
                guardar_corte_ventas(df_v, df_p, archivo_origen=up_ventas.name, fecha_corte=fecha_activa, usuario_nombre=st.session_state["usuario_actual"])
                st.success(f"¡Corte de meseros y propinas guardado correctamente para el día {fecha_activa}!")
                st.rerun()

        if up_chicas is not None:
            df_c = pd.read_excel(up_chicas, skiprows=4)
            st.success("¡Archivo de productos cargado!")

            if st.button("Procesar y Guardar Comisiones del Día", key="btn_guardar_chicas"):
                if len(df_c.columns) >= 5:
                    df_c.columns = ['CLAVE', 'DESCRIPCION', 'GRUPO', 'PRECIO', 'CANTIDAD'] + list(df_c.columns[5:])
                    filas_chicas = df_c[df_c['DESCRIPCION'].astype(str).str.contains('>')].copy()

                    nuevas_detectadas = guardar_corte_chicas(
                        filas_chicas, calcular_comision_chica, archivo_origen=up_chicas.name, fecha_corte=fecha_activa, usuario_nombre=st.session_state["usuario_actual"]
                    )
                    st.success(f"¡Corte procesado y guardado para el día {fecha_activa}! Se registraron {len(nuevas_detectadas)} personas nuevas automáticamente.")
                    st.rerun()
                else:
                    st.error("El archivo no tiene el formato esperado.")

# --- SECCIÓN 2: GESTIÓN Y EDICIÓN DE EMPLEADOS ---
elif opcion == "2. Gestión de Empleados":
    st.subheader(f"Gestión y Catálogo de Personal - Fecha Activa: {fecha_activa}")
    
    empleados_df = cargar_empleados_df(fecha_activa)

    tab_gest_chicas, tab_gest_general, tab_carga_masiva = st.tabs([
        "💃 Bailarinas y Chicas de Salón",
        "📋 Personal Operativo y General",
        "📂 Alta Masiva por Excel"
    ])

    with tab_gest_chicas:
        st.markdown(f"### Listado: Bailarinas y Chicas de Salón ({fecha_activa})")
        if not empleados_df.empty:
            df_chicas_gen = empleados_df[empleados_df['tipo'].apply(es_chica_o_bailarina)].copy()
            st.dataframe(df_chicas_gen, use_container_width=True)
        else:
            st.info("No hay registros en esta fecha.")

    with tab_gest_general:
        st.markdown(f"### Listado: Personal Operativo, Meseros y Fijos ({fecha_activa})")
        if not empleados_df.empty:
            df_general_gen = empleados_df[~empleados_df['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina)].copy()
            st.dataframe(df_general_gen, use_container_width=True)
        else:
            st.info("No hay registros en esta fecha.")

    with tab_carga_masiva:
        st.markdown("### Importar o Actualizar Personal Masivamente")
        st.info(f"Sube un archivo de Excel para dar de alta al personal en la fecha activa: **{fecha_activa}**.")

        filas_plantilla = []
        for idx, (puesto, sueldo) in enumerate(PUESTOS_CATALOGO.items(), start=1):
            filas_plantilla.append({"Nombre": f"Ejemplo Empleado {idx}", "Puesto": puesto, "Sueldo Base": sueldo})
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
            st.dataframe(df_subido.head(), use_container_width=True)

            if st.button("Procesar e Importar Personal"):
                columnas_necesarias = {'Nombre', 'Puesto', 'Sueldo Base'}
                if not columnas_necesarias.issubset(df_subido.columns):
                    st.error("El archivo Excel debe contener las columnas: Nombre, Puesto y Sueldo Base.")
                else:
                    registrados = 0
                    for _, row in df_subido.iterrows():
                        nombre_emp = str(row['Nombre']).strip()
                        puesto_emp = str(row['Puesto']).strip()
                        sueldo_emp = float(row['Sueldo Base']) if pd.notna(row['Sueldo Base']) else 0.0

                        if not nombre_emp:
                            continue
                        if puesto_emp not in PUESTOS_CATALOGO:
                            puesto_emp = "Mesero (Comisiones)"

                        agregar_empleado(nombre_emp, puesto_emp, sueldo_emp, fecha_str=fecha_activa)
                        registrados += 1

                    st.success(f"¡Importación completada para el día {fecha_activa}! Empleados procesados: {registrados}")
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
                index=list(PUESTOS_CATALOGO.keys()).index(emp_actual['tipo']) if emp_actual['tipo'] in PUESTOS_CATALOGO else 0,
                key="sel_tipo_mod"
            )
            sueldo_sugerido = PUESTOS_CATALOGO.get(nuevo_tipo_edit, float(emp_actual['sueldo_base']))
            nuevo_sueldo_edit = st.number_input("Sueldo Base ($)", value=sueldo_sugerido, format="%.2f", key="edit_sueldo_input")

            if st.button("Actualizar Empleado"):
                actualizar_empleado(int(emp_actual['id']), nuevo_tipo_edit, nuevo_sueldo_edit, fecha_str=fecha_activa)
                st.success(f"¡Datos de {emp_a_editar} actualizados para el {fecha_activa}!")
                st.rerun()

    with col_der:
        st.markdown(f"### Agregar Empleado Manual ({fecha_activa})")
        with st.form("form_empleado"):
            nuevo_nombre = st.text_input("Nombre Completo")
            nuevo_tipo = st.selectbox("Puesto", list(PUESTOS_CATALOGO.keys()), key="form_puesto")
            nuevo_sueldo = st.number_input("Sueldo Base ($)", value=PUESTOS_CATALOGO[nuevo_tipo], format="%.2f", key="form_sueldo_input")

            if st.form_submit_button("Guardar Empleado"):
                if nuevo_nombre.strip():
                    agregar_empleado(nuevo_nombre, nuevo_tipo, nuevo_sueldo, fecha_str=fecha_activa)
                    st.success(f"¡Guardado con éxito para el {fecha_activa}!")
                    st.rerun()
                else:
                    st.error("El nombre no puede estar vacío.")

# --- SECCIÓN 3: CORTE Y NÓMINA FINAL ---
elif opcion == "3. Corte y Nómina Final":
    st.subheader(f"Cálculo de Nómina Semanal por Categorías - Fecha: {fecha_activa}")

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
                key=f"pen_{key_sufijo}_{emp_id}",
                disabled=not puede_modificar
            )

            if puede_modificar and (penalizada_cambiada != penalizada_actual):
                actualizar_empleado(emp_id, emp['tipo'], sueldo_base, vales_emp, penalizada_cambiada, descuento_emp, transf_emp, fecha_str=fecha_activa)
                st.rerun()

            extras = 0.0
            boons_cant, boons_monto = 0.0, 0.0
            copa_cant, copa_monto = 0.0, 0.0
            strong_cant, strong_monto = 0.0, 0.0
            vip3_cant, vip3_monto = 0.0, 0.0
            priv_promo_cant, priv_promo_monto = 0.0, 0.0
            vip5_priv_art_cant, vip5_priv_art_monto = 0.0, 0.0
            vip15_cant, vip15_monto = 0.0, 0.0
            vip30_cant, vip30_monto = 0.0, 0.0

            if not chicas_totales.empty and 'empleado_id' in chicas_totales.columns:
                sus_filas = chicas_totales[chicas_totales['empleado_id'] == emp_id]
                if not sus_filas.empty:
                    for _, f_prod in sus_filas.iterrows():
                        desc = str(f_prod['descripcion']).upper()
                        cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                        com_unit = 80.0 if 'PRIVADO PROMO' in desc else (300.0 if 'PRIVADO ARTISTA' in desc else float(f_prod['comision_unitaria']))
                        subtotal_prod = cant * com_unit
                        
                        if 'PRIVADO PROMO' in desc:
                            priv_promo_cant += cant
                            priv_promo_monto += subtotal_prod
                        elif 'PRIVADO ARTISTA' in desc:
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

                    extras = boons_monto + copa_monto + strong_monto + vip3_monto + priv_promo_monto + vip5_priv_art_monto + vip15_monto + vip30_monto

            if penalizada_cambiada:
                extras = extras / 2.0
                boons_monto /= 2.0
                copa_monto /= 2.0
                strong_monto /= 2.0
                vip3_monto /= 2.0
                priv_promo_monto /= 2.0
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
                "Privados Promo": f"{int(priv_promo_cant)} (${priv_promo_monto:,.2f})",
                "VIP 5 / Priv / Artista": f"{int(vip5_priv_art_cant)} (${vip5_priv_art_monto:,.2f})",
                "VIP 15": f"{int(vip15_cant)} (${vip15_monto:,.2f})",
                "VIP 30": f"{int(vip30_cant)} (${vip30_monto:,.2f})",
                "_b_cant": boons_cant, "_b_m": boons_monto,
                "_c_cant": copa_cant, "_c_m": copa_monto,
                "_s_cant": strong_cant, "_s_m": strong_monto,
                "_v3_cant": vip3_cant, "_v3_m": vip3_monto,
                "_priv_promo_cant": priv_promo_cant, "_priv_promo_m": priv_promo_monto,
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

        df_estilizado = df_res[cols_mostrar].style.apply(resaltar_filas, axis=1).map(pintar_negativos, subset=['Total a Pagar'])
        editor_key = f"editor_sueldos_{key_sufijo}"
        
        columnas_deshabilitadas = [c for c in cols_mostrar if c not in ["Sueldo Base", "Vales", "Transferencia", "Descuento"]]
        if not puede_modificar:
            columnas_deshabilitadas = cols_mostrar

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
            disabled=columnas_deshabilitadas,
            use_container_width=True,
            key=editor_key
        )

        actualizado_flag = False
        if puede_modificar and (editor_key in st.session_state):
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
                
                actualizar_empleado(e_id, puesto_emp, nuevo_sb, nuevo_vales, penalizada_bd, nuevo_desc, nueva_transf, fecha_str=fecha_activa)
                actualizado_flag = True

        if actualizado_flag:
            st.rerun()

        st.markdown("---")
        st.markdown(f"##### 📊 Totales de Nómina - {nombre_pestana}")
        
        subtotal = float(df_res['Total a Pagar'].sum())
        total_vales_grupo = float(df_res['Vales'].sum())
        total_transf_grupo = float(df_res['Transferencia'].sum())
        total_descuento_grupo = float(df_res['Descuento'].sum())

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric(f"Subtotal Nómina", f"${subtotal:,.2f}")
        col_m2.metric(f"Total Vales", f"${total_vales_grupo:,.2f}")
        col_m3.metric(f"Total Transferencias", f"${total_transf_grupo:,.2f}")
        col_m4.metric(f"Total Descuentos", f"${total_descuento_grupo:,.2f}")

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
                if any(p in puesto_upper_check for p in ["AYUDANTE", "BARMAN", "GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                    p_tarj_tot = ventas_totales.get('propina_tarjeta', 0.0).sum() * 0.84
                    p_efec_tot = ventas_totales.get('propina_efectivo', 0.0).sum()
                    p_vale_tot = ventas_totales.get('propina_vales', 0.0).sum()
                    p_cred_tot = ventas_totales.get('propina_credito', 0.0).sum() if 'propina_credito' in ventas_totales.columns else 0.0
                    propinas = (p_tarj_tot + p_efec_tot + p_vale_tot + p_cred_tot) * (porcentaje_propina / 100.0)
                else:
                    filas_mesero = ventas_totales[ventas_totales['idmesero'] == emp_id]
                    if not filas_mesero.empty:
                        p_tarj = filas_mesero.get('propina_tarjeta', 0.0).sum() * 0.84
                        p_efec = filas_mesero.get('propina_efectivo', 0.0).sum()
                        p_vale = filas_mesero.get('propina_vales', 0.0).sum()
                        p_cred = filas_mesero.get('propina_credito', 0.0).sum() if 'propina_credito' in ventas_totales.columns else 0.0
                        propinas = (p_tarj + p_efec + p_vale + p_cred) * (porcentaje_propina / 100.0)

            if any(p in puesto_upper_check for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                if not chicas_totales.empty:
                    for _, f_prod in chicas_totales.iterrows():
                        desc = str(f_prod['descripcion'])
                        cant = float(f_prod['cantidad']) if pd.notna(f_prod['cantidad']) else 0.0
                        comisiones_prod += cant * calcular_comision_gerencia_caja(desc)

            total_bruto = sueldo_base + propinas + comisiones_prod
            total_pagar = total_bruto - vales_emp - transf_emp

            res_general.append({
                "ID": emp_id, "Nombre": nombre, "Puesto": tipo,
                "Total a Pagar": total_pagar, "Sueldo Base": sueldo_base,
                "Vales": vales_emp, "Transferencia": transf_emp,
                "Propina (%)": f"↑ {porcentaje_propina:.1f}% (${propinas:,.2f})",
                "Comisiones": comisiones_prod, "_propinas_num": propinas
            })

        df_res_general = pd.DataFrame(res_general)
        cols_mostrar_gen = ["ID", "Nombre", "Puesto", "Total a Pagar", "Sueldo Base", "Vales", "Transferencia", "Propina (%)", "Comisiones"]
        editor_key_gen = f"editor_sueldos_gen_{key_sufijo}"

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

        df_editado_gen = st.data_editor(
            df_estilizado_gen,
            height=min(max(len(df_res_general) * 45 + 40, 150), 900),
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "Total a Pagar": st.column_config.NumberColumn("Total a Pagar ($)", format="$%.2f", disabled=True),
                "Sueldo Base": st.column_config.NumberColumn("Sueldo Base ($)", format="$%.2f", required=True),
                "Vales": st.column_config.NumberColumn("Vales ($)", format="$%.2f", required=True),
                "Transferencia": st.column_config.NumberColumn("Transferencia ($)", format="$%.2f", required=True),
                "Propina (%)": st.column_config.TextColumn("Propina (%)", disabled=True),
                "Comisiones": st.column_config.NumberColumn("Comisiones ($)", format="$%.2f", disabled=True),
            },
            disabled=cols_disabled_gen,
            use_container_width=True,
            key=editor_key_gen
        )

        actualizado_gen_flag = False
        if puede_modificar and (editor_key_gen in st.session_state):
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
                
                actualizar_empleado(e_id, puesto_emp, nuevo_sb, nuevo_vales, penalizada_bd, descuento_bd, nueva_transf, fecha_str=fecha_activa)
                actualizado_gen_flag = True

        if actualizado_gen_flag:
            st.rerun()

        st.markdown("---")
        st.markdown(f"##### 📊 Totales de Nómina - {nombre_pestana}")
        tot_sb = float(df_res_general['Sueldo Base'].sum())
        tot_prop = float(df_res_general['_propinas_num'].sum())
        tot_com = float(df_res_general['Comisiones'].sum())
        sub_g = float(df_res_general['Total a Pagar'].sum())

        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.metric("Total Sueldos Base", f"${tot_sb:,.2f}")
        col_t2.metric("Total Propinas", f"${tot_prop:,.2f}")
        col_t3.metric("Total Comisiones", f"${tot_com:,.2f}")
        col_t4.metric(f"Subtotal", f"${sub_g:,.2f}")

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

    gasto_previo = cargar_gastos_hoy(fecha_activa)
    g_cocina_val = float(gasto_previo.gasto_cocina) if gasto_previo else 0.0
    g_compras_val = float(gasto_previo.gasto_compras) if gasto_previo else 0.0
    g_vales_val = float(gasto_previo.gasto_vales) if gasto_previo else 0.0

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        gasto_cocina = st.number_input("Gastos - Cocina ($)", value=g_cocina_val, format="%.2f", disabled=not puede_modificar)
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
        efectivo_ventas = float((ventas_acumuladas.get('efectivo', 0.0) + ventas_acumuladas.get('propina_efectivo', 0.0)).sum())
        tarjeta_ventas = float((ventas_acumuladas.get('tarjeta', 0.0) + ventas_acumuladas.get('propina_tarjeta', 0.0)).sum())
        transferencia_ventas = float((ventas_acumuladas.get('vales', 0.0) + ventas_acumuladas.get('propina_vales', 0.0)).sum())
        ventas_por_cobrar = float((ventas_acumuladas.get('otros', 0.0) + ventas_acumuladas.get('propinacredito', 0.0)).sum())

    ventas_totales_con_propinas = efectivo_ventas + tarjeta_ventas + transferencia_ventas + ventas_por_cobrar

    pdf_buffer = generar_pdf_corte(
        fecha_activa, ventas_totales_con_propinas, efectivo_ventas, tarjeta_ventas, 
        transferencia_ventas, ventas_por_cobrar, 0.0, 0.0,
        0.0, 0.0, gasto_cocina, gasto_compras, gasto_vales, 
        0.0, pd.DataFrame(), empleados_dashboard_df, chicas_acumuladas
    )
    st.download_button(
        label="📥 Descargar Reporte Ejecutivo en PDF (Completo)",
        data=pdf_buffer,
        file_name=f"Reporte_Cierre_Ejecutivo_{fecha_activa}.pdf",
        mime="application/pdf",
        type="primary"
    )

# --- SECCIÓN 5: REPORTE DE NÓMINA POR PERIODOS ---
elif opcion == "5. Reporte de Nómina por Periodos":
    st.subheader("📅 Reporte Histórico y Acumulado de Nómina por Periodos")
    st.info("Selecciona un rango de fechas para consultar el resumen de sueldos, comisiones y propinas acumuladas del personal.")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        fecha_inicio_per = st.date_input("Fecha de Inicio", datetime.now(), key="rango_ini_per")
    with col_p2:
        fecha_fin_per = st.date_input("Fecha de Fin", datetime.now(), key="rango_fin_per")

    f_ini_str = fecha_inicio_per.strftime('%Y-%m-%d')
    f_fin_str = fecha_fin_per.strftime('%Y-%m-%d')
    rango_etiqueta = f"{f_ini_str} al {f_fin_str}"

    if st.button("🔍 Consultar Periodo"):
        empleados_rango = cargar_empleados_rango_df(f_ini_str, f_fin_str)
        chicas_rango = cargar_chicas_rango_df(f_ini_str, f_fin_str)
        ventas_rango = cargar_ventas_rango_df(f_ini_str, f_fin_str)

        if empleados_rango.empty:
            st.warning(f"No se encontraron registros de nómina entre {f_ini_str} y {f_fin_str}.")
        else:
            tab_rep_bailarinas, tab_rep_meseros, tab_rep_seguridad, tab_rep_general = st.tabs([
                "💃 Bailarinas y Chicas",
                "👥 Meseros y Ayudantes",
                "🛡️ Seguridad",
                "📋 Personal General y Fijo"
            ])

            # 1. BAILARINAS (Sin ID, con Asistencias)
            with tab_rep_bailarinas:
                st.markdown(f"### Resumen de Bailarinas y Chicas ({rango_etiqueta})")
                df_bailarinas_rango = empleados_rango[empleados_rango['tipo'].apply(es_chica_o_bailarina)]
                
                if df_bailarinas_rango.empty:
                    st.info("No hay registros de bailarinas en este periodo.")
                else:
                    resumen_bailarinas = []
                    for _, emp in df_bailarinas_rango.iterrows():
                        emp_id = emp['id']
                        nombre = emp['nombre']
                        sueldo_base = float(emp['sueldo_base'])
                        descuento = float(emp['descuento_nomina'])
                        asistencias_emp = len(empleados_rango[empleados_rango['id'] == emp_id])

                        sus_prods = chicas_rango[chicas_rango['empleado_id'] == emp_id] if not chicas_rango.empty else pd.DataFrame()
                        
                        total_comisiones = 0.0
                        if not sus_prods.empty:
                            for _, p in sus_prods.iterrows():
                                desc = str(p['descripcion']).upper()
                                cant = float(p['cantidad']) if pd.notna(p['cantidad']) else 0.0
                                com_unit = float(p['comision_unitaria'])
                                
                                if 'PRIVADO PROMO' in desc:
                                    com_unit = 80.0
                                elif 'PRIVADO ARTISTA' in desc:
                                    com_unit = 300.0
                                elif 'BOONS ARTISTA' in desc:
                                    com_unit = 1000.0
                                elif 'BOONS' in desc:
                                    com_unit = 700.0
                                    
                                total_comisiones += cant * com_unit

                        total_bruto = sueldo_base + total_comisiones
                        total_pagar = total_bruto - descuento

                        resumen_bailarinas.append({
                            "Nombre": nombre,
                            "Asistencias": asistencias_emp,
                            "Sueldo Base Acumulado": sueldo_base,
                            "Comisiones Acumuladas": total_comisiones,
                            "Descuentos Acumulados": descuento,
                            "Total a Pagar": total_pagar
                        })

                    df_rep_b = pd.DataFrame(resumen_bailarinas)
                    st.dataframe(df_rep_b, use_container_width=True)
                    total_b_val = df_rep_b['Total a Pagar'].sum() if not df_rep_b.empty else 0.0
                    st.metric("Total General a Pagar (Bailarinas)", f"${total_b_val:,.2f}")
                    
                    pdf_b = generar_pdf_periodo("Resumen de Bailarinas y Chicas", rango_etiqueta, df_rep_b, total_b_val)
                    st.download_button("📥 Descargar PDF de Bailarinas", data=pdf_b, file_name=f"Nomina_Bailarinas_{rango_etiqueta}.pdf", mime="application/pdf", key="dl_pdf_b")

            # 2. MESEROS Y AYUDANTES (Sin ID, con Asistencias)
            with tab_rep_meseros:
                st.markdown(f"### Resumen de Meseros y Ayudantes ({rango_etiqueta})")
                mask_meseros_rango = (
                    empleados_rango['tipo'].astype(str).str.upper().str.contains("MESERO") &
                    ~empleados_rango['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN")
                ) | empleados_rango['tipo'].astype(str).str.upper().str.contains("AYUDANTE")
                df_meseros_rango = empleados_rango[mask_meseros_rango]

                if df_meseros_rango.empty:
                    st.info("No hay registros de meseros o ayudantes en este periodo.")
                else:
                    resumen_mes = []
                    for _, emp in df_meseros_rango.iterrows():
                        emp_id = emp['id']
                        tipo = emp['tipo'].upper()
                        sueldo_base = float(emp['sueldo_base'])
                        asistencias_emp = len(empleados_rango[empleados_rango['id'] == emp_id])
                        
                        porcentaje_propina = 5.0 if "AYUDANTE" in tipo else 50.0
                        propinas_acum = 0.0
                        if not ventas_rango.empty:
                            filas_m = ventas_rango[ventas_rango['idmesero'] == emp_id]
                            if not filas_m.empty:
                                p_tarj = filas_m.get('propina_tarjeta', 0.0).sum() * 0.84
                                p_efec = filas_m.get('propina_efectivo', 0.0).sum()
                                p_vale = filas_m.get('propina_vales', 0.0).sum()
                                p_cred = filas_m.get('propina_credito', 0.0).sum() if 'propina_credito' in ventas_rango.columns else 0.0
                                propinas_acum = (p_tarj + p_efec + p_vale + p_cred) * (porcentaje_propina / 100.0)

                        total_pagar = sueldo_base + propinas_acum
                        resumen_mes.append({
                            "Nombre": emp['nombre'],
                            "Puesto": emp['tipo'],
                            "Asistencias": asistencias_emp,
                            "Sueldo Base Acumulado": sueldo_base,
                            "Propinas Acumuladas": propinas_acum,
                            "Total a Pagar": total_pagar
                        })
                    df_rep_m = pd.DataFrame(resumen_mes)
                    st.dataframe(df_rep_m, use_container_width=True)
                    total_m_val = df_rep_m['Total a Pagar'].sum() if not df_rep_m.empty else 0.0
                    st.metric("Total General a Pagar (Meseros y Ayudantes)", f"${total_m_val:,.2f}")
                    
                    pdf_m = generar_pdf_periodo("Resumen de Meseros y Ayudantes", rango_etiqueta, df_rep_m, total_m_val)
                    st.download_button("📥 Descargar PDF de Meseros", data=pdf_m, file_name=f"Nomina_Meseros_{rango_etiqueta}.pdf", mime="application/pdf", key="dl_pdf_m")

            # 3. SEGURIDAD (Sin ID, con Asistencias)
            with tab_rep_seguridad:
                st.markdown(f"### Resumen de Personal de Seguridad ({rango_etiqueta})")
                df_seg_rango = empleados_rango[empleados_rango['tipo'].astype(str).str.upper().str.contains("SEGURIDAD")]

                if df_seg_rango.empty:
                    st.info("No hay registros de seguridad en este periodo.")
                else:
                    resumen_seg = []
                    for _, emp in df_seg_rango.iterrows():
                        sueldo_base = float(emp['sueldo_base'])
                        asistencias_emp = len(empleados_rango[empleados_rango['id'] == emp['id']])
                        resumen_seg.append({
                            "Nombre": emp['nombre'],
                            "Puesto": emp['tipo'],
                            "Asistencias": asistencias_emp,
                            "Sueldo Base Acumulado": sueldo_base,
                            "Total a Pagar": sueldo_base
                        })
                    df_rep_s = pd.DataFrame(resumen_seg)
                    st.dataframe(df_rep_s, use_container_width=True)
                    total_s_val = df_rep_s['Total a Pagar'].sum() if not df_rep_s.empty else 0.0
                    st.metric("Total General a Pagar (Seguridad)", f"${total_s_val:,.2f}")
                    
                    pdf_s = generar_pdf_periodo("Resumen de Seguridad", rango_etiqueta, df_rep_s, total_s_val)
                    st.download_button("📥 Descargar PDF de Seguridad", data=pdf_s, file_name=f"Nomina_Seguridad_{rango_etiqueta}.pdf", mime="application/pdf", key="dl_pdf_s")

            # 4. PERSONAL GENERAL Y FIJO (Sin ID, con Asistencias)
            with tab_rep_general:
                st.markdown(f"### Resumen de Personal General, Gerencia y Fijos ({rango_etiqueta})")
                mask_gen_rango = (
                    ~empleados_rango['tipo'].astype(str).str.upper().apply(es_chica_o_bailarina) &
                    ~empleados_rango['tipo'].astype(str).str.upper().str.contains("SEGURIDAD|AYUDANTE") &
                    ~(empleados_rango['tipo'].astype(str).str.upper().str.contains("MESERO") & ~empleados_rango['tipo'].astype(str).str.upper().str.contains("CAPITÁN|CAPITAN"))
                )
                df_gen_rango = empleados_rango[mask_gen_rango]

                if df_gen_rango.empty:
                    st.info("No hay registros de personal general en este periodo.")
                else:
                    resumen_gen = []
                    chicas_con_desc_count = len(df_bailarinas_rango)
                    
                    for _, emp in df_gen_rango.iterrows():
                        emp_id = emp['id']
                        tipo = emp['tipo'].upper()
                        sueldo_base = float(emp['sueldo_base'])
                        asistencias_emp = len(empleados_rango[empleados_rango['id'] == emp_id])
                        
                        propinas_o_comis = 0.0
                        if any(p in tipo for p in ["DJ", "ANIMADOR"]):
                            propinas_o_comis = chicas_con_desc_count * 40.0
                        elif "BARMAN" in tipo:
                            p_tarj_t = ventas_rango.get('propina_tarjeta', 0.0).sum() * 0.84 if not ventas_rango.empty else 0.0
                            p_efec_t = ventas_rango.get('propina_efectivo', 0.0).sum() if not ventas_rango.empty else 0.0
                            p_vale_t = ventas_rango.get('propina_vales', 0.0).sum() if not ventas_rango.empty else 0.0
                            propinas_o_comis = (p_tarj_t + p_efec_t + p_vale_t) * 0.10
                        elif any(p in tipo for p in ["GERENTE", "CAPITÁN", "CAPITAN", "CAJERO"]):
                            p_tarj_t = ventas_rango.get('propina_tarjeta', 0.0).sum() * 0.84 if not ventas_rango.empty else 0.0
                            p_efec_t = ventas_rango.get('propina_efectivo', 0.0).sum() if not ventas_rango.empty else 0.0
                            p_vale_t = ventas_rango.get('propina_vales', 0.0).sum() if not ventas_rango.empty else 0.0
                            propinas_o_comis = (p_tarj_t + p_efec_t + p_vale_t) * 0.08
                            
                            if not chicas_rango.empty:
                                for _, pr in chicas_rango.iterrows():
                                    propinas_o_comis += float(pr['cantidad']) * calcular_comision_gerencia_caja(str(pr['descripcion']))

                        total_pagar = sueldo_base + propinas_o_comis
                        resumen_gen.append({
                            "Nombre": emp['nombre'],
                            "Puesto": emp['tipo'],
                            "Asistencias": asistencias_emp,
                            "Sueldo Base Acumulado": sueldo_base,
                            "Propinas / Comisiones Acumuladas": propinas_o_comis,
                            "Total a Pagar": total_pagar
                        })
                    df_rep_g = pd.DataFrame(resumen_gen)
                    st.dataframe(df_rep_g, use_container_width=True)
                    total_g_val = df_rep_g['Total a Pagar'].sum() if not df_rep_g.empty else 0.0
                    st.metric("Total General a Pagar (Personal General y Fijo)", f"${total_g_val:,.2f}")
                    
                    pdf_g = generar_pdf_periodo("Resumen de Personal General y Fijo", rango_etiqueta, df_rep_g, total_g_val)
                    st.download_button("📥 Descargar PDF de Personal General", data=pdf_g, file_name=f"Nomina_General_{rango_etiqueta}.pdf", mime="application/pdf", key="dl_pdf_g")

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
                    crear_username = nuevo_user.strip()
                    crear_usuario(crear_username, nuevo_pass.strip(), nuevo_rol)
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
                edit_rol = st.selectbox("Rol", ["admin", "cajero", "gerente"], index=["admin", "cajero", "gerente"].index(emp_info['rol']) if emp_info['rol'] in ["admin", "cajero", "gerente"] else 0)
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