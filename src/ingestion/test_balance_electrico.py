"""Prueba manual del cliente REData contra balance-electrico.

Uso:
    python -m src.ingestion.test_balance_electrico
"""

import json
import logging

from src.ingestion.redata import get_widget_data

logging.basicConfig(level=logging.INFO)


def main() -> None:
    payload = get_widget_data(
        category="balance",
        widget="balance-electrico",
        start_date="2019-01-01T00:00",
        end_date="2019-01-31T23:59",
        time_trunc="day",
    )

    data_block = payload.get("data", {})
    groups = payload.get("included", [])

    print(f"data.type: {data_block.get('type')}")
    print(f"data.id: {data_block.get('id')}")
    print(f"Nº de grupos en 'included': {len(groups)}")

    # Cada elemento de 'included' es un grupo (Renovable, No-Renovable, ...)
    # que anida los indicadores reales en attributes.content.
    for group in groups:
        group_attrs = group.get("attributes", {})
        indicators = group_attrs.get("content", [])
        print(f"\nGrupo: {group.get('type')} ({len(indicators)} indicadores)")
        for indicator in indicators[:2]:
            attrs = indicator.get("attributes", {})
            values = attrs.get("values", [])
            print(
                f"  - {indicator.get('type')} "
                f"(id={indicator.get('id')}, groupId={indicator.get('groupId')}, "
                f"{len(values)} valores, ej: {values[0] if values else None})"
            )

    with open("data/sample_balance_electrico.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("\nGuardado en data/sample_balance_electrico.json")


if __name__ == "__main__":
    main()
