# Imagen base
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Copiar archivo de dependencias e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del bot
COPY . .

# Puerto que usará Cloud Run
ENV PORT=8080

# Comando para ejecutar la app con Uvicorn (FastAPI)
CMD ["uvicorn", "bot_pasos:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
