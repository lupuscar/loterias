import csv
from collections import Counter

def check_duplicates():
    with open("sorteos_primitiva.csv", "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    
    print(f"Total filas leídas: {len(reader)}")
    id_counts = Counter(r["id_sorteo"] for r in reader)
    dups = {k: v for k, v in id_counts.items() if v > 1}
    print(f"IDs duplicados ({len(dups)}):")
    for k, v in list(dups.items())[:10]:
        print(f"  id_sorteo {k}: {v} veces")
        # Mostrar filas con ese id
        matching = [r for r in reader if r["id_sorteo"] == k]
        for m in matching:
            print(f"    fecha={m['fecha']} comb={m['combinacion']}")

    # También chequear duplicados por fecha
    fechas_counts = Counter(r["fecha"] for r in reader)
    dup_fechas = {k: v for k, v in fechas_counts.items() if v > 1}
    print(f"\nFechas duplicadas ({len(dup_fechas)}):")
    for k, v in list(dup_fechas.items())[:5]:
        print(f"  fecha {k}: {v} veces")

if __name__ == "__main__":
    check_duplicates()
