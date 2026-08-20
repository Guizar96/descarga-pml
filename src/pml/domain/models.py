from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Optional

Mercado = Literal["MDA", "MTR"]
MERCADOS: tuple[Mercado, ...] = ("MDA", "MTR")


@dataclass(frozen=True)
class RequestTask:
    nodo: str
    fecha_inicio: date
    fecha_fin: date
    mercado: Mercado = "MDA"
    nombre: Optional[str] = None

    @property
    def rango_str(self) -> str:
        return f"{self.fecha_inicio.isoformat()}_{self.fecha_fin.isoformat()}"


@dataclass
class FetchResult:
    task: RequestTask
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    elapsed_s: Optional[float] = None


Sistema = Literal["SIN", "BCA", "BCS"]


@dataclass(frozen=True)
class PendRequestTask:
    zonas: tuple[str, ...]
    fecha_inicio: date
    fecha_fin: date
    sistema: Sistema = "SIN"
    mercado: Mercado = "MDA"

    @property
    def rango_str(self) -> str:
        return f"{self.fecha_inicio.isoformat()}_{self.fecha_fin.isoformat()}"


@dataclass
class PendFetchResult:
    task: PendRequestTask
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    elapsed_s: Optional[float] = None


@dataclass(frozen=True)
class PscRequestTask:
    fecha_inicio: date
    fecha_fin: date
    sistema: Sistema = "SIN"
    mercado: Mercado = "MDA"
    zonas: tuple[str, ...] = ()  # vacío = todas las Zonas de Reserva (parámetro omitido)

    @property
    def rango_str(self) -> str:
        return f"{self.fecha_inicio.isoformat()}_{self.fecha_fin.isoformat()}"


@dataclass
class PscFetchResult:
    task: PscRequestTask
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    elapsed_s: Optional[float] = None


@dataclass(frozen=True)
class CascRequestTask:
    fecha_inicio: date
    fecha_fin: date
    sistema: Sistema = "SIN"
    zonas: tuple[str, ...] = ()  # vacío = todas las Zonas de Reserva (parámetro omitido)

    @property
    def rango_str(self) -> str:
        return f"{self.fecha_inicio.isoformat()}_{self.fecha_fin.isoformat()}"


@dataclass
class CascFetchResult:
    task: CascRequestTask
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    elapsed_s: Optional[float] = None