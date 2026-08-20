import asyncio
from datetime import date
from pathlib import Path
import io

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient
from pml.clients.pend_client import CenacePendClient
from pml.clients.psc_client import CenacePscClient
from pml.clients.casc_client import CenaceCascClient
from pml.services.downloader import PmlDownloader
from pml.services.pend_downloader import PendDownloader
from pml.services.psc_downloader import PscDownloader
from pml.services.casc_downloader import CascDownloader
from pml.transforms.normalize import results_to_dataframes
from pml.transforms.normalize_pend import pend_results_to_dataframes
from pml.transforms.normalize_psc import psc_results_to_dataframes
from pml.transforms.normalize_casc import casc_results_to_dataframes
from pml.exports.excel import ExcelExporter
from pml.services.node_catalog import NodeCatalog
from pml.domain.models import MERCADOS
from pml.data.zonas_carga import ZONAS_CARGA

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
fmt_mw = lambda x: f"{x:,.2f} MW" if pd.notna(x) else "-"

TIPO_RESERVA_ORDER = [
    "Reserva de regulación secundaria",
    "Reserva rodante de 10 minutos",
    "Reserva no rodante de 10 minutos",
    "Reserva rodante suplementaria",
    "Reserva no rodante suplementarias",
]


def with_rangeslider(fig, tickformat="%d/%m/%Y %Hh"):
    """Agrega control deslizante en el eje X para navegar fácilmente periodos largos."""
    fig.update_xaxes(rangeslider_visible=True, tickformat=tickformat)
    return fig


def heatmap_hora(d, value_col, row_col, row_order=None, colorbar_title=None, aggfunc="mean"):
    """Heatmap con Hora en columnas (eje X) y row_col en filas (eje Y)."""
    pivot = d.pivot_table(index=row_col, columns="Hora", values=value_col, aggfunc=aggfunc)
    pivot = pivot.reindex(columns=range(24))

    if row_order is not None:
        pivot = pivot.reindex(row_order)
    else:
        pivot = pivot.sort_index()

    if pd.api.types.is_datetime64_any_dtype(pivot.index):
        y_labels = list(pivot.index.strftime("%d/%m/%Y"))
    else:
        y_labels = pivot.index.astype(str).tolist()

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{h:02d}:00" for h in pivot.columns],
            y=y_labels,
            colorscale="RdBu",
            reversescale=True,
            colorbar=dict(title=colorbar_title or value_col),
        )
    )
    height = min(900, max(320, 24 * len(pivot.index)))
    fig.update_layout(xaxis_title="Hora", margin=dict(l=10, r=10, t=30, b=10), height=height)
    return fig

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

if "psc_df_raw" not in st.session_state:
    st.session_state.psc_df_raw = None

if "psc_df_err" not in st.session_state:
    st.session_state.psc_df_err = None

if "psc_excel_buffer" not in st.session_state:
    st.session_state.psc_excel_buffer = None

if "psc_meta" not in st.session_state:
    st.session_state.psc_meta = {}

if "casc_df_raw" not in st.session_state:
    st.session_state.casc_df_raw = None

if "casc_df_err" not in st.session_state:
    st.session_state.casc_df_err = None

if "casc_excel_buffer" not in st.session_state:
    st.session_state.casc_excel_buffer = None

if "casc_meta" not in st.session_state:
    st.session_state.casc_meta = {}

tab_pml, tab_pend, tab_conexos = st.tabs(
    ["PML · Nodos de transmisión", "PEND · Nodos distribuidos", "Servicios conexos"]
)

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
            fig = px.line(df_plot, x="datetime", y="PML")

        elif len(selected_nodos) == len(nodos_disponibles) and multi_mercado:
            df_plot = df.groupby(["datetime", "Mercado"])["PML"].mean().reset_index()
            fig = px.line(df_plot, x="datetime", y="PML", color="Mercado")

        elif len(selected_nodos) == 1 and not multi_mercado:
            fig = px.line(df, x="datetime", y="PML")

        else:
            fig = px.line(df, x="datetime", y="PML", color="Serie")

        fig.update_layout(xaxis_title=None)
        fig = with_rangeslider(fig)
        st.plotly_chart(fig, use_container_width=True)

        # =========================
        # COMPONENTES (con acentos en leyenda y tooltip)
        # =========================
        st.subheader("Componentes")

        if comp_cols:
            group_cols = ["datetime"] + (["Mercado"] if multi_mercado else [])
            comp_df = df.groupby(group_cols)[comp_cols].mean().reset_index()

            # Renombrar SOLO para vista (acentos)
            comp_df = comp_df.rename(columns=DISPLAY_NAMES)

            view_comp_cols = list(DISPLAY_NAMES.values())

            id_vars = ["datetime"] + (["Mercado"] if multi_mercado else [])
            comp_long = comp_df.melt(
                id_vars=id_vars,
                value_vars=view_comp_cols,
                var_name="Componente",
                value_name="Valor"
            )

            fig_comp = px.bar(
                comp_long,
                x="datetime",
                y="Valor",
                color="Componente",
                barmode="relative",
                facet_row="Mercado" if multi_mercado else None
            )

            fig_comp.update_layout(
                xaxis_title=None,
                legend_title_text="Componente"
            )
            fig_comp = with_rangeslider(fig_comp)

            st.plotly_chart(fig_comp, use_container_width=True)
        else:
            st.info("No se detectaron columnas de componentes para graficar.")

        # =========================
        # HEATMAP (Hora × Día)
        # =========================
        st.subheader("Mapa de calor · PML (Hora × Día)")

        for mercado in mercados_presentes:
            d_m = (df[df["Mercado"] == mercado] if multi_mercado else df).copy()

            if multi_mercado:
                st.markdown(f"**{mercado}**")

            d_m["Dia"] = d_m["datetime"].dt.normalize()
            fig_heat = heatmap_hora(d_m, value_col="PML", row_col="Dia", colorbar_title="PML")
            st.plotly_chart(fig_heat, use_container_width=True)

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
        "a partir de los PML y los vectores de distribución de carga."
    )

    p1, p2, p3, p4 = st.columns([1.2, 1.2, 1.2, 1.6])
    pend_fecha_inicio = p1.date_input("Fecha inicio", value=first_day, key="pend_fecha_inicio")
    pend_fecha_fin = p2.date_input("Fecha fin", value=today, key="pend_fecha_fin")
    pend_sistema = p3.selectbox("Sistema", options=["SIN", "BCA", "BCS"], key="pend_sistema")
    pend_mercados_sel = p4.multiselect("Mercado", options=list(MERCADOS), default=["MDA"], key="pend_mercados")
    if not pend_mercados_sel:
        pend_mercados_sel = ["MDA"]

    pend_zonas_sel = st.multiselect(
        "Zonas de Carga",
        options=list(ZONAS_CARGA),
        default=["ACAPULCO", "AGUASCALIENTES"],
        key="pend_zonas_sel",
    )

    b1, _ = st.columns([1, 6])
    pend_descargar = b1.button("⬇ Descargar", key="pend_descargar")
    pend_limpiar = b1.button("🧹 Limpiar", key="pend_limpiar")

    if pend_limpiar:
        st.session_state.pend_df_raw = None
        st.session_state.pend_df_err = None
        st.session_state.pend_excel_buffer = None

    if pend_descargar:
        zonas = pend_zonas_sel

        if not zonas:
            st.warning("Selecciona al menos una Zona de Carga.")
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

            zonas_pedidas = [z for z in st.session_state.pend_meta.get("zonas", "").split(",") if z]
            zonas_sin_datos = sorted(set(zonas_pedidas) - set(pdf["ZonaCarga"].unique()))
            if zonas_sin_datos:
                st.warning(
                    f"Sin datos para: {', '.join(zonas_sin_datos)}. Probablemente pertenecen a otro "
                    f"Sistema Interconectado (BCA/BCS/SIN) distinto al seleccionado ({pend_sistema})."
                )

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
                fig = px.line(pdf, x="datetime", y="PZ")
            else:
                fig = px.line(pdf, x="datetime", y="PZ", color="Serie")

            fig.update_layout(xaxis_title=None)
            fig = with_rangeslider(fig)
            st.plotly_chart(fig, use_container_width=True)

            # =========================
            # HEATMAP (Hora × Día)
            # =========================
            st.subheader("Mapa de calor · PZ (Hora × Día)")

            for mercado in sorted(pdf["Mercado"].unique()):
                d_m = (pdf[pdf["Mercado"] == mercado] if pend_multi_mercado else pdf).copy()

                if pend_multi_mercado:
                    st.markdown(f"**{mercado}**")

                d_m["Dia"] = d_m["datetime"].dt.normalize()
                fig_heat = heatmap_hora(d_m, value_col="PZ", row_col="Dia", colorbar_title="PZ")
                st.plotly_chart(fig_heat, use_container_width=True)

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
        st.info("Selecciona una o más Zonas de Carga y presiona Descargar")

# =========================================================================
# TAB 3: SERVICIOS CONEXOS (SW-PSC precios + SW-CASC asignaciones)
# =========================================================================
with tab_conexos:
    st.markdown("## Servicios Conexos")
    st.caption(
        "Precios de Servicios Conexos (Reserva de Regulación Secundaria, Reservas Rodantes/No Rodantes de "
        "10 minutos y Reservas Suplementarias) por Zona de Reserva, para MDA y MTR. Desde 2018 cada Sistema "
        "Interconectado (SIN, BCA, BCS) opera con una sola Zona de Reserva con su mismo nombre, así que no "
        "hace falta especificarla — se traen todas automáticamente."
    )

    s1, s2, s3, s4 = st.columns([1.2, 1.2, 1.2, 1.6])
    psc_fecha_inicio = s1.date_input("Fecha inicio", value=first_day, key="psc_fecha_inicio")
    psc_fecha_fin = s2.date_input("Fecha fin", value=today, key="psc_fecha_fin")
    psc_sistema = s3.selectbox("Sistema", options=["SIN", "BCA", "BCS"], key="psc_sistema")
    psc_mercados_sel = s4.multiselect("Mercado (Precios)", options=list(MERCADOS), default=["MDA"], key="psc_mercados")
    if not psc_mercados_sel:
        psc_mercados_sel = ["MDA"]

    incluir_casc = st.checkbox(
        "Incluir Cantidades Asignadas de Servicios Conexos (CASC) — resultado de la ejecución del MDA, no existe para MTR",
        value=True,
        key="incluir_casc",
    )

    b1, _ = st.columns([1, 6])
    conexos_descargar = b1.button("⬇ Descargar", key="conexos_descargar")
    conexos_limpiar = b1.button("🧹 Limpiar", key="conexos_limpiar")

    if conexos_limpiar:
        st.session_state.psc_df_raw = None
        st.session_state.psc_df_err = None
        st.session_state.psc_excel_buffer = None
        st.session_state.casc_df_raw = None
        st.session_state.casc_df_err = None
        st.session_state.casc_excel_buffer = None

    if conexos_descargar:
        st.session_state.psc_excel_buffer = None
        st.session_state.casc_excel_buffer = None

        conexos_settings = Settings(bloque_dias=7, concurrency=25)

        psc_downloader = PscDownloader(conexos_settings)
        psc_tasks = psc_downloader.build_tasks(
            psc_fecha_inicio, psc_fecha_fin, psc_mercados_sel, sistema=psc_sistema
        )

        async def main_psc():
            async with CenacePscClient(conexos_settings) as client:
                return await psc_downloader.run(client, psc_tasks)

        psc_results = asyncio.run(main_psc())
        psc_df_raw, psc_df_err = psc_results_to_dataframes(psc_results)

        st.session_state.psc_df_raw = psc_df_raw
        st.session_state.psc_df_err = psc_df_err
        st.session_state.psc_meta = {
            "fecha_inicio": str(psc_fecha_inicio),
            "fecha_fin": str(psc_fecha_fin),
            "sistema": psc_sistema,
            "mercados": ",".join(psc_mercados_sel),
        }

        if incluir_casc:
            casc_downloader = CascDownloader(conexos_settings)
            casc_tasks = casc_downloader.build_tasks(psc_fecha_inicio, psc_fecha_fin, sistema=psc_sistema)

            async def main_casc():
                async with CenaceCascClient(conexos_settings) as client:
                    return await casc_downloader.run(client, casc_tasks)

            casc_results = asyncio.run(main_casc())
            casc_df_raw, casc_df_err = casc_results_to_dataframes(casc_results)

            st.session_state.casc_df_raw = casc_df_raw
            st.session_state.casc_df_err = casc_df_err
            st.session_state.casc_meta = {
                "fecha_inicio": str(psc_fecha_inicio),
                "fecha_fin": str(psc_fecha_fin),
                "sistema": psc_sistema,
            }
        else:
            st.session_state.casc_df_raw = None
            st.session_state.casc_df_err = None

    # =========================
    # RENDER: PSC
    # =========================
    if st.session_state.psc_df_raw is not None:
        psc_raw = st.session_state.psc_df_raw

        st.subheader("Precios de Servicios Conexos (PSC)")

        if psc_raw.empty:
            st.info("No se encontraron datos de PSC para los parámetros seleccionados.")
        else:
            psc_df = psc_raw.copy()
            psc_df["Mercado"] = psc_df["Mercado"].fillna("MDA")
            psc_multi_mercado = psc_df["Mercado"].nunique() > 1

            psc_df["datetime"] = pd.to_datetime(psc_df["Fecha"], dayfirst=True) + pd.to_timedelta(
                psc_df["Hora"] - 1, unit="h"
            )
            psc_df["time"] = psc_df["datetime"].dt.strftime("%d/%m/%Y T%H:00")

            for mercado in sorted(psc_df["Mercado"].unique()):
                d_m = psc_df[psc_df["Mercado"] == mercado] if psc_multi_mercado else psc_df

                if psc_multi_mercado:
                    st.markdown(f"**{mercado}**")

                cols = st.columns(4)
                cols[0].metric("Precio", fmt(d_m["Precio"].mean()))
                cols[1].metric("Máx", fmt(d_m["Precio"].max()))
                cols[2].metric("Mín", fmt(d_m["Precio"].min()))
                cols[3].metric("Desv. est.", fmt(d_m["Precio"].std()))

            fig_psc = px.line(
                psc_df,
                x="datetime",
                y="Precio",
                color="TipoReserva",
                facet_row="Mercado" if psc_multi_mercado else None,
            )
            fig_psc.update_layout(xaxis_title=None, legend_title_text="Tipo de reserva")
            fig_psc = with_rangeslider(fig_psc)
            st.plotly_chart(fig_psc, use_container_width=True)

            # =========================
            # HEATMAP (Hora × Tipo de reserva)
            # =========================
            st.subheader("Mapa de calor · Precio (Hora × Tipo de reserva)")

            for mercado in sorted(psc_df["Mercado"].unique()):
                d_m = psc_df[psc_df["Mercado"] == mercado] if psc_multi_mercado else psc_df

                if psc_multi_mercado:
                    st.markdown(f"**{mercado}**")

                tipos_presentes = d_m["TipoReserva"].unique()
                row_order = [t for t in TIPO_RESERVA_ORDER if t in tipos_presentes]
                row_order += sorted(set(tipos_presentes) - set(row_order))

                fig_heat = heatmap_hora(d_m, value_col="Precio", row_col="TipoReserva", row_order=row_order, colorbar_title="Precio")
                st.plotly_chart(fig_heat, use_container_width=True)

            psc_display = psc_df.drop(columns=["datetime", "time"], errors="ignore")
            st.dataframe(psc_display, use_container_width=True)

            if st.session_state.psc_df_err is not None and not st.session_state.psc_df_err.empty:
                with st.expander(f"⚠ {len(st.session_state.psc_df_err)} peticiones con error (PSC)"):
                    st.dataframe(st.session_state.psc_df_err, use_container_width=True)

            if st.button("📦 Generar Excel (PSC)", key="psc_generar_excel"):
                with st.spinner("Generando Excel..."):
                    buffer = io.BytesIO()
                    ExcelExporter().export_psc(
                        st.session_state.psc_df_raw,
                        st.session_state.psc_df_err,
                        st.session_state.psc_meta,
                        buffer,
                    )
                    buffer.seek(0)
                    st.session_state.psc_excel_buffer = buffer

            if st.session_state.psc_excel_buffer is not None:
                st.download_button(
                    label="💾 Descargar Excel (PSC)",
                    data=st.session_state.psc_excel_buffer,
                    file_name=f"PSC_{psc_fecha_inicio}_{psc_fecha_fin}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="psc_download_button",
                )

        # =========================
        # RENDER: CASC
        # =========================
        if st.session_state.casc_df_raw is not None:
            casc_raw = st.session_state.casc_df_raw
            st.divider()
            st.subheader("Cantidades Asignadas de Servicios Conexos (CASC · MDA)")

            if casc_raw.empty:
                st.info("No se encontraron datos de CASC para los parámetros seleccionados.")
            else:
                casc_df = casc_raw.copy()
                casc_df["datetime"] = pd.to_datetime(casc_df["Fecha"], dayfirst=True) + pd.to_timedelta(
                    casc_df["Hora"] - 1, unit="h"
                )
                casc_df["time"] = casc_df["datetime"].dt.strftime("%d/%m/%Y T%H:00")

                casc_cols = ["Reg. Secundaria", "Rodante 10 min", "No Rodante 10 min", "Suplementaria"]

                # =========================
                # TARJETAS
                # =========================
                cols = st.columns(4)
                for i, c in enumerate(casc_cols):
                    cols[i].metric(c, fmt_mw(casc_df[c].mean()))

                casc_long = casc_df.melt(
                    id_vars=["datetime", "Hora"],
                    value_vars=casc_cols,
                    var_name="Tipo de reserva",
                    value_name="MW",
                )

                fig_casc = px.bar(
                    casc_long,
                    x="datetime",
                    y="MW",
                    color="Tipo de reserva",
                    barmode="group",
                )
                fig_casc.update_layout(xaxis_title=None)
                fig_casc = with_rangeslider(fig_casc)
                st.plotly_chart(fig_casc, use_container_width=True)

                # =========================
                # HEATMAP (Hora × Tipo de reserva)
                # =========================
                st.subheader("Mapa de calor · CASC (Hora × Tipo de reserva)")
                fig_heat_casc = heatmap_hora(
                    casc_long, value_col="MW", row_col="Tipo de reserva", row_order=casc_cols, colorbar_title="MW"
                )
                st.plotly_chart(fig_heat_casc, use_container_width=True)

                casc_display = casc_df.drop(columns=["datetime", "time"], errors="ignore")
                st.dataframe(casc_display, use_container_width=True)

                if st.session_state.casc_df_err is not None and not st.session_state.casc_df_err.empty:
                    with st.expander(f"⚠ {len(st.session_state.casc_df_err)} peticiones con error (CASC)"):
                        st.dataframe(st.session_state.casc_df_err, use_container_width=True)

                if st.button("📦 Generar Excel (CASC)", key="casc_generar_excel"):
                    with st.spinner("Generando Excel..."):
                        buffer = io.BytesIO()
                        ExcelExporter().export_casc(
                            st.session_state.casc_df_raw,
                            st.session_state.casc_df_err,
                            st.session_state.casc_meta,
                            buffer,
                        )
                        buffer.seek(0)
                        st.session_state.casc_excel_buffer = buffer

                if st.session_state.casc_excel_buffer is not None:
                    st.download_button(
                        label="💾 Descargar Excel (CASC)",
                        data=st.session_state.casc_excel_buffer,
                        file_name=f"CASC_{psc_fecha_inicio}_{psc_fecha_fin}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="casc_download_button",
                    )

    else:
        st.info("Selecciona parámetros y presiona Descargar")
