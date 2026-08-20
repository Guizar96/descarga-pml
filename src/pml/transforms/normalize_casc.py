from __future__ import annotations

import pandas as pd

from pml.domain.models import CascFetchResult


_CANONICAL_COLUMNS = [
    "ZonaReserva",
    "Fecha",
    "Hora",
    "Reg. Secundaria",
    "Rodante 10 min",
    "No Rodante 10 min",
    "Suplementaria",
]

_RENAME_MAP = {
    "zona_reserva": "ZonaReserva",
    "fecha": "Fecha",
    "hora": "Hora",
    "res_reg": "Reg. Secundaria",
    "res_rod_10": "Rodante 10 min",
    "res_10": "No Rodante 10 min",
    "res_sup": "Suplementaria",
}


def extract_valores(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    resultados = payload.get("Resultados", []) or []
    valores: list[dict] = []
    for item in resultados:
        zona = item.get("zona_reserva")
        for v in item.get("Valores", []) or []:
            v2 = dict(v)
            v2["zona_reserva"] = zona
            valores.append(v2)
    return valores


def casc_results_to_dataframes(results: list[CascFetchResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    errors: list[dict] = []

    for r in results:
        t = r.task
        if r.ok and r.payload:
            rows.extend(extract_valores(r.payload))
        else:
            errors.append(
                {
                    "Zonas": ",".join(t.zonas) if t.zonas else "(todas)",
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

    df_raw = df_raw.rename(columns=_RENAME_MAP)

    df_raw["Hora"] = pd.to_numeric(df_raw["Hora"], errors="coerce").astype("Int64")
    for col in ["Reg. Secundaria", "Rodante 10 min", "No Rodante 10 min", "Suplementaria"]:
        if col in df_raw.columns:
            df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")

    dt = pd.to_datetime(df_raw["Fecha"], errors="coerce")
    df_raw["Fecha"] = dt.dt.strftime("%d/%m/%Y")

    for c in _CANONICAL_COLUMNS:
        if c not in df_raw.columns:
            df_raw[c] = pd.NA

    df_raw = df_raw[_CANONICAL_COLUMNS].copy()

    return df_raw, df_err
