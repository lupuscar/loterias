import argparse
import csv
import gzip
import os
import sqlite3
import sys
import time

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "primitiva.db")
SEED_PATH = os.path.join(DB_DIR, "seed.sql.gz")
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


def dump_seed(db_path: str = DB_PATH, seed_path: str = SEED_PATH) -> bool:
    """
    Exporta la base de datos SQLite actual a un archivo SQL comprimido con gzip (semilla).
    Esta semilla se versiona en Git y sirve para recrear la base de datos en nuevos entornos.
    """
    if not os.path.exists(db_path):
        print(f"❌ Error: La base de datos origen no existe en {db_path}")
        return False

    os.makedirs(os.path.dirname(seed_path), exist_ok=True)
    t0 = time.time()
    print(f"📦 Generando semilla comprimida desde {db_path}...")

    conn = sqlite3.connect(db_path)
    # Temporal para asegurar atomicidad
    temp_seed = seed_path + ".tmp"
    with gzip.open(temp_seed, "wt", encoding="utf-8") as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    conn.close()

    if os.path.exists(seed_path):
        os.remove(seed_path)
    os.rename(temp_seed, seed_path)

    elapsed = time.time() - t0
    db_size = os.path.getsize(db_path) / (1024 * 1024)
    seed_size = os.path.getsize(seed_path) / (1024 * 1024)
    print(f"✅ Semilla generada con éxito en {seed_path} ({elapsed:.2f}s)")
    print(f"   - Tamaño original SQLite: {db_size:.2f} MB")
    print(f"   - Tamaño semilla comprimida: {seed_size:.2f} MB")
    return True


def restore_from_seed(seed_path: str = SEED_PATH, db_path: str = DB_PATH) -> bool:
    """
    Restaura la base de datos SQLite a partir del volcado SQL comprimido con gzip.
    Tarda menos de un segundo y no requiere peticiones de red.
    """
    if not os.path.exists(seed_path):
        print(f"⚠ Aviso: No se encontró la semilla en {seed_path}")
        return False

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    t0 = time.time()
    print(f"🚀 Restaurando base de datos desde semilla {seed_path}...")

    # Crear base temporal y mover para garantizar que no quede corrupta
    temp_db = db_path + ".tmp"
    if os.path.exists(temp_db):
        os.remove(temp_db)

    conn = sqlite3.connect(temp_db)
    with gzip.open(seed_path, "rt", encoding="utf-8") as f:
        sql_content = f.read()
    conn.executescript(sql_content)
    conn.commit()
    conn.close()

    if os.path.exists(db_path):
        os.remove(db_path)
    os.rename(temp_db, db_path)

    elapsed = time.time() - t0
    conn = sqlite3.connect(db_path)
    sorteos_count = conn.execute("SELECT COUNT(*) FROM sorteos").fetchone()[0]
    premios_count = conn.execute("SELECT COUNT(*) FROM premios").fetchone()[0]
    fechas = conn.execute("SELECT MIN(fecha), MAX(fecha) FROM sorteos").fetchone()
    conn.close()

    print(f"✅ Base de datos restaurada en {elapsed:.2f}s:")
    print(f"   - Ubicación: {db_path}")
    print(f"   - Total sorteos: {sorteos_count} (desde {fechas[0]} hasta {fechas[1]})")
    print(f"   - Total premios: {premios_count}")
    return True


def restore_from_csv(db_path: str = DB_PATH) -> bool:
    """
    Fallback legacy: inicializa la base de datos parseando los archivos CSV originales si existen.
    """
    if not os.path.exists(SORTEOS_CSV):
        return False

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sorteos_fecha ON sorteos(fecha ASC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_premios_sorteo ON premios(id_sorteo);")

    print(f"Cargando {SORTEOS_CSV}...")
    sorteos_raw = []
    with open(SORTEOS_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fecha_str = row.get("fecha", "").strip()
            if not fecha_str:
                continue

            nums = [
                clean_int(row.get("n1")), clean_int(row.get("n2")),
                clean_int(row.get("n3")), clean_int(row.get("n4")),
                clean_int(row.get("n5")), clean_int(row.get("n6"))
            ]

            if any(n is None for n in nums):
                comb_str = row.get("combinacion", "")
                parts = [int(p.strip()) for p in comb_str.replace("-", " ").split() if p.strip().isdigit()]
                if len(parts) >= 6:
                    nums = sorted(parts[:6])

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
                "n1": n1, "n2": n2, "n3": n3, "n4": n4, "n5": n5, "n6": n6,
                "complementario": clean_int(row.get("complementario")),
                "joker": str(row.get("joker", "")).strip(),
                "reintegro": clean_int(row.get("reintegro")),
                "bote": clean_float(row.get("bote")) * 100 if (0 < clean_float(row.get("bote")) < 2000000) else clean_float(row.get("bote"))
            })

    sorteos_raw.sort(key=lambda s: s["fecha"])
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
        cursor.executemany("""
            INSERT OR REPLACE INTO premios (id, id_sorteo, tipo_juego, categoria_nombre, ganadores, importe_premio)
            VALUES (:id, :id_sorteo, :tipo_juego, :categoria_nombre, :ganadores, :importe_premio)
        """, premios_raw)
        conn.commit()

    conn.close()
    return True


def init_database(force: bool = False) -> bool:
    """
    Inicializa la base de datos SQLite si no existe (o si se fuerza explícitamente).
    Prioridad:
    1. Si ya existe y no se fuerza: no hace nada (respeta la BD viva).
    2. Si existe semilla seed.sql.gz: restaura desde ella.
    3. Si existen CSVs: genera desde CSVs.
    """
    if os.path.exists(DB_PATH) and not force:
        print(f"ℹ Base de datos detectada en {DB_PATH}. No se requiere inicialización.")
        return True

    if force and os.path.exists(DB_PATH):
        print(f"⚠ Modo force activado: eliminando {DB_PATH} previa...")
        os.remove(DB_PATH)

    if os.path.exists(SEED_PATH):
        return restore_from_seed(SEED_PATH, DB_PATH)
    elif os.path.exists(SORTEOS_CSV):
        return restore_from_csv(DB_PATH)
    else:
        print(f"❌ Error: Ni la semilla {SEED_PATH} ni los archivos CSV fueron encontrados.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Gestión e inicialización de la base de datos de Primitiva Analytics")
    parser.add_argument("--dump-seed", action="store_true", help="Generar/Actualizar data/seed.sql.gz desde data/primitiva.db")
    parser.add_argument("--restore-seed", action="store_true", help="Recrear data/primitiva.db desde la semilla data/seed.sql.gz")
    parser.add_argument("--force", action="store_true", help="Forzar sobreescritura de la base de datos si ya existe")

    args = parser.parse_args()

    if args.dump_seed:
        success = dump_seed()
        sys.exit(0 if success else 1)
    elif args.restore_seed:
        success = restore_from_seed()
        sys.exit(0 if success else 1)
    else:
        success = init_database(force=args.force)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
