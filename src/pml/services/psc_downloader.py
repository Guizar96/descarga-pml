from __future__ import annotations

import asyncio
from datetime import date
from typing import Callable, Iterable, Optional

from pml.clients.psc_client import CenacePscClient
from pml.config.settings import Settings
from pml.domain.models import Mercado, PscFetchResult, PscRequestTask, Sistema
from pml.services.downloader import split_date_range

MAX_DIAS_POR_PETICION = 7


class PscDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_tasks(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        mercados: Iterable[Mercado] = ("MDA",),
        sistema: Sistema = "SIN",
        zonas: Iterable[str] = (),
    ) -> list[PscRequestTask]:
        bloque_dias = min(self.settings.bloque_dias, MAX_DIAS_POR_PETICION)
        bloques = split_date_range(fecha_inicio, fecha_fin, bloque_dias)

        tasks: list[PscRequestTask] = []
        for mercado in mercados:
            for ini, fin in bloques:
                tasks.append(
                    PscRequestTask(
                        fecha_inicio=ini, fecha_fin=fin, sistema=sistema, mercado=mercado, zonas=tuple(zonas)
                    )
                )
        return tasks

    async def run(
        self,
        client: CenacePscClient,
        tasks: Iterable[PscRequestTask],
        progress_cb: Optional[Callable[[PscFetchResult], None]] = None,
    ) -> list[PscFetchResult]:
        sem = asyncio.Semaphore(self.settings.concurrency)
        results: list[PscFetchResult] = []

        async def _one(t: PscRequestTask) -> PscFetchResult:
            async with sem:
                try:
                    payload, status, elapsed = await client.fetch_json(
                        t.sistema, t.mercado, t.zonas, t.fecha_inicio, t.fecha_fin
                    )
                    ok = status == 200
                    fr = PscFetchResult(task=t, ok=ok, status=status, payload=payload, elapsed_s=elapsed)
                except Exception as e:
                    fr = PscFetchResult(task=t, ok=False, error=str(e))

            if progress_cb:
                progress_cb(fr)
            return fr

        coros = [_one(t) for t in tasks]
        for fut in asyncio.as_completed(coros):
            results.append(await fut)

        return results
