from __future__ import annotations

import pandas as pd

from pml.domain.models import PendFetchResult


_CANONICAL_COLUMNS = [
    "ZonaCarga",
    "Mercado",
    "Fecha",
    "Hora",
    "PZ",
    "Componente Energía",
    "Componente Perdida",
    "Componente Congestion",
]


_RENAME_MAP = {
    "fecha": "Fecha",
    "hora": "Hora",
    "pz": "PZ",
    "pz_ene": "Componente Energía",
    "pz_per": "Componente Perdida",
    "pz_cng": "Componente Congestion",
}


def extract_valores(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    resultados = payload.get("Resultados", []) or []
    valores: list[dict] = []
    for item in resultados:
        zona = item.get("zona_carga")
        for v in item.get("Valores", []) or []:
            v2 = dict(v)
            v2["zona_carga"] = zona
            valores.append(v2)
    return valores


def pend_results_to_dataframes(results: list[PendFetchResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    errors: list[dict] = []

    for r in results:
        t = r.task
        if r.ok and r.payload:
            for v in extract_valores(r.payload):
                v2 = dict(v)
                v2["Mercado"] = t.mercado
                rows.append(v2)
        else:
            errors.append(
                {
                    "Zonas": ",".join(t.zonas),
                    "Mercado": t.mercado,
                    "Sistema": t.sistema,
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

    existing_rename = {k: v for k, v in _RENAME_MAP.items() if k in df_raw.columns}
    df = df_raw.rename(columns=existing_rename)
    df = df.rename(columns={"zona_carga": "ZonaCarga"})

    if "Hora" in df.columns:
        df["Hora"] = pd.to_numeric(df["Hora"], errors="coerce").astype("Int64")

    for col in ["PZ", "Componente Energía", "Componente Perdida", "Componente Congestion"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Fecha" in df.columns:
        dt = pd.to_datetime(df["Fecha"], errors="coerce")
        df["Fecha"] = dt.dt.strftime("%d/%m/%Y")

    for c in _CANONICAL_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA

    df = df[_CANONICAL_COLUMNS].copy()

    return df, df_err
