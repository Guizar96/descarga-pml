import asyncio

from pml.config.settings import Settings
from pml.clients.cenace_client import CenacePmlClient


async def main():
    settings = Settings()
    nodo = "01VMA-400"
    ini = "2024/01/01"
    fin = "2024/01/07"

    async with CenacePmlClient(settings) as client:
        payload, status, elapsed = await client.fetch_json(nodo, ini, fin)

    print("STATUS:", status)
    print("ELAPSED_s:", round(elapsed, 3))
    print("TOP_KEYS:", list(payload.keys()) if isinstance(payload, dict) else type(payload))


if __name__ == "__main__":
    asyncio.run(main())