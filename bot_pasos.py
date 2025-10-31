# === IMPORTS Y CONFIG ===
from fastapi import FastAPI, Request, BackgroundTasks
import httpx
import os
import unicodedata

app = FastAPI()

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "a8F3kPzR9wY2qLbH5tJv6mX1sC4nD0eQ")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_ID = os.environ.get("PHONE_ID")
SCRAPER_URL = "https://scraper-pasos-ar-184988071501.southamerica-east1.run.app/scrapear"

# === FUNCIONES DE LÓGICA ===
def normalizar(texto):
    if not texto:
        return ""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto

def emoji_estado(estado: str) -> str:
    estado_norm = normalizar(estado)
    if "abierto" in estado_norm:
        return "🟢"
    elif "cerrado" in estado_norm:
        return "🔴"
    return "⚪"

def procesar_mensaje(user_text, pasos_data):
    texto = normalizar(user_text)
    if not texto:
        return ("Consultá el estado de los pasos internacionales de Argentina en tiempo real.\n"
                "Ingresá el nombre del paso, la provincia en la que se encuentra o el país con el que conecta. 👉")

    resultados = []
    for paso in pasos_data:
        coincidencias = []

        estado_norm = normalizar(paso.get("estado",""))
        if "abierto" in texto and "abierto" in estado_norm:
            coincidencias.append("abierto")
        elif "cerrado" in texto and "cerrado" in estado_norm:
            coincidencias.append("cerrado")

        if texto in normalizar(paso.get("nombre","")):
            coincidencias.append("nombre")
        if texto in normalizar(paso.get("provincia","")):
            coincidencias.append("provincia")
        if texto in normalizar(paso.get("pais","")):
            coincidencias.append("pais")

        if coincidencias:
            resultados.append(paso)

    if resultados:
        msg = ""
        for p in resultados:
            icono = emoji_estado(p.get("estado",""))
            msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('provincia','')} - {p.get('pais','')}\n"
                    f"{p.get('ultima_actualizacion','')}\n\n")
        return msg.strip()

    return ("Consultá el estado de los pasos internacionales de Argentina en tiempo real.\n"
            "Ingresá el nombre del paso, la provincia en la que se encuentra o el país con el que conecta. 👉")

# === DIVIDIR MENSAJES ===
MAX_LEN = 4000
def dividir_mensaje(msg):
    pasos = msg.split("\n*Paso internacional ")
    partes = []
    buffer = ""
    for i, paso in enumerate(pasos):
        if i != 0:
            paso = "*Paso internacional " + paso
        if len(buffer) + len(paso) + 2 > MAX_LEN:
            partes.append(buffer.strip())
            buffer = paso
        else:
            buffer += ("\n\n" if buffer else "") + paso
    if buffer:
        partes.append(buffer.strip())
    return partes

# === FUNCIONES ASINCRÓNICAS ===
async def enviar_respuesta(to_number, mensaje):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": mensaje}}
    async with httpx.AsyncClient(timeout=40) as client:
        try:
            await client.post(url, headers=headers, json=payload)
        except Exception as e:
            print(f"No se pudo enviar mensaje a {to_number}: {e}")

async def obtener_pasos():
    async with httpx.AsyncClient(timeout=40) as client:
        try:
            resp = await client.get(SCRAPER_URL)
            return resp.json()
        except Exception:
            return []

async def procesar_y_responder(from_number, user_text):
    pasos_data = await obtener_pasos()
    resultado = procesar_mensaje(user_text, pasos_data)
    for parte in dividir_mensaje(resultado):
        await enviar_respuesta(from_number, parte)

# === WEBHOOK DE VERIFICACIÓN ===
@app.get("/webhook")
async def verify(mode: str = None, hub_verify_token: str = None, hub_challenge: str = None):
    if mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge
    return "Error de verificación", 403

# === RECEPCIÓN DE MENSAJES ===
@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    if data and "entry" in data:
        for entry in data["entry"]:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for message in messages:
                    tipo = message.get("type", "")
                    from_number = message.get("from")

                    if tipo != "text":
                        print(f"Ignorado mensaje tipo '{tipo}' de {from_number}")
                        await enviar_respuesta(from_number, "Por ahora sólo puedo responder a mensajes de texto.")
                        continue

                    user_text = message["text"]["body"].strip()
                    await enviar_respuesta(from_number, "Procesando tu solicitud... ⏳")
                    background_tasks.add_task(procesar_y_responder, from_number, user_text)

    return {"status": "ok"}
