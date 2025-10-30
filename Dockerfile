# Imagen base
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del bot
COPY . .

# Puerto que usará Cloud Run
ENV PORT=8080

# Comando para ejecutar la app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "bot_pasos:app"]
