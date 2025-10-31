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
    """Procesamiento avanzado: clasifica resultados según coincidencia y prioriza por nombre."""
    texto = normalizar(user_text)

    # --- Mensaje de bienvenida ---
    saludos = ["hola"]
    if any(s in texto for s in saludos):
        return ("¡Hola! 👋\n"
                "Consultá el estado de los pasos internacionales de Argentina en tiempo real.\n"
                "Ingresá el nombre del paso, la provincia en la que se encuentra o el país con el que conecta.")

    # --- Preparar resultados ---
    resultados_nombre = []
    resultados_provincia = {}
    resultados_pais = {}
    resultados_estado = {}

    for paso in pasos_data:
        estado_norm = normalizar(paso.get("estado", ""))
        nombre_norm = normalizar(paso.get("nombre", ""))
        provincia_norm = normalizar(paso.get("provincia", ""))
        pais_norm = normalizar(paso.get("pais", ""))

        # Prioridad por nombre
        if texto in nombre_norm:
            resultados_nombre.append(paso)
            continue

        # Provincia
        if texto in provincia_norm:
            resultados_provincia.setdefault(paso.get("provincia",""), []).append(paso)
            continue

        # País
        if texto in pais_norm:
            resultados_pais.setdefault(paso.get("pais",""), []).append(paso)
            continue

        # Estado
        if ("abierto" in texto and "abierto" in estado_norm) or ("cerrado" in texto and "cerrado" in estado_norm):
            resultados_estado.setdefault(paso.get("estado",""), []).append(paso)

    # --- Construir mensaje final ---
    msg = ""
    primer_bloque = True

    # Resultados por nombre
    for p in resultados_nombre:
        icono = emoji_estado(p.get("estado",""))
        msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                f"{p.get('localidades','')}\n"
                f"{p.get('estado','')} {icono}\n"
                f"{p.get('ultima_actualizacion','')}\n")
    primer_bloque = False if resultados_nombre else True

    # Resultados por provincia
    for provincia, pasos in resultados_provincia.items():
        if not primer_bloque:
            msg += "\n"
        msg += f"👉 *Pasos internacionales en {provincia}*\n"
        for p in pasos:
            icono = emoji_estado(p.get("estado",""))
            msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        primer_bloque = False

    # Resultados por país
    for pais, pasos in resultados_pais.items():
        if not primer_bloque:
            msg += "\n"
        msg += f"👉 *Pasos internacionales con {pais}*\n"
        for p in pasos:
            icono = emoji_estado(p.get("estado",""))
            msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        primer_bloque = False

    # Resultados por estado
    for estado, pasos in resultados_estado.items():
        if not primer_bloque:
            msg += "\n"
        msg += f"👉 *Pasos internacionales {estado}s*\n"
        for p in pasos:
            icono = emoji_estado(p.get("estado",""))
            msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        primer_bloque = False

    # --- Mensaje si no se encontró coincidencia ---
    if not msg:
        return (f"No encontré pasos que coincidan con '{user_text}'. ❌\n"
                "Probá ingresando nuevamente el nombre del paso, la provincia o el país con el que conecta.")

    return msg.strip()

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
                        await enviar_respuesta(from_number, "👀 Por ahora sólo puedo responder a mensajes de texto.")
                        continue

                    user_text = message["text"]["body"].strip()
                    await enviar_respuesta(from_number, "Procesando tu solicitud... ⏳")
                    background_tasks.add_task(procesar_y_responder, from_number, user_text)

    return {"status": "ok"}


