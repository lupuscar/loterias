from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Query, HTTPException
from engine.differences import (
    fetch_all_draws,
    compute_differences,
    calculate_positional_stats,
    generate_forecast,
    run_backtesting
)

router = APIRouter(prefix="/api/pronosticos", tags=["Pronósticos"])


@router.get("", response_model=Dict[str, Any])
def get_pronosticos(
    strategy: str = Query("all", description="Estrategia: all, reversion, mean, mode, magnitude, probabilistic"),
    window: int = Query(0, ge=0, description="Ventana de sorteos a considerar (0 = todos)"),
    count: int = Query(5, ge=1, le=20, description="Número de combinaciones a generar")
):
    """
    Genera combinaciones pronosticadas para el próximo sorteo de la Primitiva
    utilizando el modelo de diferencias y la estrategia seleccionada.
    """
    limit = window if window > 0 else None
    draws = fetch_all_draws(limit=limit)
    if len(draws) < 2:
        raise HTTPException(status_code=400, detail="No hay suficientes sorteos históricos para calcular diferencias.")

    diff_records = compute_differences(draws)
    stats = calculate_positional_stats(diff_records, draws=draws)

    last_draw = draws[-1]
    last_nums = [last_draw["n1"], last_draw["n2"], last_draw["n3"],
                 last_draw["n4"], last_draw["n5"], last_draw["n6"]]

    forecasts = generate_forecast(
        last_nums=last_nums,
        stats=stats,
        strategy=strategy,
        count=count
    )

    return {
        "ultimo_sorteo": {
            "id": last_draw["id"],
            "fecha": last_draw["fecha"],
            "combinacion": last_draw["combinacion"],
            "nums": last_nums,
            "complementario": last_draw["complementario"],
            "reintegro": last_draw["reintegro"]
        },
        "parametros": {
            "estrategia": strategy,
            "ventana": window if window > 0 else "Histórico completo",
            "sorteos_analizados": len(draws)
        },
        "pronosticos": forecasts
    }


@router.get("/backtesting", response_model=Dict[str, Any])
def get_backtesting(
    strategy: str = Query("reversion", description="Estrategia a evaluar"),
    window_size: int = Query(100, ge=10, le=500, description="Tamaño de ventana de aprendizaje"),
    max_evals: int = Query(250, ge=10, le=4500, description="Sorteos retrospectivos a evaluar"),
    bets_per_draw: int = Query(1, ge=1, le=20, description="Número de pronósticos/apuestas generadas por sorteo")
):
    """
    Evalúa la efectividad histórica del modelo de pronósticos simulando predicciones
    en sorteos pasados y comprobando el número de aciertos reales (3, 4, 5, 6 aciertos).
    """
    draws = fetch_all_draws()
    if len(draws) < window_size + 20:
        raise HTTPException(status_code=400, detail="Base de datos insuficiente para el tamaño de ventana.")

    result = run_backtesting(
        draws=draws,
        strategy=strategy,
        window_size=window_size,
        max_evals=max_evals,
        bets_per_draw=bets_per_draw
    )
    return result
