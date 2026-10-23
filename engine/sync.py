import os
import re
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "primitiva.db")

# Proxies oficiales para entornos de producción (pueden sobreescribirse con variables de entorno)
DEFAULT_PROXIES = {
    "http": os.getenv("PROD_PROXY_HTTP", "http://nas918-home.synology.me:3128"),
    "https": os.getenv("PROD_PROXY_HTTPS", "http://nas918-home.synology.me:3128")
}

MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}

_cached_proximo_bote = {
    "fecha": "Jueves, 22 de octubre de 2026",
    "importe": 40000000.0,
    "importe_str": "40.000.000 €"
}


def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_cached_proximo_bote() -> Dict[str, Any]:
    global _cached_proximo_bote
    return _cached_proximo_bote


def clean_float(val: Any) -> float:
    if val is None:
        return 0.0
    val_str = str(val).strip().strip('"').strip("'")
    if not val_str or val_str.lower() in ("", "null", "none"):
        return 0.0
    val_str = val_str.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0


def clean_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    val_str = str(val).strip().strip('"').strip("'")
    if not val_str or val_str.lower() in ("", "null", "none"):
        return None
    try:
        return int(float(val_str))
    except (ValueError, TypeError):
        return None


# ==============================================================================
# 1. MOTOR PRIMARIO: API OFICIAL SELAE (loteriasyapuestas.es con curl_cffi)
# ==============================================================================

def sync_from_selae_api(db_path: str = DB_PATH, proxies: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """
    Sincroniza todos los sorteos que falten consultando la API oficial de SELAE
    utilizando curl_cffi con impersonación de Chrome y los proxies configurados.
    """
    try:
        from curl_cffi import requests
    except ImportError:
        print("[SELAE Sync] curl_cffi no está instalado. Usando fallback.")
        return None

    if proxies is None:
        proxies = DEFAULT_PROXIES

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Comprobar última fecha registrada en base de datos
    cursor.execute("SELECT MAX(fecha) FROM sorteos")
    last_fecha_row = cursor.fetchone()
    last_fecha_str = last_fecha_row[0] if last_fecha_row and last_fecha_row[0] else None

    hoy = datetime.now()
    if last_fecha_str:
        try:
            last_date = datetime.strptime(last_fecha_str[:10], "%Y-%m-%d")
            # Buscar desde 1 día antes del último sorteo para asegurar cobertura
            start_date = min(last_date - timedelta(days=1), hoy - timedelta(days=15))
        except Exception:
            start_date = hoy - timedelta(days=15)
    else:
        start_date = hoy - timedelta(days=30)

    str_inicio = start_date.strftime("%Y%m%d")
    str_fin = hoy.strftime("%Y%m%d")

    url = (
        f"https://www.loteriasyapuestas.es/servicios/buscadorSorteos?"
        f"game_id=LAPR&celebrados=true&fechaInicioInclusiva={str_inicio}&fechaFinInclusiva={str_fin}"
    )

    print(f"[SELAE Sync] Consultando sorteos oficiales ({str_inicio} a {str_fin})...")

    resp = None
    # Intento 1: A través del Proxy configurado (ideal para el VPS de producción)
    if proxies and (proxies.get("http") or proxies.get("https")):
        try:
            resp = requests.get(url, impersonate="chrome120", timeout=6, proxies=proxies)
            if resp.status_code != 200:
                resp = None
        except Exception as e:
            print(f"[SELAE Sync] Conexión por proxy no disponible ({e}).", flush=True)
            resp = None

    # Intento 2: Conexión directa (si el proxy no está disponible o estamos en local)
    if resp is None:
        try:
            resp = requests.get(url, impersonate="chrome120", timeout=6)
            if resp.status_code != 200:
                resp = None
        except Exception as e:
            print(f"[SELAE Sync] Conexión directa no disponible: {e}", flush=True)
            resp = None

    if resp is None:
        conn.close()
        return None

    try:
        data = resp.json()
    except Exception:
        conn.close()
        return None

    if not isinstance(data, list):
        conn.close()
        return None

    # Obtener IDs y fechas ya existentes en base de datos
    cursor.execute("SELECT id_sorteo, fecha FROM sorteos")
    rows = cursor.fetchall()
    ids_existentes = {r["id_sorteo"] for r in rows if r["id_sorteo"]}
    fechas_existentes = {r["fecha"][:10] for r in rows if r["fecha"]}

    # Ordenar cronológicamente (el más antiguo primero)
    data.sort(key=lambda x: x.get("fecha_sorteo", ""))

    count_new = 0
    count_prizes_updated = 0
    ultimo_sorteo_procesado = None

    for item in data:
        id_actual = str(item.get("id_sorteo", "")).strip()
        fecha_sorteo_str = item.get("fecha_sorteo", "").strip()
        if not id_actual or not fecha_sorteo_str:
            continue

        fecha_corta = fecha_sorteo_str[:10]

        # Caso: El sorteo ya existe
        if id_actual in ids_existentes or fecha_corta in fechas_existentes:
            # Comprobar si faltan los premios de este sorteo
            cursor.execute("SELECT COUNT(*) FROM premios WHERE id_sorteo = ?", (id_actual,))
            p_count = cursor.fetchone()[0]
            if p_count == 0:
                # Insertar premios pendientes
                for esc_key, tipo in [('escrutinio', 'PRIMITIVA'), ('escrutinio_joker', 'JOKER')]:
                    for esc in item.get(esc_key, []):
                        cursor.execute("""
                            INSERT INTO premios (id_sorteo, tipo_juego, categoria_nombre, ganadores, importe_premio)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            id_actual,
                            tipo,
                            str(esc.get("tipo", "")).strip(),
                            int(esc.get("ganadores", 0)),
                            clean_float(esc.get("premio", 0))
                        ))
                count_prizes_updated += 1
            continue

        # Procesar combinación ganadora
        comb_raw = item.get("combinacion", "")
        # Extraer todos los números enteros de la cadena
        all_digits = [int(x) for x in re.findall(r'\b\d+\b', comb_raw)]
        if len(all_digits) < 6:
            continue

        nums = sorted(all_digits[:6])
        comp = all_digits[6] if len(all_digits) > 6 else None
        reint = all_digits[7] if len(all_digits) > 7 else None

        combinacion_fmt = " - ".join(f"{n:02d}" for n in nums)

        # Jóker
        joker = None
        joker_raw = item.get("joker")
        if isinstance(joker_raw, dict):
            joker = str(joker_raw.get("combinacion", "")).strip()
        elif joker_raw:
            joker = str(joker_raw).strip()

        # Bote: SELAE devuelve el bote en céntimos (dividir por 100 si es mayor a 2 millones)
        raw_bote = clean_float(item.get("premio_bote", 0))
        bote = raw_bote / 100.0 if raw_bote > 2000000 else raw_bote

        cursor.execute("""
            INSERT INTO sorteos (
                id_sorteo, fecha, combinacion, n1, n2, n3, n4, n5, n6,
                complementario, joker, reintegro, bote
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            id_actual,
            fecha_sorteo_str,
            combinacion_fmt,
            nums[0], nums[1], nums[2], nums[3], nums[4], nums[5],
            comp, joker, reint, bote
        ))

        # Insertar escrutinio y premios
        for esc_key, tipo in [('escrutinio', 'PRIMITIVA'), ('escrutinio_joker', 'JOKER')]:
            for esc in item.get(esc_key, []):
                cursor.execute("""
                    INSERT INTO premios (id_sorteo, tipo_juego, categoria_nombre, ganadores, importe_premio)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    id_actual,
                    tipo,
                    str(esc.get("tipo", "")).strip(),
                    int(esc.get("ganadores", 0)),
                    clean_float(esc.get("premio", 0))
                ))

        ids_existentes.add(id_actual)
        fechas_existentes.add(fecha_corta)
        count_new += 1
        ultimo_sorteo_procesado = {
            "id_sorteo": id_actual,
            "fecha": fecha_sorteo_str,
            "combinacion": combinacion_fmt,
            "bote": bote
        }

    conn.commit()
    conn.close()

    if count_new > 0:
        msg = f"¡Sincronización oficial SELAE completada! Se han añadido {count_new} sorteos nuevos."
        return {
            "status": "new_draw_inserted",
            "message": msg,
            "count_new": count_new,
            "source": "Loterías y Apuestas del Estado (API Oficial)",
            "ultimo_sorteo": ultimo_sorteo_procesado
        }
    elif count_prizes_updated > 0:
        return {
            "status": "prizes_updated",
            "message": f"Premios oficiales actualizados para {count_prizes_updated} sorteos.",
            "source": "Loterías y Apuestas del Estado (API Oficial)"
        }
    else:
        return {
            "status": "already_up_to_date",
            "message": "La base de datos ya está completamente al día con la API oficial de SELAE.",
            "source": "Loterías y Apuestas del Estado (API Oficial)"
        }


# ==============================================================================
# 2. MOTOR SECUNDARIO: FALLBACK A COMBINACIONGANADORA.COM (Si SELAE no responde)
# ==============================================================================

def fetch_html_from_url(url: str = "https://www.combinacionganadora.com/primitiva/") -> Optional[str]:
    """Descarga el HTML de resultados utilizando curl con fallback a urllib."""
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

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return None


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

    bote = 0.0
    m_bote = re.search(r'Bote[:\s]*([\d\.,]+)\s*€', html, re.IGNORECASE)
    if m_bote:
        bote_str = m_bote.group(1).replace('.', '').replace(',', '.')
        try:
            bote = float(bote_str)
        except Exception:
            pass

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


def sync_from_combinacionganadora(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Fallback secundario que consulta el último sorteo publicado."""
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

    cursor.execute("SELECT id, id_sorteo, fecha FROM sorteos ORDER BY fecha DESC LIMIT 1")
    last_row = cursor.fetchone()
    last_db_fecha = last_row["fecha"] if last_row else None

    if last_db_fecha and sorteo["fecha"] <= last_db_fecha:
        cursor.execute("SELECT COUNT(*) FROM premios WHERE id_sorteo = ?", (sorteo["id_sorteo"],))
        pcount = cursor.fetchone()[0]
        if pcount == 0 and len(premios) > 0:
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
            "message": f"La base de datos ya está al día. Último sorteo registrado: {last_db_fecha[:10]}.",
            "sorteo": dict(last_row) if last_row else sorteo,
            "source": "Combinación Ganadora (Fallback)"
        }

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
        "premios_count": len(premios),
        "source": "Combinación Ganadora (Fallback)"
    }


# ==============================================================================
# 3. ORQUESTADOR PRINCIPAL: Intenta SELAE Oficial con Proxy -> Fallback automático
# ==============================================================================

def sync_latest_draw(db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Orquestador de sincronización:
    1. Intenta sincronizar todos los sorteos pendientes desde la API oficial de SELAE
       usando curl_cffi y los proxies de producción.
    2. Si SELAE no responde o falla la conexión, conmuta automáticamente al fallback.
    """
    selae_res = None
    try:
        selae_res = sync_from_selae_api(db_path=db_path)
    except Exception as e:
        print(f"[Sync Orchestrator] Excepción en sync oficial SELAE: {e}")
        selae_res = None

    if selae_res is not None:
        return selae_res

    print("[Sync Orchestrator] Conmutando a fallback de resultados...")
    return sync_from_combinacionganadora(db_path=db_path)
