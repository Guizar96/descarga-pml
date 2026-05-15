from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd


def resource_path(relative_path: str | Path) -> Path:
    """
    Devuelve ruta absoluta a un recurso.
    - En desarrollo: relativa al root del proyecto.
    - En PyInstaller onefile: relativa a sys._MEIPASS (carpeta temporal donde se extraen recursos).
    """
    rel = Path(relative_path)

    # PyInstaller onefile expone la carpeta temporal en sys._MEIPASS
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel  # type: ignore[attr-defined]

    # Desarrollo: asumimos root = carpeta donde está pyproject.toml (subiendo desde src/pml/services/)
    # services -> pml -> src -> <root>
    return Path(__file__).resolve().parents[3] / rel


class NodeCatalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> pd.DataFrame:
        # Resolver ruta compatible con exe y con dev
        path = resource_path(self.path)

        df = pd.read_excel(path, engine="openpyxl")
        return self.normalize(df)

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d.columns = [c.strip() for c in d.columns]

        d = d.rename(
            columns={
                "CLAVE": "Nodo",
                "NOMBRE": "Nombre",
                "GERENCIA REGIONAL DE TRANSMISIÓN": "GerenciaRegional",
            }
        )

        required = ["Nodo", "Nombre", "SISTEMA"]
        for c in required:
            if c not in d.columns:
                raise ValueError(f"El catálogo no contiene la columna requerida: {c}")

        d["Nodo"] = d["Nodo"].astype(str).str.strip()
        d["Nombre"] = d["Nombre"].astype(str).str.strip()
        d["SISTEMA"] = d["SISTEMA"].astype(str).str.strip()

        if "GerenciaRegional" in d.columns:
            d["GerenciaRegional"] = d["GerenciaRegional"].astype(str).str.strip()

        return d