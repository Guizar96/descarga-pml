from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pml.config.settings import Settings


class CenacePmlClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "CenacePmlClient":
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

    def build_url(self, nodo: str, fecha_inicio: str, fecha_fin: str) -> str:
        return f"{self.settings.base_url}/{nodo}/{fecha_inicio}/{fecha_fin}/JSON"

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

    async def fetch_json(self, nodo: str, fecha_inicio: str, fecha_fin: str) -> tuple[dict, int, float]:
        if not self._session:
            raise RuntimeError("ClientSession no inicializada. Usa: async with CenacePmlClient(settings) as client")

        url = self.build_url(nodo, fecha_inicio, fecha_fin)

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