# --- PESTAÑA 2: PERSONAL GENERAL Y OPERATIVO ---
    with tab_general:
        st.markdown("### Nómina: Personal Operativo, Meseros y Gerencia")
        
        # Filtro estricto: Excluye cualquier empleado que sea chica, bailarina o comisiones de chicas
        def es_personal_general(tipo_str, nombre_str):
            t = str(tipo_str).upper()
            n = str(nombre_str).upper()
            # Si es chica, bailarina, o se llama Janeth/Diann Ornelas, se excluye de meseros
            if ('CHICA' in t) or ('BAILARINA' in t) or ('JANETH' in n) or ('DIANN' in n):
                return False
            return True

        df_general_empleados = empleados_df[
            empleados_df.apply(lambda row: es_personal_general(row['tipo'], row['nombre']), axis=1)
        ] if not empleados_df.empty else empleados_df

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
                        if not ventas_emp.empty and 'propina_tarjeta' in ventas_emp.columns:
                            total_propina = float(
                                ventas_emp['propina_tarjeta'].sum() + 
                                ventas_emp['propina_efectivo'].sum() +
                                (ventas_emp['propina_vales'].sum() if 'propina_vales' in ventas_emp.columns else 0.0)
                            )
                            extras = total_propina * 0.50

                total_pagar = sueldo_base + extras
                res_general.append({
                    "ID": emp_id, "Nombre": nombre, "Puesto": tipo,
                    "Sueldo Base": sueldo_base, "Comisiones / Extras": extras, "Total a Pagar": total_pagar
                })
            df_res_general = pd.DataFrame(res_general)
            
            # --- TABLA EDITABLE PARA PERSONAL GENERAL ---
            df_editado_gen = st.data_editor(
                df_res_general,
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
                    "Comisiones / Extras": st.column_config.NumberColumn(
                        "Comisiones / Extras ($)",
                        format="$%.2f",
                        disabled=True
                    ),
                },
                disabled=["ID", "Nombre", "Puesto", "Comisiones / Extras"],
                use_container_width=True,
                key="editor_sueldos_general"
            )

            df_editado_gen['Total a Pagar'] = df_editado_gen['Sueldo Base'] + df_editado_gen['Comisiones / Extras']

            for _, row_ed in df_editado_gen.iterrows():
                e_id = row_ed['ID']
                nuevo_sb = float(row_ed['Sueldo Base'])
                original_sb = float(df_res_general[df_res_general['ID'] == e_id]['Sueldo Base'].values[0])
                if nuevo_sb != original_sb:
                    actualizar_empleado(row_ed['Nombre'], row_ed['Puesto'], nuevo_sb)

            sub_g = float(df_editado_gen['Total a Pagar'].sum())
            st.metric("Subtotal Nómina Personal General", f"${sub_g:,.2f}")