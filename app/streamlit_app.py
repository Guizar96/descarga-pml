import asyncio
from datetime import date
from pathlib import Path
import io

import pandas as pd
import streamlit as st
import plotly.express as px

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient
from pml.services.downloader import PmlDownloader
from pml.transforms.normalize import results_to_dataframes
from pml.exports.excel import ExcelExporter
from pml.services.node_catalog import NodeCatalog

st.set_page_config(layout="wide")

# =========================
# CATÁLOGO
# =========================
CATALOG_PATH = Path("src/pml/data/Nodos.xlsx")
catalog = NodeCatalog(CATALOG_PATH).load()

all_nodos = sorted(catalog["Nodo"].unique())
all_sistemas = sorted(catalog["SISTEMA"].dropna().unique())
all_gerencias = sorted(catalog["GerenciaRegional"].dropna().unique())

# =========================
# STATE
# =========================
if "df_raw" not in st.session_state:
    st.session_state.df_raw = None

if "excel_buffer" not in st.session_state:
    st.session_state.excel_buffer = None

# =========================
# HEADER
# =========================
c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1.2, 2, 2, 4, 2])

today = date.today()
first_day = today.replace(day=1)

fecha_inicio = c1.date_input("Fecha inicio", value=first_day)
fecha_fin = c2.date_input("Fecha fin", value=today)

sistemas_sel = c3.multiselect("Sistema", all_sistemas)
gerencias_sel = c4.multiselect("Gerencia", all_gerencias)

cat = catalog.copy()

if sistemas_sel:
    cat = cat[cat["SISTEMA"].isin(sistemas_sel)]
if gerencias_sel:
    cat = cat[cat["GerenciaRegional"].isin(gerencias_sel)]

nodos_disponibles = sorted(cat["Nodo"].unique())

selected_nodos = c5.multiselect(
    "Nodos",
    options=["(Todos)"] + nodos_disponibles,
    default=["(Todos)"]
)

descargar = c6.button("⬇ Descargar")
limpiar = c6.button("🧹 Limpiar")

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
    tasks = downloader.build_tasks(nodos_dict, fecha_inicio, fecha_fin)

    async def main():
        async with CenacePmlClient(settings) as client:
            return await downloader.run(client, tasks)

    results = asyncio.run(main())
    df_raw, _ = results_to_dataframes(results)

    st.session_state.df_raw = df_raw

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

    fmt = lambda x: f"${x:,.2f}" if pd.notna(x) else "-"

    # =========================
    # KPIs
    # =========================
    if len(selected_nodos) == len(nodos_disponibles):
        df_kpi = df.groupby("datetime")["PML"].mean().reset_index()
    else:
        df_kpi = df

    mean_p = df_kpi["PML"].mean()
    max_p = df_kpi["PML"].max()
    min_p = df_kpi["PML"].min()
    std_p = df_kpi["PML"].std()

    comp_means = df[comp_cols].mean() if comp_cols else pd.Series(dtype=float)

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

    if len(selected_nodos) == len(nodos_disponibles):
        df_plot = df.groupby("datetime")["PML"].mean().reset_index()
        df_plot["time"] = df_plot["datetime"].dt.strftime("%d/%m/%Y T%H:00")
        fig = px.line(df_plot, x="time", y="PML")

    elif len(selected_nodos) == 1:
        fig = px.line(df, x="time", y="PML")

    else:
        fig = px.line(df, x="time", y="PML", color="Nodo")

    fig.update_layout(xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    # =========================
    # COMPONENTES (con acentos en leyenda y tooltip)
    # =========================
    st.subheader("Componentes")

    if comp_cols:
        comp_df = df.groupby("datetime")[comp_cols].mean().reset_index()
        comp_df["time"] = comp_df["datetime"].dt.strftime("%d/%m/%Y T%H:00")

        # Renombrar SOLO para vista (acentos)
        comp_df = comp_df.rename(columns=DISPLAY_NAMES)

        view_comp_cols = list(DISPLAY_NAMES.values())

        comp_long = comp_df.melt(
            id_vars=["time"],
            value_vars=view_comp_cols,
            var_name="Componente",
            value_name="Valor"
        )

        fig_comp = px.bar(
            comp_long,
            x="time",
            y="Valor",
            color="Componente",
            barmode="relative"
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
    df_display = df.drop(columns=["datetime", "time"], errors="ignore")
    df_display = df_display.rename(columns=DISPLAY_NAMES)
    st.dataframe(df_display, use_container_width=True)

    # =========================
    # EXPORT ✅ OPTIMIZADO (Generar → Descargar)
    # =========================
    if st.button("📦 Generar Excel"):
        with st.spinner("Generando Excel..."):
            buffer = io.BytesIO()
            ExcelExporter().export(
                st.session_state.df_raw,
                None,
                {},
                buffer
            )
            buffer.seek(0)
            st.session_state.excel_buffer = buffer

    if st.session_state.excel_buffer is not None:
        st.download_button(
            label="💾 Descargar Excel",
            data=st.session_state.excel_buffer,
            file_name=f"PML_{fecha_inicio}_{fecha_fin}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info("Selecciona parámetros y presiona Descargar")