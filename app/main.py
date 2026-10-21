import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.sorteos import router as sorteos_router
from app.api.estadisticas import router as estadisticas_router
from app.api.pronosticos import router as pronosticos_router
from engine.differences import get_db_connection

from contextlib import asynccontextmanager

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
    yield

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
