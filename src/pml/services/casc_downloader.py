from __future__ import annotations

import asyncio
from datetime import date
from typing import Callable, Iterable, Optional

from pml.clients.casc_client import CenaceCascClient
from pml.config.settings import Settings
from pml.domain.models import CascFetchResult, CascRequestTask, Sistema
from pml.services.downloader import split_date_range

MAX_DIAS_POR_PETICION = 7


class CascDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_tasks(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        sistema: Sistema = "SIN",
        zonas: Iterable[str] = (),
    ) -> list[CascRequestTask]:
        bloque_dias = min(self.settings.bloque_dias, MAX_DIAS_POR_PETICION)
        bloques = split_date_range(fecha_inicio, fecha_fin, bloque_dias)

        return [
            CascRequestTask(fecha_inicio=ini, fecha_fin=fin, sistema=sistema, zonas=tuple(zonas))
            for ini, fin in bloques
        ]

    async def run(
        self,
        client: CenaceCascClient,
        tasks: Iterable[CascRequestTask],
        progress_cb: Optional[Callable[[CascFetchResult], None]] = None,
    ) -> list[CascFetchResult]:
        sem = asyncio.Semaphore(self.settings.concurrency)
        results: list[CascFetchResult] = []

        async def _one(t: CascRequestTask) -> CascFetchResult:
            async with sem:
                try:
                    payload, status, elapsed = await client.fetch_json(t.sistema, t.zonas, t.fecha_inicio, t.fecha_fin)
                    ok = status == 200
                    fr = CascFetchResult(task=t, ok=ok, status=status, payload=payload, elapsed_s=elapsed)
                except Exception as e:
                    fr = CascFetchResult(task=t, ok=False, error=str(e))

            if progress_cb:
                progress_cb(fr)
            return fr

        coros = [_one(t) for t in tasks]
        for fut in asyncio.as_completed(coros):
            results.append(await fut)

        return results
