# === IMPORTS Y CONFIG ===
from fastapi import FastAPI, Request, BackgroundTasks
import httpx
import os
import unicodedata
import logging

app = FastAPI()

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "a8F3kPzR9wY2qLbH5tJv6mX1sC4nD0eQ")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_ID = os.environ.get("PHONE_ID")
SCRAPER_URL = "https://scraper-pasos-ar-184988071501.southamerica-east1.run.app/scrapear"

logging.basicConfig(
    level=logging.INFO,  # Para registrar todos los mensajes entrantes
    format="%(asctime)s [%(levelname)s] %(message)s"
)

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
    """Búsqueda simple y combinada, país exacto, palabras ≥4 caracteres, sin romper filtros simples."""
    texto = normalizar(user_text)

    # --- Mensaje de bienvenida ---
    saludos = ["hola"]
    if any(s in texto for s in saludos):
        return ('¡Hola! 👋 ¿Cómo estás?\n\n'
                'Acá vas a poder consultar el estado de los pasos internacionales de Argentina en tiempo real.\n\n'
                'Podés buscar por el nombre del paso, la provincia en la que se encuentra o el país con el que conecta.\n'
                '💡 Por ejemplo: escribí "agua" para buscar los pasos Agua Negra o Aguas Blancas - Bermejo, o "abiertos con Brasil" para buscar todos los pasos abiertos con Brasil.')

    # --- Ignorar inputs muy cortos ---
    if len(texto) < 4:
        return ('Por favor, ingresá al menos 4 letras para poder buscar coincidencias.\n\n'
                '💡 Por ejemplo: escribí "agua" para buscar los pasos Agua Negra o Aguas Blancas - Bermejo, o "abiertos con Brasil" para buscar todos los pasos abiertos con Brasil.')

    # --- Detectar filtros ---
    filtro_estado = None
    if "abierto" in texto or "abiertos" in texto:
        filtro_estado = "abierto"
    elif "cerrado" in texto or "cerrados" in texto:
        filtro_estado = "cerrado"

    filtro_provincias = set()
    filtro_paises = set()
    nombres = []

    todos = "todos" in texto
    user_words = [w for w in texto.split() if len(w) >= 4]

    # --- Preparar filtros ---
    for paso in pasos_data:
        provincia_norm = normalizar(paso.get("provincia",""))
        pais_norm = normalizar(paso.get("pais",""))
        nombre_norm = normalizar(paso.get("nombre",""))

        # Nombre: coincidencia frase completa o palabra ≥4
        if texto in nombre_norm or any(word in nombre_norm for word in user_words):
            nombres.append(paso)

        # Provincia: frase completa o palabra ≥4
        if texto in provincia_norm or any(word in provincia_norm for word in user_words):
            filtro_provincias.add(provincia_norm)

        # País: coincidencia exacta de palabra
        for word in user_words:
            if word == pais_norm:
                filtro_paises.add(pais_norm)

    # --- Construir resultados ---
    resultados_combinados = []
    resultados_simples = []

    if filtro_estado or filtro_provincias or filtro_paises or todos:
        # Lógica combinada
        for paso in pasos_data:
            estado_norm = normalizar(paso.get("estado",""))
            provincia_norm = normalizar(paso.get("provincia",""))
            pais_norm = normalizar(paso.get("pais",""))

            cumple = True
            if filtro_estado and filtro_estado not in estado_norm:
                cumple = False
            if filtro_provincias and provincia_norm not in filtro_provincias:
                cumple = False
            if filtro_paises and pais_norm not in filtro_paises:
                cumple = False
            if cumple:
                resultados_combinados.append(paso)
    else:
        # Solo búsqueda simple por nombre/provincia/estado/pais
        resultados_simples = nombres[:]

    # --- Construir mensaje final ---
    if not resultados_combinados and not resultados_simples:
        return (f'No encontré pasos que coincidan con "{user_text}".\n\n'
                'Probá ingresando nuevamente el nombre del paso, el de la provincia en la que se encuentra o el del país con el que conecta.\n\n'
                '💡 Recordá que debés ingresar al menos 4 letras para que pueda buscar coincidencias.')

    from collections import defaultdict
    msg = ""
    primer_bloque = True
    grouped_simple = defaultdict(list)
    grouped_combinada = defaultdict(list)

    # --- Agrupar simples ---
    for paso in resultados_simples:
        grouped_simple["nombre"].append(paso)

    # --- Agrupar combinados ---
    for paso in resultados_combinados:
        estado_norm = normalizar(paso.get("estado",""))
        provincia_norm = normalizar(paso.get("provincia",""))
        pais_norm = normalizar(paso.get("pais",""))
        key = (provincia_norm if provincia_norm in filtro_provincias else None,
               pais_norm if pais_norm in filtro_paises else None,
               estado_norm if filtro_estado and filtro_estado in estado_norm else None)
        grouped_combinada[key].append(paso)

    # --- Mostrar resultados simples ---
    for key, pasos in grouped_simple.items():
        if not primer_bloque:
            msg += "\n"
        for p in pasos:
            icono = emoji_estado(p.get("estado",""))
            msg += (f"*{p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n\n")
        primer_bloque = False

    # --- Mostrar resultados combinados ---
    for (provincia, pais, estado), pasos in grouped_combinada.items():
        if not primer_bloque:
            msg += "\n"
        titulo = "👉 *Pasos internacionales"
        if provincia:
            titulo += f" en {provincia.title()}"
        if pais:
            titulo += f" con {pais.title()}"
        if estado:
            titulo += f" {estado}s"
        titulo += "*\n\n"

        msg += titulo
        for p in pasos:
            icono = emoji_estado(p.get("estado",""))
            msg += (f"*{p.get('nombre','')}*\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')} {icono}\n"
                    f"{p.get('ultima_actualizacion','')}\n\n")
        primer_bloque = False

    return msg.strip()

# === DIVIDIR MENSAJES ===
MAX_LEN = 4000
def dividir_mensaje(msg):
    partes = []
    pasos = msg.split("\n\n")  # <- usamos el doble salto de línea como delimitador
    buffer = ""
    for paso in pasos:
        if not paso.strip():
            continue  # ignorar bloques vacíos
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

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    if not data or "entry" not in data:
        return {"status": "no entry found"}

    for entry in data["entry"]:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])

            for message in messages:
                tipo = message.get("type", "")
                from_number = message.get("from")

                if tipo != "text":
                    logging.info("Ignorado mensaje tipo '%s' de %s", tipo, from_number)
                    await enviar_respuesta(
                        from_number,
                        '👀 Por ahora no puedo escuchar audios, ni ver fotos o stickers.\n\n'
                        'Probá ingresando nuevamente el nombre del paso, el de la provincia en la que se encuentra o el del país con el que conecta.\n\n'
                        '💡 Recordá que debés ingresar al menos 4 letras para que pueda buscar coincidencias.'
                    )
                    continue

                user_text = message["text"]["body"].strip()
                texto_norm = normalizar(user_text)

                # --- Detectar saludos ---
                saludos = ["hola"]
                if any(s in texto_norm for s in saludos):
                    pasos_data = []  # No hace falta scrapear si es solo saludo
                    resultado = procesar_mensaje(user_text, pasos_data)
                    for parte in dividir_mensaje(resultado):
                        await enviar_respuesta(from_number, parte)
                    continue

                # --- Detectar agradecimientos ---
                agradecimientos = ["gracias"]
                if any(a in texto_norm for a in agradecimientos):
                    await enviar_respuesta(
                        from_number,
                        '¡De nada! 🤩 Acá estaré para ayudarte cuando tengas nuevas consultas sobre el estado de los pasos internacionales.'
                    )
                    continue

                # --- Detectar textos demasiado cortos (menos de 4 letras) ---
                if len(texto_norm) < 4:
                    await enviar_respuesta(
                        from_number,
                        'Por favor, ingresá al menos 4 letras para poder buscar coincidencias.\n\n'
                        '💡 Por ejemplo: escribí "agua" para buscar los pasos Agua Negra o Aguas Blancas - Bermejo, o "abiertos con Brasil" para buscar todos los pasos abiertos con Brasil.')
                    continue  # No llamamos al scraper

                # --- Para el resto de los mensajes ---
                await enviar_respuesta(from_number, 'Buscando pasos... ⏳')
                background_tasks.add_task(procesar_y_responder, from_number, user_text)

    return {"status": "ok"}



