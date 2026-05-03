import asyncio
from datetime import date

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient
from pml.services.downloader import PmlDownloader


async def main():
    settings = Settings(bloque_dias=7, concurrency=5)
    nodos = {
        "01VMA-400": "EVM-II",
        # agrega otro si quieres probar multi-nodo:
        "01ACO-230": "Acolman"
    }

    fecha_inicio = date(2024, 1, 1)
    fecha_fin = date(2024, 12, 31)

    downloader = PmlDownloader(settings)
    tasks = downloader.build_tasks(nodos, fecha_inicio, fecha_fin)
    total = len(tasks)

    ok = 0
    fail = 0
    done = 0

    def progress(fr):
        nonlocal ok, fail, done
        done += 1
        if fr.ok:
            ok += 1
        else:
            fail += 1
        print(f"[{done}/{total}] OK={ok} FAIL={fail} | {fr.task.nodo} {fr.task.rango_str} status={fr.status} err={fr.error}")

    async with CenacePmlClient(settings) as client:
        results = await downloader.run(client, tasks, progress_cb=progress)

    print("\nResumen:")
    print("Tasks:", total)
    print("OK:", sum(1 for r in results if r.ok))
    print("FAIL:", sum(1 for r in results if not r.ok))


if __name__ == "__main__":
    asyncio.run(main())