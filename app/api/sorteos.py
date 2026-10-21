import sqlite3
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from app.models import SorteoCreate, SorteoResponse, PremioResponse
from engine.differences import get_db_connection, insert_new_draw, get_draw_by_id, get_premios_by_sorteo

router = APIRouter(prefix="/api/sorteos", tags=["Sorteos"])


@router.get("", response_model=Dict[str, Any])
def list_sorteos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
    search_date: Optional[str] = Query(None, description="Filtro por año o fecha YYYY-MM"),
    has_number: Optional[int] = Query(None, ge=1, le=49, description="Filtrar sorteos que contengan este número")
):
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if search_date:
        where_clauses.append("fecha LIKE ?")
        params.append(f"%{search_date.strip()}%")

    if has_number:
        where_clauses.append("(n1 = ? OR n2 = ? OR n3 = ? OR n4 = ? OR n5 = ? OR n6 = ?)")
        params.extend([has_number] * 6)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Conteo total
    cursor.execute(f"SELECT COUNT(*) FROM sorteos {where_sql}", params)
    total = cursor.fetchone()[0]

    offset = (page - 1) * page_size
    query = f"""
        SELECT id, id_sorteo, fecha, combinacion, n1, n2, n3, n4, n5, n6,
               complementario, joker, reintegro, bote
        FROM sorteos
        {where_sql}
        ORDER BY fecha DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/ultimo", response_model=Dict[str, Any])
def get_ultimo_sorteo():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, id_sorteo, fecha, combinacion, n1, n2, n3, n4, n5, n6,
               complementario, joker, reintegro, bote
        FROM sorteos
        ORDER BY fecha DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No hay sorteos registrados.")
    return dict(row)


from engine.sync import sync_latest_draw


@router.post("/sync", response_model=Dict[str, Any])
@router.get("/sync", response_model=Dict[str, Any])
def sync_sorteos_endpoint():
    """
    Sincroniza automáticamente los resultados y premios oficiales del sorteo
    más reciente de La Primitiva desde la fuente pública de resultados.
    """
    try:
        result = sync_latest_draw()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante la sincronización: {str(e)}")


@router.get("/{sorteo_id}", response_model=Dict[str, Any])
def get_sorteo(sorteo_id: int):
    sorteo = get_draw_by_id(sorteo_id)
    if not sorteo:
        raise HTTPException(status_code=404, detail="Sorteo no encontrado.")

    premios = get_premios_by_sorteo(sorteo["id_sorteo"])
    return {
        "sorteo": sorteo,
        "premios": premios
    }


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_sorteo(sorteo_in: SorteoCreate):
    data = sorteo_in.model_dump()
    try:
        new_id = insert_new_draw(data)
        created = get_draw_by_id(new_id)
        return {
            "message": "Sorteo registrado con éxito",
            "sorteo": created
        }
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"Error de integridad en base de datos: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado al guardar sorteo: {str(e)}")
