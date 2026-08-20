from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Iterable, Optional

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pml.config.settings import Settings


class CenacePscClient:
    """Cliente para el servicio web SW-PSC (Precios de Servicios Conexos, por Zona de Reserva)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "CenacePscClient":
        timeout = aiohttp.ClientTimeout(
            total=self.settings.timeout_total_s,
            connect=self.settings.timeout_connect_s,
        )
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def build_url(
        self,
        sistema: str,
        mercado: str,
        zonas: Iterable[str],
        fecha_inicio: date,
        fecha_fin: date,
    ) -> str:
        zonas = list(zonas)
        zc_segment = ""
        if zonas:
            lista_zc = ",".join(z.strip().upper().replace(" ", "-") for z in zonas)
            zc_segment = f"{lista_zc}/"

        return (
            f"{self.settings.base_url}/SWPSC/SIM/{sistema}/{mercado}/{zc_segment}"
            f"{fecha_inicio.year}/{fecha_inicio.month:02d}/{fecha_inicio.day:02d}/"
            f"{fecha_fin.year}/{fecha_fin.month:02d}/{fecha_fin.day:02d}/JSON"
        )

    def _retry_decorator(self):
        return retry(
            stop=stop_after_attempt(self.settings.retries),
            wait=wait_exponential(
                multiplier=0.8,
                min=self.settings.backoff_min_s,
                max=self.settings.backoff_max_s,
            ),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
            reraise=True,
        )

    async def fetch_json(
        self,
        sistema: str,
        mercado: str,
        zonas: Iterable[str],
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[dict, int, float]:
        if not self._session:
            raise RuntimeError("ClientSession no inicializada. Usa: async with CenacePscClient(settings) as client")

        url = self.build_url(sistema, mercado, zonas, fecha_inicio, fecha_fin)

        @_wrap(self._retry_decorator())
        async def _do():
            t0 = time.perf_counter()
            async with self._session.get(url) as resp:
                status = resp.status
                payload = await resp.json(content_type=None)
            elapsed = time.perf_counter() - t0
            return payload, status, elapsed

        return await _do()


def _wrap(decorator):
    def _decor(fn):
        return decorator(fn)
    return _decor
