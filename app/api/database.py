import os
import time
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from scripts.init_db import dump_seed, DB_PATH, SEED_PATH
from engine.differences import get_db_connection

router = APIRouter(prefix="/api/database", tags=["Base de Datos & Semilla"])


@router.get("/info", response_model=Dict[str, Any])
def get_database_info():
    """Devuelve el estado de la base de datos viva y del archivo de semilla."""
    db_exists = os.path.exists(DB_PATH)
    seed_exists = os.path.exists(SEED_PATH)

    total_sorteos = 0
    total_premios = 0
    ultimo_sorteo = None
    db_size_mb = 0.0

    if db_exists:
        db_size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2)
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*), MAX(fecha) FROM sorteos")
            s_row = c.fetchone()
            total_sorteos = s_row[0]
            ultimo_sorteo = s_row[1]
            c.execute("SELECT COUNT(*) FROM premios")
            total_premios = c.fetchone()[0]
            conn.close()
        except Exception:
            pass

    seed_size_mb = 0.0
    seed_modified = None
    if seed_exists:
        seed_size_mb = round(os.path.getsize(SEED_PATH) / (1024 * 1024), 2)
        seed_mtime = os.path.getmtime(SEED_PATH)
        seed_modified = datetime.fromtimestamp(seed_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "db": {
            "exists": db_exists,
            "path": DB_PATH,
            "size_mb": db_size_mb,
            "total_sorteos": total_sorteos,
            "total_premios": total_premios,
            "ultimo_sorteo": ultimo_sorteo
        },
        "seed": {
            "exists": seed_exists,
            "path": SEED_PATH,
            "size_mb": seed_size_mb,
            "last_modified": seed_modified
        }
    }


@router.post("/seed", response_model=Dict[str, Any])
@router.get("/seed/update", response_model=Dict[str, Any])
def update_seed_endpoint():
    """
    Genera y actualiza el archivo de semilla comprimido (seed.sql.gz)
    a partir de la base de datos viva actual.
    """
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="No existe la base de datos viva para generar la semilla.")

    t0 = time.time()
    success = dump_seed(DB_PATH, SEED_PATH)
    if not success:
        raise HTTPException(status_code=500, detail="Error al generar el volcado de semilla comprimido.")

    elapsed = round(time.time() - t0, 2)
    seed_size_mb = round(os.path.getsize(SEED_PATH) / (1024 * 1024), 2)

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), MAX(fecha) FROM sorteos")
    total_sorteos, ultimo_sorteo = c.fetchone()
    conn.close()

    return {
        "status": "success",
        "message": f"¡Semilla generada con éxito ({seed_size_mb} MB) con {total_sorteos} sorteos históricos!",
        "elapsed_seconds": elapsed,
        "seed_size_mb": seed_size_mb,
        "total_sorteos": total_sorteos,
        "ultimo_sorteo": ultimo_sorteo,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@router.get("/seed/download", include_in_schema=False)
def download_seed():
    """Descarga el archivo de semilla comprimido seed.sql.gz directamente en el navegador."""
    if not os.path.exists(SEED_PATH):
        raise HTTPException(status_code=404, detail="El archivo seed.sql.gz aún no ha sido generado.")
    return FileResponse(
        path=SEED_PATH,
        filename="seed.sql.gz",
        media_type="application/gzip"
    )


@router.get("/download", include_in_schema=False)
def download_database():
    """Descarga el archivo de base de datos viva SQLite directamente en el navegador."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="El archivo primitiva.db no existe.")
    return FileResponse(
        path=DB_PATH,
        filename="primitiva.db",
        media_type="application/x-sqlite3"
    )
