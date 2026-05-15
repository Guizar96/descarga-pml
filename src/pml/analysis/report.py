from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


class ReportBuilder:
    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        d = df.copy()

        # Tipos
        d["PML"] = pd.to_numeric(d.get("PML"), errors="coerce")
        d["Hora"] = pd.to_numeric(d.get("Hora"), errors="coerce")
        d["Fecha_dt"] = pd.to_datetime(d.get("Fecha"), errors="coerce", dayfirst=True)

        d = d.dropna(subset=["Fecha_dt", "Hora", "PML", "Nodo"])
        d["Hora"] = d["Hora"].astype(int)

        # Timestamp (fecha + hora). Hora en tus datos parece 1..24
        # Convertimos a 0..23 para timestamp sumando (Hora-1) horas.
        d["ts"] = d["Fecha_dt"] + pd.to_timedelta(d["Hora"] - 1, unit="h")

        return d

    def kpis(self, df: pd.DataFrame) -> dict:
        d = self._prepare(df)
        if d.empty:
            return {"rows": 0}

        s = d["PML"]
        k = {
            "rows": int(len(d)),
            "pml_mean": float(s.mean()),
            "pml_min": float(s.min()),
            "pml_max": float(s.max()),
            "pml_std": float(s.std()),
            "neg_hours": int((s < 0).sum()),
            "neg_share": float((s < 0).mean()),
        }
        return k

    def fig_timeseries(self, df: pd.DataFrame):
        d = self._prepare(df)
        if d.empty:
            return None

        # Serie temporal por nodo
        fig = px.line(
            d.sort_values("ts"),
            x="ts",
            y="PML",
            color="Nodo",
            title="PML - Serie temporal",
        )
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    def fig_histogram(self, df: pd.DataFrame):
        d = self._prepare(df)
        if d.empty:
            return None

        fig = px.histogram(
            d,
            x="PML",
            color="Nodo",
            nbins=60,
            opacity=0.65,
            title="PML - Distribución",
        )
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    def fig_box_by_hour(self, df: pd.DataFrame):
        d = self._prepare(df)
        if d.empty:
            return None

        fig = px.box(
            d,
            x="Hora",
            y="PML",
            color="Nodo",
            title="PML - Boxplot por hora",
        )
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    def fig_heatmap_hour_day(self, df: pd.DataFrame, nodo: str | None = None):
        d = self._prepare(df)
        if d.empty:
            return None

        if nodo:
            d = d[d["Nodo"] == nodo]
            if d.empty:
                return None

        d["Dia"] = d["Fecha_dt"].dt.strftime("%d/%m/%Y")
        pivot = d.pivot_table(index="Hora", columns="Dia", values="PML", aggfunc="mean")

        fig = go.Figure(
            data=go.Heatmap(
                z=pivot.values,
                x=pivot.columns.tolist(),
                y=pivot.index.tolist(),
                colorscale="RdBu",
                reversescale=True,
                colorbar=dict(title="PML"),
            )
        )
        title = "PML - Heatmap (Hora × Día)" + (f" | {nodo}" if nodo else "")
        fig.update_layout(title=title, xaxis_title="Día", yaxis_title="Hora", margin=dict(l=10, r=10, t=50, b=10))
        return fig

    def top_hours(self, df: pd.DataFrame, n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
        d = self._prepare(df)
        if d.empty:
            return pd.DataFrame(), pd.DataFrame()

        cols = ["Nodo", "Nombre", "Fecha_dt", "Hora", "PML", "ts"]
        d2 = d[cols].copy()

        top_high = d2.sort_values("PML", ascending=False).head(n)
        top_low = d2.sort_values("PML", ascending=True).head(n)

        # Formateo de fecha para mostrar bonito
        for tdf in (top_high, top_low):
            tdf["Fecha"] = tdf["Fecha_dt"].dt.strftime("%d/%m/%Y")
            tdf.drop(columns=["Fecha_dt"], inplace=True)

        top_high = top_high[["Nodo", "Nombre", "Fecha", "Hora", "PML", "ts"]]
        top_low = top_low[["Nodo", "Nombre", "Fecha", "Hora", "PML", "ts"]]

        return top_high, top_low