import asyncio
from datetime import date

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient
from pml.services.downloader import PmlDownloader
from pml.transforms.normalize import results_to_dataframes
from pml.exports.excel import ExcelExporter


async def main():
    settings = Settings(bloque_dias=7, concurrency=5)

    nodos = {
        "01VMA-400": "EVM-II","01ACO-230": "Acolman"
    }

    fecha_inicio = date(2025, 1, 1)
    fecha_fin = date(2025, 12, 31)

    downloader = PmlDownloader(settings)
    tasks = downloader.build_tasks(nodos, fecha_inicio, fecha_fin)

    ok = 0
    fail = 0

    def progress(fr):
        nonlocal ok, fail
        if fr.ok:
            ok += 1
        else:
            fail += 1

    async with CenacePmlClient(settings) as client:
        results = await downloader.run(client, tasks, progress_cb=progress)

    df_raw, df_err = results_to_dataframes(results)


    meta = {
        "fecha_inicio": str(fecha_inicio),
        "fecha_fin": str(fecha_fin),
        "bloque_dias": settings.bloque_dias,
        "concurrency": settings.concurrency,
        "nodos": ",".join(nodos.keys()),
        "ok_requests": ok,
        "fail_requests": fail,
        "raw_rows": int(len(df_raw)),
    }

    out = "PML_MDA.xlsx"
    ExcelExporter().export(df_raw, df_err, meta, out)
    print("Excel generado:", out)
    print("RAW rows:", len(df_raw))
    print("ERROR rows:", len(df_err))


if __name__ == "__main__":
    asyncio.run(main())