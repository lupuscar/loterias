# 🎱 Primitiva Analytics & Motor de Pronósticos por Diferencias

Aplicación web moderna y analítica para la **Lotería Primitiva**, construida con **FastAPI**, **SQLite** y un motor predictivo basado en el **análisis de diferencias posicionales consecutivas** sobre más de **4.200 sorteos históricos** (desde 1985 hasta la actualidad).

---

## 🚀 Características Principales

1. **🔮 Módulo de Pronósticos Inteligentes:**
   - **Análisis Diferencial Posicional:** Calcula para cada posición ($n_1 < n_2 < \dots < n_6$) los saltos entre sorteos consecutivos ($d_i = n_i(T) - n_i(T-1)$).
   - **Estrategias Configurables:**
     - ⚡ *Equilibrio & Regresión al Centro:* Combina el salto medio con la atracción gravitacional hacia el centro teórico de cada posición ($E[n_i] = i \cdot \frac{50}{7}$).
     - 📈 *Media Aritmética:* Desplazamiento medio histórico o en ventana temporal.
     - 🎯 *Moda de Saltos:* Aplica los saltos exactos más frecuentes en la historia.
     - 📏 *Magnitud Típica:* Amplitud media de desplazamiento.
     - 🎲 *Monte Carlo Ponderado:* Generación estocástica fiel a la distribución empírica de frecuencias.
   - **Comprobación Histórica (Backtesting):** Simula el comportamiento del modelo retrospectivamente y muestra la tasa de aciertos de 3, 4, 5 y 6 números.

2. **📊 Estudio Estadístico de Diferencias:**
   - Panel visual con las 6 posiciones.
   - Gráfico interactivo (histograma de frecuencias) de saltos por posición.
   - Tabla de las últimas diferencias consecutivas calculadas.

3. **📋 Consultor Histórico (+4.200 Sorteos):**
   - Buscador por año, mes o número específico.
   - Visualización con bolas de lotería realistas (combinación, complementario, reintegro, joker, bote).
   - Modal con desglose de categorías y premios por sorteo.

4. **➕ Actualizador de Sorteos:**
   - Formulario para registrar nuevos sorteos con selector visual de 49 números.
   - Validación automática de duplicados y ordenación ascendente inmediata.

---

## 🛠️ Ejecución en Local (WSL / Linux)

### 1. Activar el entorno virtual e instalar dependencias
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Inicializar la base de datos SQLite (restauración instantánea desde semilla)
```bash
python3 scripts/init_db.py
```
> La base de datos viva se almacena en `data/primitiva.db` (no rastreada en Git para evitar conflictos de producción). Si no existe, se restaura en 0,2s a partir de la semilla comprimida `data/seed.sql.gz`.
> - Para regenerar la semilla con datos actuales: `python3 scripts/init_db.py --dump-seed`
> - Para forzar la recreación local desde la semilla: `python3 scripts/init_db.py --force`

### 3. Iniciar el servidor de desarrollo
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Abre tu navegador en: **`http://localhost:8000`**  
Documentación interactiva Swagger: **`http://localhost:8000/docs`**

---

## 🐳 Despliegue en Producción (VPS con Docker & Traefik)

El proyecto incluye `Dockerfile` optimizado (`python:3.12-slim`) y `docker-compose.yml` preconfigurado con etiquetas para Traefik.

### 1. Clonar en tu VPS
```bash
git clone <tu-repositorio-git>
cd loterias
```

### 2. Configurar variables de entorno (.env)
Copia la plantilla y configura tu dominio y la red externa de Traefik:
```bash
cp .env.example .env
nano .env
```
Ejemplo de `.env`:
```env
DOMAIN=primitiva.tudominio.com
TRAEFIK_NETWORK=backend-with-internet
```

### 3. Ejecutar el script de despliegue en producción
El script automatizado realiza comprobaciones de requisitos, backup de la base de datos SQLite, pull de Git (si procede), build optimizado y health check:
```bash
./deploy.sh
```

La base de datos SQLite se almacena en el volumen persistente `./data`, por lo que tus sorteos nuevos nunca se perderán entre actualizaciones de contenedor.


---

## 📡 Endpoints de la API REST

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/` | Aplicación web interactiva (SPA) |
| `GET` | `/api/health` | Estado del sistema, total de sorteos y premios |
| `GET` | `/api/sorteos/ultimo` | Datos del último sorteo registrado |
| `GET` | `/api/sorteos` | Listado paginado con filtros por fecha y número |
| `GET` | `/api/sorteos/{id}` | Detalle del sorteo y premios asociados |
| `POST` | `/api/sorteos` | Registrar un nuevo sorteo (validación estricta) |
| `GET` | `/api/estadisticas/diferencias` | Medias, modas, desviaciones y distribución |
| `GET` | `/api/estadisticas/recientes-diferencias` | Últimos pares con vector de saltos |
| `GET` | `/api/pronosticos` | Generador de pronósticos configurables |
| `GET` | `/api/pronosticos/backtesting` | Simulación histórica de aciertos |
