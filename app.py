# --- RESUMEN DE VENTAS POR MESERO EN TARJETAS DE MÉTRICAS ---
    st.markdown("---")
    st.markdown("#### 👥 Resumen de Ventas por Mesero (Día Actual)")
    
    empleados_df = cargar_empleados_df()
    if not ventas_acumuladas.empty and not empleados_df.empty:
        df_ventas_meseros = pd.merge(
            ventas_acumuladas, 
            empleados_df[['id', 'nombre']], 
            left_on='idmesero', 
            right_on='id', 
            how='left'
        )
        
        resumen_meseros = df_ventas_meseros.groupby('nombre').agg({
            'importe': 'sum',
            'efectivo': 'sum',
            'tarjeta': 'sum',
            'vales': 'sum',
            'otros': 'sum'
        }).reset_index()
        
        # Mostramos en filas de hasta 4 métricas por renglón
        for i in range(0, len(resumen_meseros), 4):
            cols = st.columns(4)
            for j in range(4):
                if i + j < len(resumen_meseros):
                    row = resumen_meseros.iloc[i + j]
                    nombre_mesero = row['nombre']
                    importe_total = row['importe']
                    efectivo_m = row['efectivo']
                    tarjeta_m = row['tarjeta']
                    
                    detalle_extra = f"Efect: ${efectivo_m:,.2f} | Tarj: ${tarjeta_m:,.2f}"
                    
                    with cols[j]:
                        st.metric(
                            label=f"MESERO: {nombre_mesero}",
                            value=f"${importe_total:,.2f}",
                            delta=detalle_extra
                        )
    else:
        st.info("No hay registros de ventas de meseros disponibles para mostrar en el resumen de hoy.")