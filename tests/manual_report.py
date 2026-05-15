import asyncio
from datetime import date

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient
from pml.services.downloader import PmlDownloader
from pml.transforms.normalize import results_to_dataframes
from pml.analysis.report import ReportBuilder


async def main():
    settings = Settings(bloque_dias=7, concurrency=5)
    nodos = {"01VMA-400": "EVM-II"}
    fecha_inicio = date(2024, 4, 1)
    fecha_fin = date(2024, 4, 15)

    downloader = PmlDownloader(settings)
    tasks = downloader.build_tasks(nodos, fecha_inicio, fecha_fin)

    async with CenacePmlClient(settings) as client:
        results = await downloader.run(client, tasks)

    df_raw, df_err = results_to_dataframes(results)
    print("RAW:", len(df_raw), "ERRORS:", len(df_err))

    rb = ReportBuilder()
    k = rb.kpis(df_raw)
    print("KPIs:", k)

    top_high, top_low = rb.top_hours(df_raw, n=5)
    print("\nTop 5 altas:")
    print(top_high)
    print("\nTop 5 bajas:")
    print(top_low)


if __name__ == "__main__":
    asyncio.run(main())