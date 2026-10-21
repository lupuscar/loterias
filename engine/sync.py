import os
import re
import sqlite3
import subprocess
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "primitiva.db")

MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}


def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_html_from_url(url: str = "https://www.combinacionganadora.com/primitiva/") -> Optional[str]:
    """Descarga el HTML de resultados utilizando curl con fallback a urllib."""
    # 1. Intento primario con curl (rápido, soporta HTTP/2 y compresión)
    try:
        cmd = [
            "curl", "-sL", "-m", "10",
            "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            url
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
        if res.returncode == 0 and len(res.stdout) > 5000:
            return res.stdout
    except Exception:
        pass

    # 2. Fallback con urllib
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return None


_cached_proximo_bote = {
    "fecha": "Jueves, 22 de octubre de 2026",
    "importe": 40000000.0,
    "importe_str": "40.000.000 €"
}


def get_cached_proximo_bote() -> Dict[str, Any]:
    global _cached_proximo_bote
    return _cached_proximo_bote


def parse_draw_and_prizes(html: str) -> Optional[Dict[str, Any]]:
    """Parsea el HTML para extraer el sorteo más reciente y el escrutinio de premios."""
    global _cached_proximo_bote
    m = re.search(
        r'Loter[íi]a Primitiva\s+[a-záéíóú]+\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4}):\s*([\d,]+)\.\s*Complementario:\s*(\d+)\.\s*Reintegro:\s*(\d+)\.\s*(?:Joker:\s*(\d+))?',
        html,
        re.IGNORECASE
    )
    if not m:
        return None

    dia, mes_nombre, anio, comb_str, comp, reint, joker = m.groups()
    mes_num = MESES.get(mes_nombre.lower(), 1)
    fecha_dt = datetime(int(anio), mes_num, int(dia), 21, 42, 0)
    fecha_formatted = fecha_dt.strftime("%Y-%m-%d %H:%M:%S")

    nums = sorted([int(x) for x in comb_str.split(',')])
    if len(nums) != 6:
        return None

    # Buscar bote del sorteo celebrado
    bote = 0.0
    m_bote = re.search(r'Bote[:\s]*([\d\.,]+)\s*€', html, re.IGNORECASE)
    if m_bote:
        bote_str = m_bote.group(1).replace('.', '').replace(',', '.')
        try:
            bote = float(bote_str)
        except Exception:
            pass

    # Buscar bote del próximo sorteo oficial
    m_jackpot = re.search(
        r'primitiva/["\']>La Primitiva</a></div>\s*<div[^>]*data-jackpot[^>]*><small>(.*?)</small><strong>([\d\.,]+)€?</strong>',
        html,
        re.IGNORECASE
    )
    if m_jackpot:
        fecha_prox, prox_importe_str = m_jackpot.groups()
        try:
            prox_val = float(prox_importe_str.replace('.', '').replace(',', '.'))
            _cached_proximo_bote = {
                "fecha": fecha_prox.strip(),
                "importe": prox_val,
                "importe_str": f"{prox_val:,.0f} €".replace(',', '.')
            }
        except Exception:
            pass

    id_sorteo = f"SORT-{fecha_dt.strftime('%Y%m%d')}"

    sorteo_data = {
        "id_sorteo": id_sorteo,
        "fecha": fecha_formatted,
        "combinacion": " - ".join(f"{n:02d}" for n in nums),
        "n1": nums[0], "n2": nums[1], "n3": nums[2],
        "n4": nums[3], "n5": nums[4], "n6": nums[5],
        "complementario": int(comp) if comp else None,
        "reintegro": int(reint) if reint else None,
        "joker": joker if joker else None,
        "bote": bote
    }

    # Extraer categorías de premios
    premios_data = []
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    for t in tables:
        if 'acertantes' in t.lower() and ('especial' in t.lower() or 'categoría' in t.lower() or 'premios' in t.lower()):
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.DOTALL | re.IGNORECASE)
            for r in rows:
                cols = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL | re.IGNORECASE)
                if len(cols) >= 3:
                    cat_name = re.sub(r'<[^>]+>', '', cols[0]).strip()
                    ganadores_str = re.sub(r'[^\d]', '', cols[1]).strip()
                    premio_clean = re.sub(r'[^\d,\.]', '', cols[2]).strip().replace('.', '').replace(',', '.')
                    if cat_name and any(k in cat_name.lower() for k in ['especial', 'categoría', 'reintegro', '1', '2', '3', '4', '5']):
                        try:
                            ganadores = int(ganadores_str) if ganadores_str else 0
                            importe = float(premio_clean) if premio_clean else 0.0
                            premios_data.append({
                                "id_sorteo": id_sorteo,
                                "tipo_juego": "PRIMITIVA",
                                "categoria_nombre": cat_name,
                                "ganadores": ganadores,
                                "importe_premio": importe
                            })
                        except Exception:
                            pass
            break

    return {
        "sorteo": sorteo_data,
        "premios": premios_data
    }


def sync_latest_draw(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Sincroniza el sorteo más reciente y sus premios con la base de datos SQLite.
    Devuelve un diccionario con el resultado de la operación.
    """
    html = fetch_html_from_url()
    if not html:
        return {
            "status": "error",
            "message": "No se pudo conectar a la fuente de resultados de La Primitiva."
        }

    parsed = parse_draw_and_prizes(html)
    if not parsed:
        return {
            "status": "error",
            "message": "No se pudo extraer la información del sorteo del contenido descargado."
        }

    sorteo = parsed["sorteo"]
    premios = parsed["premios"]

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Comprobar el sorteo más reciente en base de datos
    cursor.execute("SELECT id, id_sorteo, fecha FROM sorteos ORDER BY fecha DESC LIMIT 1")
    last_row = cursor.fetchone()
    last_db_fecha = last_row["fecha"] if last_row else None
    last_db_id_sorteo = last_row["id_sorteo"] if last_row else None

    # Caso 1: Sorteo ya registrado
    if last_db_fecha and sorteo["fecha"] <= last_db_fecha:
        # Comprobar si tiene premios registrados
        cursor.execute("SELECT COUNT(*) FROM premios WHERE id_sorteo = ?", (sorteo["id_sorteo"],))
        pcount = cursor.fetchone()[0]

        if pcount == 0 and len(premios) > 0:
            # Sorteo existía pero faltaban los premios (escrutinio publicado a posteriori)
            for p in premios:
                cursor.execute("""
                    INSERT INTO premios (id_sorteo, tipo_juego, categoria_nombre, ganadores, importe_premio)
                    VALUES (?, ?, ?, ?, ?)
                """, (p["id_sorteo"], p["tipo_juego"], p["categoria_nombre"], p["ganadores"], p["importe_premio"]))
            conn.commit()
            conn.close()
            return {
                "status": "prizes_updated",
                "message": f"Premios actualizados con éxito para el sorteo del {sorteo['fecha'][:10]}.",
                "sorteo": sorteo,
                "premios_agregados": len(premios)
            }

        conn.close()
        return {
            "status": "already_up_to_date",
            "message": f"La base de datos ya está al día. El último sorteo registrado es del {last_db_fecha[:10]}.",
            "sorteo": dict(last_row) if last_row else sorteo,
            "nuevo_sorteo_disponible": False
        }

    # Caso 2: Nuevo sorteo
    cursor.execute("""
        INSERT INTO sorteos (
            id_sorteo, fecha, combinacion, n1, n2, n3, n4, n5, n6,
            complementario, joker, reintegro, bote
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sorteo["id_sorteo"],
        sorteo["fecha"],
        sorteo["combinacion"],
        sorteo["n1"], sorteo["n2"], sorteo["n3"],
        sorteo["n4"], sorteo["n5"], sorteo["n6"],
        sorteo["complementario"],
        sorteo["joker"],
        sorteo["reintegro"],
        sorteo["bote"]
    ))
    new_draw_id = cursor.lastrowid

    # Insertar premios correspondientes
    for p in premios:
        cursor.execute("""
            INSERT INTO premios (id_sorteo, tipo_juego, categoria_nombre, ganadores, importe_premio)
            VALUES (?, ?, ?, ?, ?)
        """, (sorteo["id_sorteo"], p["tipo_juego"], p["categoria_nombre"], p["ganadores"], p["importe_premio"]))

    conn.commit()
    conn.close()

    sorteo["id"] = new_draw_id
    return {
        "status": "new_draw_inserted",
        "message": f"¡Nuevo sorteo registrado con éxito! Fecha: {sorteo['fecha'][:10]} - Combinación: {sorteo['combinacion']}",
        "sorteo": sorteo,
        "premios_count": len(premios)
    }
