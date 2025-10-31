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

# Para paginado, guardamos el estado por usuario en memoria (puede reemplazarse por Redis)
usuario_estado = {}

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

def procesar_mensaje(user_text, pasos_data, start=0, limit=10, from_number=None):
    """Procesamiento avanzado con paginado: clasifica resultados y prioriza por nombre."""
    texto = normalizar(user_text)

    # --- Mensaje de bienvenida ---
    saludos = ["hola"]
    if any(s in texto for s in saludos):
        return ("¡Hola! 👋\n"
                "Consultá el estado de los pasos internacionales de Argentina en tiempo real.\n"
                "Ingresá el nombre del paso, la provincia en la que se encuentra o el país con el que conecta."), False

    # --- Ignorar inputs muy cortos ---
    if len(texto) < 4:
        return "Por favor ingresá al menos 4 caracteres para buscar coincidencias. ❌", False

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

        # País: solo coincidencia exacta completa
        if texto == pais_norm:
            resultados_pais.setdefault(paso.get("pais",""), []).append(paso)
            continue

        # Estado
        if ("abierto" in texto and "abierto" in estado_norm) or ("cerrado" in texto and "cerrado" in estado_norm):
            resultados_estado.setdefault(paso.get("estado",""), []).append(paso)

    # --- Combinar todos los pasos en una lista para paginado ---
    pasos_completos = resultados_nombre + sum(resultados_provincia.values(), []) + \
                     sum(resultados_pais.values(), []) + sum(resultados_estado.values(), [])

    total_pasos = len(pasos_completos)
    pasos_a_enviar = pasos_completos[start:start+limit]

    if not pasos_a_enviar:
        return f"No encontré pasos que coincidan con '{user_text}'. ❌", False

    # --- Construir mensaje final ---
    msg = ""
    for p in pasos_a_enviar:
        icono = emoji_estado(p.get("estado",""))
        msg += (f"*Paso internacional {p.get('nombre','')}*\n"
                f"{p.get('localidades','')}\n"
                f"{p.get('estado','')} {icono}\n"
                f"{p.get('ultima_actualizacion','')}\n\n")

    hay_mas = total_pasos > start + limit
    if hay_mas and from_number:
        # Guardamos el estado del usuario por número de WhatsApp
        usuario_estado[from_number] = {
            "pasos": pasos_completos,
            "start": start + limit,
            "limit": limit,
            "user_text": user_text
        }

    return msg.strip(), hay_mas

# === FUNCIONES ASINCRÓNICAS ===
async def enviar_respuesta(to_number, mensaje, hay_mas=False):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

    if hay_mas:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": mensaje},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "cargar_mas", "title": "Cargar más"}}
                    ]
                }
            }
        }
    else:
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

async def procesar_y_responder(from_number, user_text, start=0, limit=10):
    pasos_data = await obtener_pasos()
    resultado, hay_mas = procesar_mensaje(user_text, pasos_data, start=start, limit=limit, from_number=from_number)
    await enviar_respuesta(from_number, resultado, hay_mas=hay_mas)

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

                    # === Detectar texto o botón ===
                    if tipo == "text":
                        user_text = message["text"]["body"].strip()
                    elif tipo == "button":
                        user_text = message.get("button", {}).get("payload") or message.get("button", {}).get("text") or ""
                    else:
                        print(f"Ignorado mensaje tipo '{tipo}' de {from_number}")
                        await enviar_respuesta(
                            from_number,
                            "👀 Por ahora sólo puedo responder a mensajes de texto o botones.\n"
                            "Probá ingresando nuevamente el nombre del paso, la provincia o el país con el que conecta."
                        )
                        continue

                    texto_norm = normalizar(user_text)

                    # === Mensaje de bienvenida (saludo) ===
                    saludos = ["hola"]
                    if any(s in texto_norm for s in saludos):
                        pasos_data = []
                        resultado, _ = procesar_mensaje(user_text, pasos_data)
                        await enviar_respuesta(from_number, resultado)
                        continue

                    # === Botón “Cargar más” ===
                    if texto_norm == "cargar_mas":
                        estado = usuario_estado.pop(from_number, None)
                        if estado:
                            background_tasks.add_task(
                                procesar_y_responder,
                                from_number,
                                user_text=estado["user_text"],
                                start=estado["start"],
                                limit=estado["limit"]
                            )
                        else:
                            await enviar_respuesta(from_number, "⚠ No hay más resultados para mostrar.")
                        continue

                    # === Resto de mensajes ===
                    await enviar_respuesta(from_number, "Procesando tu solicitud... ⏳")
                    background_tasks.add_task(procesar_y_responder, from_number, user_text)

    return {"status": "ok"}
