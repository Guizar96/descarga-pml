from __future__ import annotations

import pandas as pd


def _build_monthly_summary(df: pd.DataFrame, key_col: str, value_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    d = df.copy()

    # Asegurar tipos
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce")

    # Fecha viene como dd/mm/aaaa (string); convertir a datetime
    d["Fecha_dt"] = pd.to_datetime(d["Fecha"], errors="coerce", dayfirst=True)

    # Filtrar registros válidos
    d = d.dropna(subset=["Fecha_dt", value_col, key_col])

    if "Mercado" not in d.columns:
        d["Mercado"] = "MDA"
    d["Mercado"] = d["Mercado"].fillna("MDA")

    # Mes en formato mm/aaaa
    d["Mes"] = d["Fecha_dt"].dt.strftime("%m/%Y")

    # Pivot: filas por clave+mercado, columnas mes, valores promedio
    pivot = d.pivot_table(index=[key_col, "Mercado"], columns="Mes", values=value_col, aggfunc="mean")

    # Ordenar columnas cronológicamente (mm/aaaa) de manera robusta
    col_order = (
        pd.to_datetime(pivot.columns, format="%m/%Y")
        .sort_values()
        .strftime("%m/%Y")
        .tolist()
    )
    pivot = pivot[col_order]

    # Columna Promedio por fila
    pivot["Promedio"] = pivot.mean(axis=1)

    # Fila General por mercado (todas las claves)
    general = d.pivot_table(index="Mercado", columns="Mes", values=value_col, aggfunc="mean")
    general = general[col_order]
    general["Promedio"] = d.groupby("Mercado")[value_col].mean()

    summary = pivot.reset_index()

    general = general.reset_index()
    general[key_col] = "General"

    # Concatenar: claves arriba, general (por mercado) hasta abajo
    summary = pd.concat([summary, general], axis=0, ignore_index=True)
    summary = summary[[key_col, "Mercado"] + col_order + ["Promedio"]]

    return summary


def build_pml_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    return _build_monthly_summary(df, key_col="Nodo", value_col="PML")


def build_pend_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    return _build_monthly_summary(df, key_col="ZonaCarga", value_col="PZ")
