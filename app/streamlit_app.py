import asyncio
from datetime import date
from pathlib import Path
import io

import pandas as pd
import streamlit as st
import plotly.express as px

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient
from pml.clients.pend_client import CenacePendClient
from pml.services.downloader import PmlDownloader
from pml.services.pend_downloader import PendDownloader
from pml.transforms.normalize import results_to_dataframes
from pml.transforms.normalize_pend import pend_results_to_dataframes
from pml.exports.excel import ExcelExporter
from pml.services.node_catalog import NodeCatalog
from pml.domain.models import MERCADOS

st.set_page_config(layout="wide")

# =========================
# CATÁLOGO
# =========================
CATALOG_PATH = Path("src/pml/data/Nodos.xlsx")
catalog = NodeCatalog(CATALOG_PATH).load()

all_nodos = sorted(catalog["Nodo"].unique())
all_sistemas = sorted(catalog["SISTEMA"].dropna().unique())
all_gerencias = sorted(catalog["GerenciaRegional"].dropna().unique())

today = date.today()
first_day = today.replace(day=1)

fmt = lambda x: f"${x:,.2f}" if pd.notna(x) else "-"

# =========================
# STATE
# =========================
if "df_raw" not in st.session_state:
    st.session_state.df_raw = None

if "excel_buffer" not in st.session_state:
    st.session_state.excel_buffer = None

if "mercados_sel" not in st.session_state:
    st.session_state.mercados_sel = ["MDA"]

if "pend_df_raw" not in st.session_state:
    st.session_state.pend_df_raw = None

if "pend_df_err" not in st.session_state:
    st.session_state.pend_df_err = None

if "pend_excel_buffer" not in st.session_state:
    st.session_state.pend_excel_buffer = None

if "pend_meta" not in st.session_state:
    st.session_state.pend_meta = {}

tab_pml, tab_pend = st.tabs(["PML · Nodos de transmisión", "PEND · Nodos distribuidos"])

# =========================================================================
# TAB 1: PML (nodos de transmisión)
# =========================================================================
with tab_pml:
    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 1.2, 1.3, 2, 2, 3.5, 2])

    fecha_inicio = c1.date_input("Fecha inicio", value=first_day, key="pml_fecha_inicio")
    fecha_fin = c2.date_input("Fecha fin", value=today, key="pml_fecha_fin")

    mercados_sel = c3.multiselect("Mercado", options=list(MERCADOS), default=["MDA"], key="pml_mercados")
    if not mercados_sel:
        mercados_sel = ["MDA"]

    sistemas_sel = c4.multiselect("Sistema", all_sistemas, key="pml_sistemas")
    gerencias_sel = c5.multiselect("Gerencia", all_gerencias, key="pml_gerencias")

    cat = catalog.copy()

    if sistemas_sel:
        cat = cat[cat["SISTEMA"].isin(sistemas_sel)]
    if gerencias_sel:
        cat = cat[cat["GerenciaRegional"].isin(gerencias_sel)]

    nodos_disponibles = sorted(cat["Nodo"].unique())

    selected_nodos = c6.multiselect(
        "Nodos",
        options=["(Todos)"] + nodos_disponibles,
        default=["(Todos)"],
        key="pml_nodos",
    )

    descargar = c7.button("⬇ Descargar", key="pml_descargar")
    limpiar = c7.button("🧹 Limpiar", key="pml_limpiar")

    st.markdown("## Precios marginales locales (PML)")

    if "(Todos)" in selected_nodos or not selected_nodos:
        selected_nodos = nodos_disponibles

    # =========================
    # DESCARGA
    # =========================
    if limpiar:
        st.session_state.df_raw = None
        st.session_state.excel_buffer = None

    if descargar:
        st.session_state.excel_buffer = None

        settings = Settings(bloque_dias=7, concurrency=25)
        nodos_dict = {n: n for n in selected_nodos}

        downloader = PmlDownloader(settings)
        tasks = downloader.build_tasks(nodos_dict, fecha_inicio, fecha_fin, mercados_sel)

        async def main():
            async with CenacePmlClient(settings) as client:
                return await downloader.run(client, tasks)

        results = asyncio.run(main())
        df_raw, _ = results_to_dataframes(results)

        st.session_state.df_raw = df_raw
        st.session_state.mercados_sel = mercados_sel

    # =========================
    # RENDER
    # =========================
    if st.session_state.df_raw is not None:

        df = st.session_state.df_raw.copy()
        df.columns = df.columns.str.strip()

        # =========================
        # COMPONENTES (detección robusta)
        # Nota: mantienes tu regla con acento en energía (como pediste)
        # =========================
        col_energia = next((c for c in df.columns if "energía" in c.lower()), None)
        col_perdida = next((c for c in df.columns if "perdida" in c.lower()), None)
        col_congestion = next((c for c in df.columns if "congestion" in c.lower()), None)

        comp_cols = [c for c in [col_energia, col_perdida, col_congestion] if c]

        # =========================
        # Mapa de nombres "bonitos" para VISTA (acentos)
        # =========================
        DISPLAY_NAMES = {}
        if col_energia:
            DISPLAY_NAMES[col_energia] = "Energía"
        if col_perdida:
            DISPLAY_NAMES[col_perdida] = "Pérdidas"
        if col_congestion:
            DISPLAY_NAMES[col_congestion] = "Congestión"

        # =========================
        # FECHA
        # =========================
        df["datetime"] = pd.to_datetime(df["Fecha"], dayfirst=True) + pd.to_timedelta(df["Hora"] - 1, unit="h")
        df["time"] = df["datetime"].dt.strftime("%d/%m/%Y T%H:00")

        # FIX hora 0-23 (consistente con gráficas)
        df["Hora"] = df["datetime"].dt.hour

        df = df[df["Nodo"].isin(selected_nodos)]

        # =========================
        # NOMBRE (desde catálogo)
        # =========================
        df = df.drop(columns=["Nombre"], errors="ignore")
        df = df.merge(catalog[["Nodo", "Nombre"]], on="Nodo", how="left")

        # =========================
        # MERCADO (MDA / MTR)
        # =========================
        if "Mercado" not in df.columns:
            df["Mercado"] = "MDA"
        df["Mercado"] = df["Mercado"].fillna("MDA")
        multi_mercado = df["Mercado"].nunique() > 1

        # Serie = etiqueta usada para colorear/agrupar cuando hay más de un nodo
        # y/o más de un mercado a la vez, para no mezclar MDA y MTR en una sola línea.
        if multi_mercado:
            df["Serie"] = df["Nodo"] + " · " + df["Mercado"]
        else:
            df["Serie"] = df["Nodo"]

        # =========================
        # KPIs
        # =========================
        mercados_presentes = sorted(df["Mercado"].unique())

        for mercado in mercados_presentes:
            d_m = df[df["Mercado"] == mercado] if multi_mercado else df

            if multi_mercado:
                st.markdown(f"**{mercado}**")

            if len(selected_nodos) == len(nodos_disponibles):
                df_kpi = d_m.groupby("datetime")["PML"].mean().reset_index()
            else:
                df_kpi = d_m

            mean_p = df_kpi["PML"].mean()
            max_p = df_kpi["PML"].max()
            min_p = df_kpi["PML"].min()
            std_p = df_kpi["PML"].std()

            comp_means = d_m[comp_cols].mean() if comp_cols else pd.Series(dtype=float)

            cols = st.columns(4 + len(comp_cols))

            cols[0].metric("PML", fmt(mean_p))
            cols[1].metric("Máx", fmt(max_p))
            cols[2].metric("Mín", fmt(min_p))
            cols[3].metric("Desv. est.", fmt(std_p))

            for i, c in enumerate(comp_cols):
                label = DISPLAY_NAMES.get(c, c)
                cols[4 + i].metric(label, fmt(comp_means[c]))

        # =========================
        # LÍNEA
        # =========================
        st.subheader("PML")

        if len(selected_nodos) == len(nodos_disponibles) and not multi_mercado:
            df_plot = df.groupby("datetime")["PML"].mean().reset_index()
            df_plot["time"] = df_plot["datetime"].dt.strftime("%d/%m/%Y T%H:00")
            fig = px.line(df_plot, x="time", y="PML")

        elif len(selected_nodos) == len(nodos_disponibles) and multi_mercado:
            df_plot = df.groupby(["datetime", "Mercado"])["PML"].mean().reset_index()
            df_plot["time"] = df_plot["datetime"].dt.strftime("%d/%m/%Y T%H:00")
            fig = px.line(df_plot, x="time", y="PML", color="Mercado")

        elif len(selected_nodos) == 1 and not multi_mercado:
            fig = px.line(df, x="time", y="PML")

        else:
            fig = px.line(df, x="time", y="PML", color="Serie")

        fig.update_layout(xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

        # =========================
        # COMPONENTES (con acentos en leyenda y tooltip)
        # =========================
        st.subheader("Componentes")

        if comp_cols:
            group_cols = ["datetime"] + (["Mercado"] if multi_mercado else [])
            comp_df = df.groupby(group_cols)[comp_cols].mean().reset_index()
            comp_df["time"] = comp_df["datetime"].dt.strftime("%d/%m/%Y T%H:00")

            # Renombrar SOLO para vista (acentos)
            comp_df = comp_df.rename(columns=DISPLAY_NAMES)

            view_comp_cols = list(DISPLAY_NAMES.values())

            id_vars = ["time"] + (["Mercado"] if multi_mercado else [])
            comp_long = comp_df.melt(
                id_vars=id_vars,
                value_vars=view_comp_cols,
                var_name="Componente",
                value_name="Valor"
            )

            fig_comp = px.bar(
                comp_long,
                x="time",
                y="Valor",
                color="Componente",
                barmode="relative",
                facet_row="Mercado" if multi_mercado else None
            )

            fig_comp.update_layout(
                xaxis_title=None,
                legend_title_text="Componente"
            )

            st.plotly_chart(fig_comp, use_container_width=True)
        else:
            st.info("No se detectaron columnas de componentes para graficar.")

        # =========================
        # TABLA (renombrada para vista, sin columnas auxiliares)
        # =========================
        df_display = df.drop(columns=["datetime", "time", "Serie"], errors="ignore")
        df_display = df_display.rename(columns=DISPLAY_NAMES)
        st.dataframe(df_display, use_container_width=True)

        # =========================
        # EXPORT ✅ OPTIMIZADO (Generar → Descargar)
        # =========================
        if st.button("📦 Generar Excel", key="pml_generar_excel"):
            with st.spinner("Generando Excel..."):
                buffer = io.BytesIO()
                meta = {
                    "fecha_inicio": str(fecha_inicio),
                    "fecha_fin": str(fecha_fin),
                    "mercados": ",".join(st.session_state.mercados_sel),
                }
                ExcelExporter().export(
                    st.session_state.df_raw,
                    None,
                    meta,
                    buffer
                )
                buffer.seek(0)
                st.session_state.excel_buffer = buffer

        if st.session_state.excel_buffer is not None:
            st.download_button(
                label="💾 Descargar Excel",
                data=st.session_state.excel_buffer,
                file_name=f"PML_{fecha_inicio}_{fecha_fin}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="pml_download_button",
            )

    else:
        st.info("Selecciona parámetros y presiona Descargar")

# =========================================================================
# TAB 2: PEND (nodos distribuidos / zonas de carga)
# =========================================================================
with tab_pend:
    st.markdown("## Precios de Energía en Nodos Distribuidos (PEND)")
    st.caption(
        "Precio promedio ponderado por Zona de Carga (nodos de distribución de CFE), calculado por CENACE "
        "a partir de los PML y los vectores de distribución de carga. Escribe las Zonas de Carga separadas "
        "por coma (nombre oficial CENACE, p. ej. ACAPULCO, AGUASCALIENTES, LOS CABOS); los espacios se "
        "convierten automáticamente a guiones."
    )

    p1, p2, p3, p4 = st.columns([1.2, 1.2, 1.2, 1.6])
    pend_fecha_inicio = p1.date_input("Fecha inicio", value=first_day, key="pend_fecha_inicio")
    pend_fecha_fin = p2.date_input("Fecha fin", value=today, key="pend_fecha_fin")
    pend_sistema = p3.selectbox("Sistema", options=["SIN", "BCA", "BCS"], key="pend_sistema")
    pend_mercados_sel = p4.multiselect("Mercado", options=list(MERCADOS), default=["MDA"], key="pend_mercados")
    if not pend_mercados_sel:
        pend_mercados_sel = ["MDA"]

    pend_zonas_text = st.text_input(
        "Zonas de Carga (separadas por coma)",
        value="ACAPULCO, AGUASCALIENTES",
        key="pend_zonas_text",
    )

    b1, _ = st.columns([1, 6])
    pend_descargar = b1.button("⬇ Descargar", key="pend_descargar")
    pend_limpiar = b1.button("🧹 Limpiar", key="pend_limpiar")

    if pend_limpiar:
        st.session_state.pend_df_raw = None
        st.session_state.pend_df_err = None
        st.session_state.pend_excel_buffer = None

    if pend_descargar:
        zonas = [z.strip() for z in pend_zonas_text.split(",") if z.strip()]

        if not zonas:
            st.warning("Escribe al menos una Zona de Carga.")
        else:
            st.session_state.pend_excel_buffer = None

            pend_settings = Settings(bloque_dias=7, concurrency=25)
            pend_downloader = PendDownloader(pend_settings)
            pend_tasks = pend_downloader.build_tasks(
                zonas, pend_fecha_inicio, pend_fecha_fin, pend_mercados_sel, sistema=pend_sistema
            )

            async def main_pend():
                async with CenacePendClient(pend_settings) as client:
                    return await pend_downloader.run(client, pend_tasks)

            pend_results = asyncio.run(main_pend())
            pend_df_raw, pend_df_err = pend_results_to_dataframes(pend_results)

            st.session_state.pend_df_raw = pend_df_raw
            st.session_state.pend_df_err = pend_df_err
            st.session_state.pend_meta = {
                "fecha_inicio": str(pend_fecha_inicio),
                "fecha_fin": str(pend_fecha_fin),
                "sistema": pend_sistema,
                "mercados": ",".join(pend_mercados_sel),
                "zonas": ",".join(zonas),
            }

    if st.session_state.pend_df_raw is not None:
        pdf_raw = st.session_state.pend_df_raw

        if pdf_raw.empty:
            st.info("No se encontraron datos para los parámetros seleccionados.")
        else:
            pdf = pdf_raw.copy()
            pdf["Mercado"] = pdf["Mercado"].fillna("MDA")
            pend_multi_mercado = pdf["Mercado"].nunique() > 1
            n_zonas = pdf["ZonaCarga"].nunique()

            pdf["datetime"] = pd.to_datetime(pdf["Fecha"], dayfirst=True) + pd.to_timedelta(pdf["Hora"] - 1, unit="h")
            pdf["time"] = pdf["datetime"].dt.strftime("%d/%m/%Y T%H:00")

            if pend_multi_mercado:
                pdf["Serie"] = pdf["ZonaCarga"] + " · " + pdf["Mercado"]
            else:
                pdf["Serie"] = pdf["ZonaCarga"]

            # =========================
            # KPIs
            # =========================
            for mercado in sorted(pdf["Mercado"].unique()):
                d_m = pdf[pdf["Mercado"] == mercado] if pend_multi_mercado else pdf

                if pend_multi_mercado:
                    st.markdown(f"**{mercado}**")

                cols = st.columns(4)
                cols[0].metric("PZ", fmt(d_m["PZ"].mean()))
                cols[1].metric("Máx", fmt(d_m["PZ"].max()))
                cols[2].metric("Mín", fmt(d_m["PZ"].min()))
                cols[3].metric("Desv. est.", fmt(d_m["PZ"].std()))

            # =========================
            # LÍNEA
            # =========================
            st.subheader("PZ (Precio por Zona de Carga)")

            if n_zonas == 1 and not pend_multi_mercado:
                fig = px.line(pdf, x="time", y="PZ")
            else:
                fig = px.line(pdf, x="time", y="PZ", color="Serie")

            fig.update_layout(xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

            # =========================
            # TABLA
            # =========================
            st.subheader("Datos")
            pdf_display = pdf.drop(columns=["datetime", "time", "Serie"], errors="ignore")
            st.dataframe(pdf_display, use_container_width=True)

            if st.session_state.pend_df_err is not None and not st.session_state.pend_df_err.empty:
                with st.expander(f"⚠ {len(st.session_state.pend_df_err)} peticiones con error"):
                    st.dataframe(st.session_state.pend_df_err, use_container_width=True)

            # =========================
            # EXPORT
            # =========================
            if st.button("📦 Generar Excel", key="pend_generar_excel"):
                with st.spinner("Generando Excel..."):
                    buffer = io.BytesIO()
                    ExcelExporter().export_pend(
                        st.session_state.pend_df_raw,
                        st.session_state.pend_df_err,
                        st.session_state.pend_meta,
                        buffer,
                    )
                    buffer.seek(0)
                    st.session_state.pend_excel_buffer = buffer

            if st.session_state.pend_excel_buffer is not None:
                st.download_button(
                    label="💾 Descargar Excel",
                    data=st.session_state.pend_excel_buffer,
                    file_name=f"PEND_{pend_fecha_inicio}_{pend_fecha_fin}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="pend_download_button",
                )

    else:
        st.info("Escribe una o más Zonas de Carga y presiona Descargar")
