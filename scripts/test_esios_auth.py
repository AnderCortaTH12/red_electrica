"""Verifica que la autenticación contra la API de ESIOS funciona.

Uso:
    python scripts\\test_esios_auth.py

Carga ESIOS_API_KEY desde .env y hace una única petición de prueba
(búsqueda de indicadores por texto) para confirmar que el token es válido
antes de construir nada más encima.
"""

import os
import sys

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.esios.ree.es"


def main() -> int:
    load_dotenv()

    token = os.environ.get("ESIOS_API_KEY")
    if not token:
        print("ERROR: ESIOS_API_KEY no está definida. ¿Existe .env y tiene el token?")
        return 1

    headers = {
        "Accept": "application/json; application/vnd.esios-api-v1+json",
        "Content-Type": "application/json",
        "x-api-key": token,
    }

    print("Probando GET /indicators?text=Precio ...")
    response = requests.get(
        f"{BASE_URL}/indicators",
        headers=headers,
        params={"text": "Precio"},
        timeout=30,
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 401:
        print("ERROR: 401 Unauthorized. El token es inválido o ha caducado.")
        return 1
    if response.status_code == 403:
        print("ERROR: 403 Forbidden. Revisa permisos del token.")
        return 1
    response.raise_for_status()

    payload = response.json()
    indicators = payload.get("indicators", [])
    print(f"OK. Autenticación correcta. {len(indicators)} indicadores encontrados con 'Precio'.")
    for ind in indicators[:10]:
        print(f"  - id={ind.get('id'):<6} {ind.get('name')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
