import csv
import os
import sqlite3
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "primitiva.db")
SORTEOS_CSV = os.path.join(os.path.dirname(__file__), "..", "sorteos_primitiva.csv")
PREMIOS_CSV = os.path.join(os.path.dirname(__file__), "..", "sorteos_premios.csv")


def clean_int(val):
    if val is None:
        return None
    val_str = str(val).strip().strip('"').strip("'")
    if not val_str or val_str.lower() in ("", "null", "none"):
        return None
    try:
        return int(float(val_str))
    except (ValueError, TypeError):
        return None


def clean_float(val):
    if val is None:
        return 0.0
    val_str = str(val).strip().strip('"').strip("'").replace(",", ".")
    if not val_str or val_str.lower() in ("", "null", "none"):
        return 0.0
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0


def init_database():
    os.makedirs(DB_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        print(f"Eliminando base de datos anterior: {DB_PATH}")
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tabla sorteos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sorteos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_sorteo TEXT UNIQUE,
            fecha TEXT NOT NULL,
            combinacion TEXT NOT NULL,
            n1 INTEGER NOT NULL,
            n2 INTEGER NOT NULL,
            n3 INTEGER NOT NULL,
            n4 INTEGER NOT NULL,
            n5 INTEGER NOT NULL,
            n6 INTEGER NOT NULL,
            complementario INTEGER,
            joker TEXT,
            reintegro INTEGER,
            bote REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabla premios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS premios (
            id INTEGER PRIMARY KEY,
            id_sorteo TEXT NOT NULL,
            tipo_juego TEXT,
            categoria_nombre TEXT,
            ganadores INTEGER DEFAULT 0,
            importe_premio REAL DEFAULT 0.0,
            FOREIGN KEY (id_sorteo) REFERENCES sorteos(id_sorteo)
        )
    """)

    # Índices para consultas y análisis
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sorteos_fecha ON sorteos(fecha ASC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_premios_sorteo ON premios(id_sorteo);")

    # 1. Cargar y ordenar sorteos cronológicamente
    if os.path.exists(SORTEOS_CSV):
        print(f"Cargando {SORTEOS_CSV}...")
        sorteos_raw = []
        with open(SORTEOS_CSV, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fecha_str = row.get("fecha", "").strip()
                if not fecha_str:
                    continue

                nums = [
                    clean_int(row.get("n1")),
                    clean_int(row.get("n2")),
                    clean_int(row.get("n3")),
                    clean_int(row.get("n4")),
                    clean_int(row.get("n5")),
                    clean_int(row.get("n6"))
                ]

                # Si alguno es nulo, intentar parsear combinacion
                if any(n is None for n in nums):
                    comb_str = row.get("combinacion", "")
                    parts = [int(p.strip()) for p in comb_str.replace("-", " ").split() if p.strip().isdigit()]
                    if len(parts) >= 6:
                        nums = sorted(parts[:6])

                # Asegurar orden estrictamente ascendente de n1..n6
                valid_nums = sorted([n for n in nums if n is not None])
                if len(valid_nums) < 6:
                    continue

                n1, n2, n3, n4, n5, n6 = valid_nums[:6]
                combinacion_formateada = f"{n1:02d} - {n2:02d} - {n3:02d} - {n4:02d} - {n5:02d} - {n6:02d}"

                id_val = row.get("id_sorteo") or row.get("\ufeffid_sorteo") or ""
                sorteos_raw.append({
                    "id_sorteo": str(id_val).strip(),
                    "fecha": fecha_str,
                    "combinacion": combinacion_formateada,
                    "n1": n1,
                    "n2": n2,
                    "n3": n3,
                    "n4": n4,
                    "n5": n5,
                    "n6": n6,
                    "complementario": clean_int(row.get("complementario")),
                    "joker": str(row.get("joker", "")).strip(),
                    "reintegro": clean_int(row.get("reintegro")),
                    "bote": clean_float(row.get("bote")) * 100 if (0 < clean_float(row.get("bote")) < 2000000) else clean_float(row.get("bote"))
                })

        # ORDENAR CRONOLÓGICAMENTE: el sorteo más antiguo primero
        sorteos_raw.sort(key=lambda s: s["fecha"])

        print(f"Insertando {len(sorteos_raw)} sorteos en orden cronológico...")
        insert_sql = """
            INSERT OR REPLACE INTO sorteos (
                id_sorteo, fecha, combinacion, n1, n2, n3, n4, n5, n6,
                complementario, joker, reintegro, bote
            ) VALUES (
                :id_sorteo, :fecha, :combinacion, :n1, :n2, :n3, :n4, :n5, :n6,
                :complementario, :joker, :reintegro, :bote
            )
        """
        cursor.executemany(insert_sql, sorteos_raw)
        conn.commit()

    # 2. Cargar premios
    if os.path.exists(PREMIOS_CSV):
        print(f"Cargando {PREMIOS_CSV}...")
        premios_raw = []
        with open(PREMIOS_CSV, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_id = clean_int(row.get("id")) or clean_int(row.get("\ufeffid"))
                id_sorteo = str(row.get("id_sorteo", "")).strip()
                if not id_sorteo:
                    continue
                premios_raw.append({
                    "id": p_id,
                    "id_sorteo": id_sorteo,
                    "tipo_juego": row.get("tipo_juego", "").strip(),
                    "categoria_nombre": row.get("categoria_nombre", "").strip(),
                    "ganadores": clean_int(row.get("ganadores")) or 0,
                    "importe_premio": clean_float(row.get("importe_premio"))
                })

        print(f"Insertando {len(premios_raw)} registros de premios...")
        cursor.executemany("""
            INSERT OR REPLACE INTO premios (id, id_sorteo, tipo_juego, categoria_nombre, ganadores, importe_premio)
            VALUES (:id, :id_sorteo, :tipo_juego, :categoria_nombre, :ganadores, :importe_premio)
        """, premios_raw)
        conn.commit()

    # Comprobar resultados
    cursor.execute("SELECT COUNT(*) FROM sorteos;")
    total_sorteos = cursor.fetchone()[0]
    cursor.execute("SELECT MIN(fecha), MAX(fecha) FROM sorteos;")
    min_fecha, max_fecha = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM premios;")
    total_premios = cursor.fetchone()[0]

    print("\n✅ Base de datos inicializada con éxito:")
    print(f" - Ubicación: {DB_PATH}")
    print(f" - Total sorteos: {total_sorteos} (desde {min_fecha} hasta {max_fecha})")
    print(f" - Total premios: {total_premios}")

    # Mostrar los últimos 3 sorteos insertados
    cursor.execute("SELECT id, fecha, combinacion FROM sorteos ORDER BY fecha DESC LIMIT 3;")
    print("\nÚltimos 3 sorteos registrados:")
    for row in cursor.fetchall():
        print(f"   ID {row[0]}: {row[1]} -> {row[2]}")

    conn.close()


if __name__ == "__main__":
    init_database()
