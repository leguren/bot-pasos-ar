from fastapi import FastAPI, Request, BackgroundTasks
import httpx
import os
import unicodedata

app = FastAPI()

# --- CONFIGURACIÓN ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "a8F3kPzR9wY2qLbH5tJv6mX1sC4nD0eQ")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")  # token largo del Cloud API
PHONE_ID = os.environ.get("PHONE_ID")  # id del número de WhatsApp Cloud API
SCRAPER_URL = "https://scraper-pasos-ar-184988071501.southamerica-east1.run.app/scrapear"

# --- FUNCIONES DE LOGICA ---
def normalizar(texto):
    """Convierte a minúsculas, quita acentos y espacios extra."""
    if not texto:
        return ""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")  # elimina acentos
    return texto

def procesar_mensaje(user_text, pasos_data):
    texto = normalizar(user_text)

    # --- 1) Buscar por estado ---
    if "abierto" in texto or "cerrado" in texto:
        estado_req = "Abierto" if "abierto" in texto else "Cerrado"
        pasos_filtrados = [p for p in pasos_data if normalizar(p.get("estado","")) == normalizar(estado_req)]
        if not pasos_filtrados:
            return f"No hay pasos {estado_req}s."
        msg = f"*Pasos internacionales {estado_req.lower()}s*\n\n"
        for p in pasos_filtrados:
            icono = "🟢" if estado_req == "Abierto" else "🔴"
            msg += f"{p.get('nombre','')}\n"
        return msg.strip()

    # --- 2) Buscar por nombre de paso ---
    pasos_nombre = [p for p in pasos_data if texto in normalizar(p.get("nombre",""))]
    if pasos_nombre:
        msg = ""
        for p in pasos_nombre:
            estado = normalizar(p.get("estado",""))
            icono = "🟢" if "abierto" in estado else "🔴" if "cerrado" in estado else "⚪"
            msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n\n")
        return msg.strip()

    # --- 3) Buscar por provincia ---
    pasos_prov = [p for p in pasos_data if texto in normalizar(p.get("provincia",""))]
    if pasos_prov:
        msg = f"*Pasos internacionales en {pasos_prov[0].get('provincia','')}*\n"
        for p in pasos_prov:
            estado = normalizar(p.get("estado",""))
            icono = "🟢" if "abierto" in estado else "🔴" if "cerrado" in estado else "⚪"
            msg += (f"\n*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 4) Buscar por país ---
    pasos_pais = [p for p in pasos_data if texto in normalizar(p.get("pais",""))]
    if pasos_pais:
        msg = f"*Pasos internacionales con {pasos_pais[0].get('pais','')}*\n"
        for paso in pasos_pais:
            estado = normalizar(paso.get("estado",""))
            icono = "🟢" if "abierto" in estado else "🔴" if "cerrado" in estado else "⚪"
            msg += (f"\n*Paso internacional {paso.get('nombre','')}*\n"
                    f"{paso.get('localidades','')}\n"
                    f"{paso.get('estado','')} {icono}\n"
                    f"{paso.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 5) Mensaje de bienvenida si no se encontró nada ---
    return ("Consultá el estado de los pasos internacionales de Argentina en tiempo real.\n"
            "Ingresá el nombre del paso, la provincia en la que se encuentra o el país con el que conecta. 👉​")

# --- FUNCIONES ASINCRÓNICAS ---
async def enviar_respuesta(to_number, mensaje):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": mensaje}
    }
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            await client.post(url, headers=headers, json=payload)
        except Exception as e:
            print(f"No se pudo enviar mensaje a {to_number}: {e}")

async def obtener_pasos():
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.get(SCRAPER_URL)
            return resp.json()
        except Exception:
            return []

async def procesar_y_responder(from_number, user_text):
    pasos_data = await obtener_pasos()
    resultado = procesar_mensaje(user_text, pasos_data)
    await enviar_respuesta(from_number, resultado)

# --- WEBHOOK DE VERIFICACIÓN ---
@app.get("/webhook")
async def verify(mode: str = None, hub_verify_token: str = None, hub_challenge: str = None):
    if mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge
    return "Error de verificación", 403

# --- RECEPCIÓN DE MENSAJES ---
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

                    # 1️⃣ Respuesta inmediata (menos de 10 segundos)
                    await enviar_respuesta(from_number, "Procesando tu solicitud... ⏳")

                    # 2️⃣ Procesamiento en segundo plano
                    background_tasks.add_task(procesar_y_responder, from_number, user_text)

    return {"status": "ok"}
