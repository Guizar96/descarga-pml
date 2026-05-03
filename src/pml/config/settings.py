from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Settings:
    base_url: str = "https://ws01.cenace.gob.mx:8082/SWPML/SIM/SIN/MDA"
    bloque_dias: int = 7
    concurrency: int = 10
    timeout_total_s: int = 60
    timeout_connect_s: int = 10
    retries: int = 3
    backoff_min_s: float = 0.5
    backoff_max_s: float = 6.0
