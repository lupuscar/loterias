FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto y datasets
COPY app/ ./app/
COPY engine/ ./engine/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY sorteos_primitiva.csv .
COPY sorteos_premios.csv .

# Directorio para la base de datos persistente SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
