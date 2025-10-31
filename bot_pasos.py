from fastapi import FastAPI, Request, BackgroundTasks
import httpx
import os
import unicodedata

app = FastAPI()

# --- CONFIGURACIÓN ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "a8F3kPzR9wY2qLbH5tJv6mX1sC4nD0eQ")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_ID = os.environ.get("PHONE_ID")
SCRAPER_URL = "https://scraper-pasos-ar-184988071501.southamerica-east1.run.app/scrapear"

# --- FUNCIONES DE LÓGICA ---
def normalizar(texto):
    if not texto:
        return ""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto

def procesar_mensaje(user_text, pasos_data):
    texto = normalizar(user_text)

    # --- 1) Hola → mensaje de bienvenida ---
    if texto in ["hola", "hi", "buenas", "buen día", "buenos días"]:
        return "bienvenida"

    # --- 2) Buscar por estado ---
    if "abierto" in texto or "cerrado" in texto:
        estado_req = "Abierto" if "abierto" in texto else "Cerrado"
        pasos_filtrados = [p for p in pasos_data if normalizar(p.get("estado","")) == normalizar(estado_req)]
        if not pasos_filtrados:
            return "no_encontrado"
        msg = f"*Pasos internacionales {estado_req.lower()}s*\n\n"
        for p in pasos_filtrados:
            msg += f"{p.get('nombre','')}\n"
        return msg.strip()

    # --- 3) Buscar por nombre de paso ---
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

    # --- 4) Buscar por provincia ---
    pasos_prov = [p for p in pasos_data if texto in normalizar(p.get("provincia",""))]
    if pasos_prov:
        msg = f"*Pasos internacionales en {pasos_prov[0].get('provincia','')}*\n"
        for p in pasos_prov:
            estado = normalizar(p.get("estado",""))
            icono = "🟢" if "abierto" in estado else "🔴" if "cerrado" in estado else "⚪"
            msg += (f"\n*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 5) Buscar por país ---
    pasos_pais = [p for p in pasos_data if texto in normalizar(p.get("pais",""))]
    if pasos_pais:
        msg = f"*Pasos internacionales con {pasos_pais[0].get('pais','')}*\n"
        for paso in pasos_pais:
            estado = normalizar(paso.get("estado",""))
            icono = "🟢" if "abierto" in estado else "🔴" if "cerrado" in estado else "⚪"
            msg += (f"\n*Paso internacional {paso.get('nombre','')}*\n"
                    f"{paso.get('estado','')} {icono}\n"
                    f"{paso.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 6) No se encontró nada ---
    return "no_encontrado"

# --- LÍMITE DE CARACTERES ---
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
            buffer = (buffer + "\n\n" + paso) if buffer else paso
    if buffer:
        partes.append(buffer.strip())
    return partes

# --- FUNCIONES DE BOTONES ---
async def enviar_bienvenida_con_botones(to_number):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Hola 👋! Podés consultar los pasos internacionales por nombre, provincia o usando estos botones:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "ver_todos", "title": "Ver todos los pasos"}},
                    {"type": "reply", "reply": {"id": "ver_abiertos", "title": "Ver solo los abiertos"}},
                    {"type": "reply", "reply": {"id": "ver_cerrados", "title": "Ver solo los cerrados"}},
                    {"type": "reply", "reply": {"id": "buscar_pais", "title": "Buscar por país"}}
                ]
            }
        }
    }
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(url, headers=headers, json=payload)

async def enviar_no_encontrado_con_botones(to_number):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "No encontré lo que estás buscando. Intentá nuevamente o probá con estos botones:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "ver_todos", "title": "Ver todos los pasos"}},
                    {"type": "reply", "reply": {"id": "ver_abiertos", "title": "Ver solo los abiertos"}},
                    {"type": "reply", "reply": {"id": "ver_cerrados", "title": "Ver solo los cerrados"}},
                    {"type": "reply", "reply": {"id": "buscar_pais", "title": "Buscar por país"}}
                ]
            }
        }
    }
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(url, headers=headers, json=payload)

# --- FUNCIONES ASINCRÓNICAS ---
async def enviar_respuesta(to_number, mensaje):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": mensaje}}
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(url, headers=headers, json=payload)

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

    if resultado == "bienvenida":
        await enviar_bienvenida_con_botones(from_number)
        return
    elif resultado == "no_encontrado":
        await enviar_no_encontrado_con_botones(from_number)
        return

    # dividimos y enviamos normalmente
    for parte in dividir_mensaje(resultado):
        await enviar_respuesta(from_number, parte)

# --- WEBHOOK ---
@app.get("/webhook")
async def verify(mode: str = None, hub_verify_token: str = None, hub_challenge: str = None):
    if mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge
    return "Error de verificación", 403

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

                    if tipo == "text":
                        user_text = message["text"]["body"].strip()
                        # --- procesar directamente ---
                        background_tasks.add_task(procesar_y_responder, from_number, user_text)
                        continue

                    if tipo == "interactive":
                        interactive_type = message["interactive"]["type"]
                        if interactive_type == "button_reply":
                            reply_id = message["interactive"]["button_reply"]["id"]
                            pasos_data = await obtener_pasos()
                            if reply_id == "ver_todos":
                                resultado = procesar_mensaje("todos", pasos_data)
                            elif reply_id == "ver_abiertos":
                                resultado = procesar_mensaje("abierto", pasos_data)
                            elif reply_id == "ver_cerrados":
                                resultado = procesar_mensaje("cerrado", pasos_data)
                            elif reply_id == "buscar_pais":
                                continue
                            elif reply_id.startswith("pais_"):
                                pais = reply_id.split("_")[1].capitalize()
                                resultado = procesar_mensaje(pais, pasos_data)
                            else:
                                continue
                            if resultado and resultado not in ["bienvenida", "no_encontrado"]:
                                for parte in dividir_mensaje(resultado):
                                    await enviar_respuesta(from_number, parte)
                        continue

    return {"status": "ok"}
