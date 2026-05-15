from __future__ import annotations

import pandas as pd

from pml.domain.models import FetchResult


_CANONICAL_COLUMNS = [
    "Nodo",
    "Nombre",
    "Fecha",
    "Hora",
    "PML",
    "Componente Energía",
    "Componente Perdida",
    "Componente Congestion",
]


_RENAME_MAP = {
    "fecha": "Fecha",
    "hora": "Hora",
    "pml": "PML",
    "pml_ene": "Componente Energía",
    "pml_per": "Componente Perdida",
    "pml_cng": "Componente Congestion",
}


def extract_valores(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    resultados = payload.get("Resultados", []) or []
    valores: list[dict] = []
    for item in resultados:
        valores.extend(item.get("Valores", []) or [])
    return valores


def results_to_dataframes(results: list[FetchResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    errors: list[dict] = []

    for r in results:
        t = r.task
        if r.ok and r.payload:
            valores = extract_valores(r.payload)
            for v in valores:
                v2 = dict(v)
                v2["Nodo"] = t.nodo
                v2["Nombre"] = t.nombre
                rows.append(v2)
        else:
            errors.append(
                {
                    "Nodo": t.nodo,
                    "Nombre": t.nombre,
                    "FechaInicioBloque": t.fecha_inicio.isoformat(),
                    "FechaFinBloque": t.fecha_fin.isoformat(),
                    "Status": r.status,
                    "Error": r.error,
                    "Elapsed_s": r.elapsed_s,
                }
            )

    df_raw = pd.DataFrame(rows)
    df_err = pd.DataFrame(errors)

    if df_raw.empty:
        return df_raw, df_err

    # Renombrar a canónico (si existen)
    existing_rename = {k: v for k, v in _RENAME_MAP.items() if k in df_raw.columns}
    df = df_raw.rename(columns=existing_rename)

    # Tipos
    if "Hora" in df.columns:
        df["Hora"] = pd.to_numeric(df["Hora"], errors="coerce").astype("Int64")

    for col in ["PML", "Componente Energía", "Componente Perdida", "Componente Congestion"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fecha: convertir a dd/mm/aaaa (string)
    if "Fecha" in df.columns:
        dt = pd.to_datetime(df["Fecha"], errors="coerce")
        df["Fecha"] = dt.dt.strftime("%d/%m/%Y")

    # Garantizar columnas canónicas (si faltan, se crean)
    for c in _CANONICAL_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA

    # Reordenar y devolver solo las columnas canónicas
    df = df[_CANONICAL_COLUMNS].copy()

    return df, df_err