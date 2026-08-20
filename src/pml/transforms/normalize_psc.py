from __future__ import annotations

import pandas as pd

from pml.domain.models import PscFetchResult


_CANONICAL_COLUMNS = ["ZonaReserva", "Mercado", "Fecha", "Hora", "TipoReserva", "Precio"]


def extract_valores(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    resultados = payload.get("Resultados", []) or []
    valores: list[dict] = []
    for item in resultados:
        zona = item.get("clv_zona_reserva")
        for v in item.get("Valores", []) or []:
            v2 = dict(v)
            v2["clv_zona_reserva"] = zona
            valores.append(v2)
    return valores


def psc_results_to_dataframes(results: list[PscFetchResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    errors: list[dict] = []

    for r in results:
        t = r.task
        if r.ok and r.payload:
            for v in extract_valores(r.payload):
                rows.append(
                    {
                        "ZonaReserva": v.get("clv_zona_reserva"),
                        "Mercado": t.mercado,
                        "Fecha": v.get("fecha"),
                        "Hora": v.get("hora"),
                        "TipoReserva": v.get("tipo_res"),
                        "Precio": v.get("pres"),
                    }
                )
        else:
            errors.append(
                {
                    "Zonas": ",".join(t.zonas) if t.zonas else "(todas)",
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

    df_raw["Hora"] = pd.to_numeric(df_raw["Hora"], errors="coerce").astype("Int64")
    df_raw["Precio"] = pd.to_numeric(df_raw["Precio"], errors="coerce")

    dt = pd.to_datetime(df_raw["Fecha"], errors="coerce")
    df_raw["Fecha"] = dt.dt.strftime("%d/%m/%Y")

    df_raw = df_raw[_CANONICAL_COLUMNS].copy()

    return df_raw, df_err
