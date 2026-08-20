from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Callable, Iterable, Optional

from pml.clients.cenace_client import CenacePmlClient
from pml.config.settings import Settings
from pml.domain.models import FetchResult, Mercado, RequestTask


def split_date_range(fecha_inicio: date, fecha_fin: date, bloque_dias: int) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cur = fecha_inicio
    while cur <= fecha_fin:
        end = min(cur + timedelta(days=bloque_dias - 1), fecha_fin)
        ranges.append((cur, end))
        cur = end + timedelta(days=1)
    return ranges


class PmlDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_tasks(
        self,
        nodos: dict[str, str],
        fecha_inicio: date,
        fecha_fin: date,
        mercados: Iterable[Mercado] = ("MDA",),
    ) -> list[RequestTask]:
        bloques = split_date_range(fecha_inicio, fecha_fin, self.settings.bloque_dias)
        tasks: list[RequestTask] = []
        for mercado in mercados:
            for nodo, nombre in nodos.items():
                for ini, fin in bloques:
                    tasks.append(
                        RequestTask(nodo=nodo, nombre=nombre, fecha_inicio=ini, fecha_fin=fin, mercado=mercado)
                    )
        return tasks

    async def run(
        self,
        client: CenacePmlClient,
        tasks: Iterable[RequestTask],
        progress_cb: Optional[Callable[[FetchResult], None]] = None,
    ) -> list[FetchResult]:
        sem = asyncio.Semaphore(self.settings.concurrency)
        results: list[FetchResult] = []

        async def _one(t: RequestTask) -> FetchResult:
            ini = t.fecha_inicio.strftime("%Y/%m/%d")
            fin = t.fecha_fin.strftime("%Y/%m/%d")

            async with sem:
                try:
                    payload, status, elapsed = await client.fetch_json(t.nodo, ini, fin, t.mercado)
                    ok = status == 200
                    fr = FetchResult(task=t, ok=ok, status=status, payload=payload, elapsed_s=elapsed)
                except Exception as e:
                    fr = FetchResult(task=t, ok=False, error=str(e))

            if progress_cb:
                progress_cb(fr)
            return fr

        coros = [_one(t) for t in tasks]
        for fut in asyncio.as_completed(coros):
            results.append(await fut)

        return results