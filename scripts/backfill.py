"""Backfill inicial: procesa todos los periodos pendientes desde
2026-01 hasta el mes anterior al actual.

Es una fina envoltura sobre `ingest_month.main()` sin `--periodo` (que
ya calcula y procesa todos los pendientes) -- pensado como punto de
entrada explícito para la ejecución única inicial del proyecto, sin
duplicar la lógica de idempotencia/pendientes que ya vive en
`ingest_month.py`. Reprocesar (p.ej. tras una revisión de Enagás) se
sigue haciendo con `ingest_month.py --periodo YYYY-MM --force`.

Uso:
    python -m scripts.backfill
"""

from __future__ import annotations

import sys

from scripts.ingest_month import main as ingest_main


def main(argv: list[str] | None = None) -> int:
    return ingest_main(argv or [])


if __name__ == "__main__":
    sys.exit(main())
