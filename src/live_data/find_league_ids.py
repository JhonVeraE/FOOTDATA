"""
Corré esto PRIMERO, una sola vez, para confirmar los league_id reales
(los de config.py son ejemplos que puse de memoria, no los verifiqué
contra la API real porque este entorno no tiene salida a internet).

Uso:
    python3 find_league_ids.py
"""
from api_client import get


def buscar(nombre):
    print(f"\nBuscando: {nombre}")
    resultados = get("leagues", {"search": nombre})
    for r in resultados:
        liga = r["league"]
        pais = r["country"]["name"]
        temporadas = [s["year"] for s in r["seasons"] if s.get("current")]
        print(f"  id={liga['id']:<6} {liga['name']:<35} pais={pais:<15} temporada_actual={temporadas}")


if __name__ == "__main__":
    buscar("Liga Profesional Argentina")
    buscar("Primera A")  # Colombia -- filtrar por pais=Colombia en el resultado
    buscar("UEFA Champions League")
    print("\nCopiá los id correctos a config.py -> LEAGUES antes de seguir.")
