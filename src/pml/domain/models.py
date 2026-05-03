from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


@dataclass(frozen=True)
class RequestTask:
    nodo: str
    fecha_inicio: date
    fecha_fin: date
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