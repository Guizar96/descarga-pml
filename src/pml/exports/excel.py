from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd

from pml.analysis.summary import build_pend_monthly_summary, build_pml_monthly_summary
from pml.services.node_catalog import NodeCatalog


class ExcelExporter:

    def _enrich_with_catalog(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega nombre de nodo desde catálogo y limpia duplicados.
        """
        CATALOG_PATH = Path("src/pml/data/nodos.xlsx")
        catalog = NodeCatalog(CATALOG_PATH).load()

        df = df.copy()
        df.columns = df.columns.str.strip()

        # evitar duplicados de nombre
        df = df.drop(columns=["Nombre"], errors="ignore")

        df = df.merge(
            catalog[["Nodo", "Nombre"]],
            on="Nodo",
            how="left"
        )

        # ordenar columnas
        if "Nombre" in df.columns:
            cols = ["Nodo", "Nombre"] + [
                c for c in df.columns if c not in ["Nodo", "Nombre"]
            ]
            df = df[cols]

        return df

    def export(
        self,
        df_raw: pd.DataFrame,
        df_err: pd.DataFrame | None,
        meta: dict,
        path  # puede ser str o BytesIO
    ):

        # =========================
        # VALIDACIÓN INICIAL
        # =========================
        if df_raw is None:
            df_raw = pd.DataFrame()

        df_raw = df_raw.copy()

        # asegurar tipo hora
        if "Hora" in df_raw.columns and df_raw["Hora"].notna().all():
            df_raw["Hora"] = df_raw["Hora"].astype(int)

        # =========================
        # ENRIQUECER
        # =========================
        if not df_raw.empty:
            df_raw = self._enrich_with_catalog(df_raw)

        # =========================
        # META
        # =========================
        meta2 = dict(meta)
        meta2["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_meta = pd.DataFrame([meta2])

        # =========================
        # SUMMARY
        # =========================
        try:
            df_summary = build_pml_monthly_summary(df_raw) if not df_raw.empty else pd.DataFrame()
        except Exception:
            df_summary = pd.DataFrame()

        # =========================
        # EXPORT ROBUSTO
        # =========================
        writer = pd.ExcelWriter(path, engine="openpyxl")

        try:
            hojas = 0

            # ===== RAW
            if not df_raw.empty:
                df_raw.to_excel(writer, sheet_name="RAW", index=False)
                hojas += 1

            # ===== META
            if not df_meta.empty:
                df_meta.to_excel(writer, sheet_name="META", index=False)
                hojas += 1

            # ===== SUMMARY
            if df_summary is not None and not df_summary.empty:
                df_summary.to_excel(writer, sheet_name="SUMMARY", index=False)
                hojas += 1

            # ===== ERRORS
            if isinstance(df_err, pd.DataFrame) and not df_err.empty:
                df_err.to_excel(writer, sheet_name="ERRORS", index=False)
                hojas += 1

            # =========================
            # ✅ GARANTIZAR AL MENOS UNA HOJA
            # =========================
            if hojas == 0:
                pd.DataFrame({
                    "Mensaje": ["No hay datos disponibles para exportar"]
                }).to_excel(
                    writer,
                    sheet_name="INFO",
                    index=False
                )

            # ✅ CRÍTICO PARA BYTESIO
            writer.close()

        except Exception as e:
            writer.close()
            raise e

        return path

    def _export_simple(
        self,
        df_raw: pd.DataFrame,
        df_err: pd.DataFrame | None,
        meta: dict,
        path,
    ):
        """Export genérico RAW/META/ERRORS, sin catálogo ni resumen mensual (usado por PSC/CASC)."""

        if df_raw is None:
            df_raw = pd.DataFrame()

        df_raw = df_raw.copy()

        if "Hora" in df_raw.columns and df_raw["Hora"].notna().all():
            df_raw["Hora"] = df_raw["Hora"].astype(int)

        meta2 = dict(meta)
        meta2["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_meta = pd.DataFrame([meta2])

        writer = pd.ExcelWriter(path, engine="openpyxl")

        try:
            hojas = 0

            if not df_raw.empty:
                df_raw.to_excel(writer, sheet_name="RAW", index=False)
                hojas += 1

            if not df_meta.empty:
                df_meta.to_excel(writer, sheet_name="META", index=False)
                hojas += 1

            if isinstance(df_err, pd.DataFrame) and not df_err.empty:
                df_err.to_excel(writer, sheet_name="ERRORS", index=False)
                hojas += 1

            if hojas == 0:
                pd.DataFrame({
                    "Mensaje": ["No hay datos disponibles para exportar"]
                }).to_excel(
                    writer,
                    sheet_name="INFO",
                    index=False
                )

            writer.close()

        except Exception as e:
            writer.close()
            raise e

        return path

    def export_psc(self, df_raw: pd.DataFrame, df_err: pd.DataFrame | None, meta: dict, path):
        """Exporta resultados del SW-PSC (Precios de Servicios Conexos)."""
        return self._export_simple(df_raw, df_err, meta, path)

    def export_casc(self, df_raw: pd.DataFrame, df_err: pd.DataFrame | None, meta: dict, path):
        """Exporta resultados del SW-CASC (Cantidades Asignadas de Servicios Conexos)."""
        return self._export_simple(df_raw, df_err, meta, path)

    def export_pend(
        self,
        df_raw: pd.DataFrame,
        df_err: pd.DataFrame | None,
        meta: dict,
        path,
    ):
        """Exporta resultados del SW-PEND (Precios de Energía en Nodos Distribuidos / Zonas de Carga)."""

        if df_raw is None:
            df_raw = pd.DataFrame()

        df_raw = df_raw.copy()

        if "Hora" in df_raw.columns and df_raw["Hora"].notna().all():
            df_raw["Hora"] = df_raw["Hora"].astype(int)

        meta2 = dict(meta)
        meta2["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_meta = pd.DataFrame([meta2])

        try:
            df_summary = build_pend_monthly_summary(df_raw) if not df_raw.empty else pd.DataFrame()
        except Exception:
            df_summary = pd.DataFrame()

        writer = pd.ExcelWriter(path, engine="openpyxl")

        try:
            hojas = 0

            if not df_raw.empty:
                df_raw.to_excel(writer, sheet_name="RAW", index=False)
                hojas += 1

            if not df_meta.empty:
                df_meta.to_excel(writer, sheet_name="META", index=False)
                hojas += 1

            if df_summary is not None and not df_summary.empty:
                df_summary.to_excel(writer, sheet_name="SUMMARY", index=False)
                hojas += 1

            if isinstance(df_err, pd.DataFrame) and not df_err.empty:
                df_err.to_excel(writer, sheet_name="ERRORS", index=False)
                hojas += 1

            if hojas == 0:
                pd.DataFrame({
                    "Mensaje": ["No hay datos disponibles para exportar"]
                }).to_excel(
                    writer,
                    sheet_name="INFO",
                    index=False
                )

            writer.close()

        except Exception as e:
            writer.close()
            raise e

        return path