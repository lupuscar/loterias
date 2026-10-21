from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Query
from engine.differences import (
    fetch_all_draws,
    compute_differences,
    calculate_positional_stats
)

router = APIRouter(prefix="/api/estadisticas", tags=["Estadísticas"])


@router.get("/diferencias", response_model=Dict[str, Any])
def get_diferencias_stats(
    window: int = Query(0, ge=0, description="Ventana de últimos N sorteos (0 = todos)")
):
    """
    Devuelve las estadísticas completas de diferencias posicionales (medias, modas,
    desviaciones típicas, distribuciones para gráficos e histogramas).
    """
    limit = window if window > 0 else None
    draws = fetch_all_draws(limit=limit)
    diff_records = compute_differences(draws)
    stats = calculate_positional_stats(diff_records)

    # Limpiar counter no serializable antes de responder
    for p in stats.get("positions", []):
        if "raw_distribution" in p:
            del p["raw_distribution"]

    return {
        "window": window,
        "total_draws": len(draws),
        "total_diff_pairs": stats["total_pairs"],
        "positions": stats["positions"]
    }


@router.get("/recientes-diferencias", response_model=List[Dict[str, Any]])
def get_recientes_diferencias(
    limit: int = Query(20, ge=5, le=100)
):
    """
    Devuelve los últimos N pares de sorteos consecutivos con su vector de diferencias calculado.
    """
    # Necesitamos limit + 1 sorteos para obtener 'limit' pares
    draws = fetch_all_draws(limit=limit + 1)
    diff_records = compute_differences(draws)
    # Devolver los más recientes primero
    return diff_records[::-1][:limit]
