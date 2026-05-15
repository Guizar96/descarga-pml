from __future__ import annotations

import pandas as pd


def build_pml_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    d = df.copy()

    # Asegurar tipos
    d["PML"] = pd.to_numeric(d["PML"], errors="coerce")

    # Fecha viene como dd/mm/aaaa (string); convertir a datetime
    d["Fecha_dt"] = pd.to_datetime(d["Fecha"], errors="coerce", dayfirst=True)

    # Filtrar registros válidos
    d = d.dropna(subset=["Fecha_dt", "PML", "Nodo"])

    # Mes en formato mm/aaaa
    d["Mes"] = d["Fecha_dt"].dt.strftime("%m/%Y")

    # Pivot: filas por nodo, columnas mes, valores promedio PML
    pivot = (
        d.pivot_table(index="Nodo", columns="Mes", values="PML", aggfunc="mean")
    )

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

    # Fila General (todos los nodos)
    general = d.pivot_table(index=None, columns="Mes", values="PML", aggfunc="mean")
    general = general[col_order]
    general["Promedio"] = d["PML"].mean()
    general.index = ["General"]

    # Concatenar: nodos arriba, general hasta abajo
    summary = pd.concat([pivot, general], axis=0)

    # Dejar "Nodo" como primera columna
    summary = summary.reset_index().rename(columns={"index": "Nodo"})

    return summary
