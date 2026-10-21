import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.differences import (
    fetch_all_draws,
    compute_differences,
    calculate_positional_stats,
    generate_forecast,
    run_backtesting
)

def test_engine():
    print("Obteniendo sorteos...")
    draws = fetch_all_draws()
    print(f"Total sorteos cargados: {len(draws)}")

    print("\nCalculando diferencias consecutivas...")
    diff_records = compute_differences(draws)
    print(f"Total pares consecutivos calculados: {len(diff_records)}")

    # Primer par
    first_p = diff_records[0]
    print(f"Primer par: {first_p['prev_fecha']} -> {first_p['fecha']}")
    print(f"  Comb Anterior: {first_p['prev_combinacion']}")
    print(f"  Comb Actual:   {first_p['curr_combinacion']}")
    print(f"  Diferencias:   {first_p['diffs']}")

    print("\nEstadísticas por posición (Histórico Completo):")
    stats = calculate_positional_stats(diff_records)
    for p in stats["positions"]:
        print(f"  Pos {p['position']}: Media={p['mean']:+.2f} | Mediana={p['median']:+.2f} | Moda={p['mode']:+d} ({p['mode_pct']}%) | StdDev={p['std_dev']:.2f}")

    # Último sorteo registrado
    last_draw = draws[-1]
    last_nums = [last_draw["n1"], last_draw["n2"], last_draw["n3"], last_draw["n4"], last_draw["n5"], last_draw["n6"]]
    print(f"\nÚltimo sorteo ({last_draw['fecha']}): {last_draw['combinacion']}")

    print("\nGenerando Pronósticos para el próximo sorteo:")
    forecasts = generate_forecast(last_nums, stats, strategy="all", count=2)
    for f in forecasts:
        print(f"  [{f['name']}]: {f['combination_str']} (Diferencias: {f['applied_diffs']})")

    print("\nEjecutando Backtesting en los últimos 200 sorteos (ventana de 100 sorteos)...")
    bt = run_backtesting(draws, window_size=100, max_evals=200)
    print(f"  Total evaluados: {bt['total_evaluados']}")
    print(f"  Aciertos: {bt['aciertos']}")
    print(f"  Porcentajes: {bt['porcentajes']}")
    print("✅ Motor probado con éxito!")

if __name__ == "__main__":
    test_engine()
