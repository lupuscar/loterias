#!/usr/bin/env bash
# ==============================================================================
# Script de Despliegue en Producción - Primitiva Analytics
# ==============================================================================
# Este script está optimizado EXCLUSIVAMENTE para entornos de PRODUCCIÓN.
# Realiza comprobaciones previas, copia de seguridad de la base de datos,
# actualización de código (opcional/git), construcción de la imagen Docker,
# reinicio de contenedor con Traefik y verificación de salud de la API.
# ==============================================================================

set -euo pipefail

# Colores para salida de terminal
COLOR_RESET="\033[0m"
COLOR_BOLD="\033[1m"
COLOR_GREEN="\033[1;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_RED="\033[1;31m"
COLOR_CYAN="\033[1;36m"
COLOR_GRAY="\033[0;90m"

log_info() {
    echo -e "${COLOR_CYAN}ℹ [INFO]${COLOR_RESET} $1"
}

log_success() {
    echo -e "${COLOR_GREEN}✔ [ÉXITO]${COLOR_RESET} $1"
}

log_warning() {
    echo -e "${COLOR_YELLOW}⚠ [AVISO]${COLOR_RESET} $1"
}

log_error() {
    echo -e "${COLOR_RED}✖ [ERROR]${COLOR_RESET} $1" >&2
}

# 1. Asegurar ruta base del proyecto
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${COLOR_BOLD}${COLOR_CYAN}"
echo "=========================================================="
echo "   🚀 DESPLIEGUE EN PRODUCCIÓN - PRIMITIVA ANALYTICS"
echo "=========================================================="
echo -e "${COLOR_RESET}"
echo -e "Directorio de trabajo: ${COLOR_GRAY}${PROJECT_DIR}${COLOR_RESET}"
echo -e "Fecha y hora:        ${COLOR_GRAY}$(date '+%Y-%m-%d %H:%M:%S')${COLOR_RESET}"
echo ""

# 2. Comprobar requisitos previos del sistema
log_info "Verificando dependencias del sistema..."

if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker no está instalado o no se encuentra en el PATH."
    exit 1
fi

# Detectar sintaxis de docker compose (v2) o docker-compose (v1)
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    log_error "Ni 'docker compose' ni 'docker-compose' están disponibles."
    exit 1
fi

# Comprobar acceso al daemon de Docker
if ! docker info >/dev/null 2>&1; then
    log_error "No hay conexión con el daemon de Docker. ¿Tiene permisos suficientes (sudo / grupo docker)?"
    exit 1
fi

log_success "Docker y Docker Compose detectados correctamente."

# 3. Comprobar archivo de entorno .env
if [ ! -f .env ]; then
    log_error "El archivo .env no existe en ${PROJECT_DIR}."
    if [ -f .env.example ]; then
        log_info "Existe una plantilla .env.example. Por favor, crea tu archivo .env antes de desplegar:"
        echo -e "   cp .env.example .env && nano .env"
    fi
    exit 1
fi

# Cargar variables del .env
set -a
# shellcheck disable=SC1091
source .env
set +a

if [ -z "${DOMAIN:-}" ]; then
    log_error "La variable DOMAIN no está configurada en .env."
    exit 1
fi

TRAEFIK_NETWORK="${TRAEFIK_NETWORK:-proxy}"
log_info "Configuración de producción cargada:"
echo -e "   - Dominio:        ${COLOR_BOLD}${DOMAIN}${COLOR_RESET}"
echo -e "   - Red de Traefik: ${COLOR_BOLD}${TRAEFIK_NETWORK}${COLOR_RESET}"

# 4. Comprobar que la red externa de Traefik exista en Docker
if ! docker network inspect "$TRAEFIK_NETWORK" >/dev/null 2>&1; then
    log_warning "La red externa de Traefik '${TRAEFIK_NETWORK}' no existe todavía en Docker."
    read -r -p "¿Deseas crear la red '${TRAEFIK_NETWORK}' ahora? [S/n]: " CREATE_NET || CREATE_NET="s"
    if [[ "$CREATE_NET" =~ ^[sSyY]?$ ]]; then
        docker network create "$TRAEFIK_NETWORK"
        log_success "Red Docker '${TRAEFIK_NETWORK}' creada correctamente."
    else
        log_error "Despliegue cancelado: la red externa '${TRAEFIK_NETWORK}' es obligatoria para Traefik."
        exit 1
    fi
else
    log_success "Red de Traefik '${TRAEFIK_NETWORK}' verificada."
fi

# 5. Opcional: Actualizar código desde Git si estamos en un repositorio
if [ -d .git ]; then
    log_info "Repositorio Git detectado."
    # Comprobar si hay cambios locales no guardados
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        log_warning "Existen cambios locales no commiteados en el repositorio."
        read -r -p "¿Continuar con el despliegue sin actualizar desde remoto? [S/n]: " CONT_GIT || CONT_GIT="s"
        if [[ ! "$CONT_GIT" =~ ^[sSyY]?$ ]]; then
            log_error "Despliegue detenido para resolver cambios locales."
            exit 1
        fi
    else
        CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
        REMOTE_EXISTS="$(git remote -v || true)"
        if [ -n "$REMOTE_EXISTS" ]; then
            log_info "Descargando últimas actualizaciones de Git (${CURRENT_BRANCH})..."
            git fetch --prune
            git pull origin "$CURRENT_BRANCH"
            log_success "Código actualizado al último commit de '${CURRENT_BRANCH}'."
        fi
    fi
fi

# 6. Copia de seguridad de la base de datos de producción
DB_FILE="./data/primitiva.db"
BACKUP_DIR="./data/backups"

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_FILE" ]; then
    BACKUP_FILE="${BACKUP_DIR}/primitiva_backup_$(date +%Y%m%d_%H%M%S).db"
    log_info "Creando copia de seguridad de la base de datos..."
    cp "$DB_FILE" "$BACKUP_FILE"
    log_success "Backup guardado en: ${COLOR_GRAY}${BACKUP_FILE}${COLOR_RESET}"

    # Mantener únicamente los últimos 10 backups para no saturar disco
    OLD_BACKUPS_COUNT=$(find "$BACKUP_DIR" -name "primitiva_backup_*.db" | wc -l)
    if [ "$OLD_BACKUPS_COUNT" -gt 10 ]; then
        find "$BACKUP_DIR" -name "primitiva_backup_*.db" -type f -printf '%T+ %p\n' \
            | sort | head -n -10 | awk '{print $2}' | xargs -r rm -f
        log_info "Limpieza de backups antiguos completada (conservando los 10 más recientes)."
    fi
else
    log_warning "No se encontró base de datos previa en ${DB_FILE}. Se inicializará automáticamente al arrancar."
fi

# 7. Construir imagen Docker de Producción
log_info "Construyendo imagen Docker de producción..."
$DOCKER_COMPOSE build --pull

# 8. Reiniciar contenedor en segundo plano
log_info "Iniciando/Actualizando servicios en producción..."
$DOCKER_COMPOSE up -d --remove-orphans

# 9. Verificación de salud (Health Check)
log_info "Esperando a que el servicio esté listo y saludable..."

CONTAINER_NAME="primitiva_analytics"
MAX_ATTEMPTS=15
ATTEMPT=1
HEALTHY=0

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    echo -ne "   Comprobando estado (intento ${ATTEMPT}/${MAX_ATTEMPTS})...\r"
    
    # Comprobar que el contenedor esté corriendo
    CONTAINER_RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo "false")
    
    if [ "$CONTAINER_RUNNING" = "true" ]; then
        # Consultar endpoint /api/health usando Python interno del contenedor
        HEALTH_STATUS=$($DOCKER_COMPOSE exec -T primitiva-app python3 -c '
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen("http://localhost:8000/api/health", timeout=3)
    data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") == "healthy":
        print(f"OK|{data.get(\"total_sorteos\")}|{data.get(\"ultimo_sorteo\")}")
        sys.exit(0)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
' 2>/dev/null || echo "FAIL")

        if [[ "$HEALTH_STATUS" =~ ^OK\| ]]; then
            TOTAL_SORTEOS=$(echo "$HEALTH_STATUS" | cut -d'|' -f2)
            ULTIMO_SORTEO=$(echo "$HEALTH_STATUS" | cut -d'|' -f3)
            HEALTHY=1
            break
        fi
    fi

    sleep 2
    ATTEMPT=$((ATTEMPT + 1))
done

echo ""

if [ $HEALTHY -eq 1 ]; then
    log_success "Servicio verificado y funcionando correctamente."
    echo -e "   - Total sorteos en BD:  ${COLOR_BOLD}${TOTAL_SORTEOS}${COLOR_RESET}"
    echo -e "   - Último sorteo activo: ${COLOR_BOLD}${ULTIMO_SORTEO}${COLOR_RESET}"
else
    log_error "La comprobación de salud ha fallado o ha tardado demasiado."
    log_info "Últimos registros del contenedor:"
    $DOCKER_COMPOSE logs --tail 30 primitiva-app
    exit 1
fi

# 10. Limpieza de imágenes Docker huérfanas
log_info "Limpiando imágenes Docker intermedias no utilizadas..."
docker image prune -f >/dev/null 2>&1 || true

# 11. Resumen final
echo ""
echo -e "${COLOR_BOLD}${COLOR_GREEN}==========================================================${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}   🎉 DESPLIEGUE EN PRODUCCIÓN COMPLETADO CON ÉXITO${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}==========================================================${COLOR_RESET}"
echo ""
echo -e "🌐 URL de acceso:       ${COLOR_BOLD}https://${DOMAIN}${COLOR_RESET}"
echo -e "📋 Contenedor:          ${COLOR_BOLD}${CONTAINER_NAME}${COLOR_RESET}"
echo -e "🔒 Proxy Reverso:       ${COLOR_BOLD}Traefik (${TRAEFIK_NETWORK})${COLOR_RESET}"
echo -e "📁 Datos persistentes:  ${COLOR_GRAY}${PROJECT_DIR}/data${COLOR_RESET}"
echo ""
echo -e "${COLOR_CYAN}Comandos útiles en producción:${COLOR_RESET}"
echo -e "   - Ver logs en vivo:       ${COLOR_BOLD}${DOCKER_COMPOSE} logs -f primitiva-app${COLOR_RESET}"
echo -e "   - Ver estado del servicio: ${COLOR_BOLD}${DOCKER_COMPOSE} ps${COLOR_RESET}"
echo -e "   - Reiniciar servicio:     ${COLOR_BOLD}${DOCKER_COMPOSE} restart primitiva-app${COLOR_RESET}"
echo ""
