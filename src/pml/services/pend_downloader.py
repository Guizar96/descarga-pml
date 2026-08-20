from __future__ import annotations

import asyncio
from datetime import date
from typing import Callable, Iterable, Optional

from pml.clients.pend_client import CenacePendClient
from pml.config.settings import Settings
from pml.domain.models import Mercado, PendFetchResult, PendRequestTask, Sistema
from pml.services.downloader import split_date_range

MAX_ZONAS_POR_PETICION = 10
MAX_DIAS_POR_PETICION = 7


def split_zonas(zonas: Iterable[str], chunk_size: int = MAX_ZONAS_POR_PETICION) -> list[list[str]]:
    zonas = list(zonas)
    return [zonas[i : i + chunk_size] for i in range(0, len(zonas), chunk_size)]


class PendDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_tasks(
        self,
        zonas: Iterable[str],
        fecha_inicio: date,
        fecha_fin: date,
        mercados: Iterable[Mercado] = ("MDA",),
        sistema: Sistema = "SIN",
    ) -> list[PendRequestTask]:
        bloque_dias = min(self.settings.bloque_dias, MAX_DIAS_POR_PETICION)
        bloques = split_date_range(fecha_inicio, fecha_fin, bloque_dias)
        zona_chunks = split_zonas(zonas)

        tasks: list[PendRequestTask] = []
        for mercado in mercados:
            for chunk in zona_chunks:
                for ini, fin in bloques:
                    tasks.append(
                        PendRequestTask(
                            zonas=tuple(chunk), fecha_inicio=ini, fecha_fin=fin, sistema=sistema, mercado=mercado
                        )
                    )
        return tasks

    async def run(
        self,
        client: CenacePendClient,
        tasks: Iterable[PendRequestTask],
        progress_cb: Optional[Callable[[PendFetchResult], None]] = None,
    ) -> list[PendFetchResult]:
        sem = asyncio.Semaphore(self.settings.concurrency)
        results: list[PendFetchResult] = []

        async def _one(t: PendRequestTask) -> PendFetchResult:
            async with sem:
                try:
                    payload, status, elapsed = await client.fetch_json(
                        t.sistema, t.mercado, t.zonas, t.fecha_inicio, t.fecha_fin
                    )
                    ok = status == 200
                    fr = PendFetchResult(task=t, ok=ok, status=status, payload=payload, elapsed_s=elapsed)
                except Exception as e:
                    fr = PendFetchResult(task=t, ok=False, error=str(e))

            if progress_cb:
                progress_cb(fr)
            return fr

        coros = [_one(t) for t in tasks]
        for fut in asyncio.as_completed(coros):
            results.append(await fut)

        return results
