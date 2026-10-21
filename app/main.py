import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.sorteos import router as sorteos_router
from app.api.estadisticas import router as estadisticas_router
from app.api.pronosticos import router as pronosticos_router
from engine.differences import get_db_connection

import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from engine.sync import sync_latest_draw


async def background_auto_sync_loop():
    """
    Tarea periódica en segundo plano que comprueba y actualiza automáticamente
    los sorteos y premios en fechas y horas clave (Lunes, Jueves y Sábados noche).
    """
    # Esperar 5 segundos tras el arranque inicial antes de la primera comprobación
    await asyncio.sleep(5)
    while True:
        try:
            now = datetime.now()
            # Días de sorteo: 0=Lunes, 3=Jueves, 5=Sábado
            is_draw_day = now.weekday() in (0, 3, 5)
            # Horario crítico de publicación: 21:40 a 23:59
            is_draw_time = 21 <= now.hour <= 23

            # Durante el horario de sorteos comprobar cada 5 minutos; el resto del tiempo cada 30 minutos
            interval = 300 if (is_draw_day and is_draw_time) else 1800

            # Ejecutar sincronización en hilo no bloqueante para no interferir con peticiones HTTP
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, sync_latest_draw)
            if res.get("status") in ("new_draw_inserted", "prizes_updated"):
                print(f"[AutoSync] {res.get('message')}")
        except Exception as e:
            print(f"[AutoSync Error] {e}")
            interval = 600

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Comprobar si la base de datos existe; si no, inicializarla automáticamente
    db_file = os.path.join(os.path.dirname(__file__), "..", "data", "primitiva.db")
    if not os.path.exists(db_file):
        print("Base de datos no encontrada. Inicializando desde CSVs...")
        try:
            from scripts.init_db import init_database
            init_database()
        except Exception as e:
            print(f"Error inicializando base de datos: {e}")

    # Iniciar worker en segundo plano
    sync_task = asyncio.create_task(background_auto_sync_loop())
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Primitiva Analytics & Pronósticos API",
    description="API para consulta de sorteos, análisis diferencial posicional y pronósticos de la Lotería Primitiva.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware (permitir peticiones locales y desde proxy reverso)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar Routers
app.include_router(sorteos_router)
app.include_router(estadisticas_router)
app.include_router(pronosticos_router)


@app.get("/api/health", tags=["Health"])
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), MAX(fecha) FROM sorteos")
        total_sorteos, ultimo_sorteo = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM premios")
        total_premios = cursor.fetchone()[0]
        conn.close()
        return {
            "status": "healthy",
            "total_sorteos": total_sorteos,
            "ultimo_sorteo": ultimo_sorteo,
            "total_premios": total_premios
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# Servir archivos estáticos del frontend
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Primitiva Analytics API en funcionamiento. Abre /docs para ver la documentación OpenAPI."}
