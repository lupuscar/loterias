#!/usr/bin/env bash
# ==============================================================================
# Sincronización Segura de Base de Datos: Producción -> Local
# ==============================================================================
# Este script descarga una copia de la base de datos viva desde el VPS de producción
# a tu entorno local, sin necesidad de usar Git ni provocar conflictos.
# ==============================================================================

set -euo pipefail

COLOR_RESET="\033[0m"
COLOR_BOLD="\033[1m"
COLOR_GREEN="\033[1;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_CYAN="\033[1;36m"
COLOR_RED="\033[1;31m"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

PROD_SSH_HOST="${PROD_SSH_HOST:-${1:-}}"
PROD_REMOTE_DIR="${PROD_REMOTE_DIR:-/root/loterias}"

if [ -z "$PROD_SSH_HOST" ]; then
    echo -e "${COLOR_YELLOW}Uso:${COLOR_RESET} $0 <usuario@servidor-vps> [ruta_remota_proyecto]"
    echo ""
    echo "Ejemplo:"
    echo "  $0 root@mi-vps.com"
    echo "  $0 root@192.168.1.100 /home/deploy/loterias"
    echo ""
    echo "También puedes configurar en tu .env local:"
    echo "  PROD_SSH_HOST=root@mi-vps.com"
    echo "  PROD_REMOTE_DIR=/root/loterias"
    exit 1
fi

LOCAL_DB="data/primitiva.db"
BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"

# 1. Backup local de seguridad si ya existía una BD
if [ -f "$LOCAL_DB" ]; then
    LOCAL_BACKUP="${BACKUP_DIR}/primitiva_local_before_pull_$(date +%Y%m%d_%H%M%S).db"
    echo -e "${COLOR_CYAN}ℹ [INFO]${COLOR_RESET} Creando backup de la base de datos local actual en: ${LOCAL_BACKUP}"
    cp "$LOCAL_DB" "$LOCAL_BACKUP"
fi

# 2. Descargar la base viva de producción
REMOTE_DB_PATH="${PROD_REMOTE_DIR}/data/primitiva.db"
echo -e "${COLOR_CYAN}ℹ [INFO]${COLOR_RESET} Descargando ${REMOTE_DB_PATH} desde ${PROD_SSH_HOST}..."

if scp -C "${PROD_SSH_HOST}:${REMOTE_DB_PATH}" "${LOCAL_DB}.tmp"; then
    mv "${LOCAL_DB}.tmp" "$LOCAL_DB"
    echo -e "${COLOR_GREEN}✔ [ÉXITO]${COLOR_RESET} Base de datos descargada y actualizada localmente con éxito."
    
    # 3. Comprobar registros
    if [ -f "./venv/bin/python3" ]; then
        ./venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('$LOCAL_DB')
s = conn.execute('SELECT COUNT(*), MAX(fecha) FROM sorteos').fetchone()
p = conn.execute('SELECT COUNT(*) FROM premios').fetchone()[0]
conn.close()
print(f'   - Total sorteos: {s[0]} (último: {s[1]})')
print(f'   - Total premios: {p}')
"
    fi
else
    rm -f "${LOCAL_DB}.tmp"
    echo -e "${COLOR_RED}✖ [ERROR]${COLOR_RESET} No se pudo descargar la base de datos desde producción."
    exit 1
fi
