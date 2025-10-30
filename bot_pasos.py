from flask import Flask, request
import requests
import os

app = Flask(__name__)

# --- CONFIGURACIÓN ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "a8F3kPzR9wY2qLbH5tJv6mX1sC4nD0eQ")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")  # token largo del Cloud API
PHONE_ID = os.environ.get("PHONE_ID")  # id del número de WhatsApp Cloud API
SCRAPER_URL = "https://scraper-pasos-ar-184988071501.southamerica-east1.run.app/scrapear"

# --- FUNCIONES DE LOGICA ---
def procesar_mensaje(user_text, pasos_data):
    texto = user_text.strip().lower()

    # --- 1) Buscar por estado ---
    if "abierto" in texto or "cerrado" in texto:
        estado_req = "Abierto" if "abierto" in texto else "Cerrado"
        pasos_filtrados = [p for p in pasos_data if p.get("estado", "").lower() == estado_req.lower()]
        if not pasos_filtrados:
            return f"No hay pasos {estado_req}s."
        msg = f"Pasos {estado_req.lower()}s:\n"
        for p in pasos_filtrados:
            msg += (f"{p.get('nombre','')}\n")
        return msg.strip()

    # --- 2) Buscar por nombre de paso (parcial) -> devuelve todos los que coincidan ---
    pasos_nombre = [p for p in pasos_data if texto in p.get("nombre", "").lower()]
    if pasos_nombre:
        msg = ""
        for p in pasos_nombre:
            msg += (f"Paso internacional {p.get('nombre','')}\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 3) Buscar por provincia (parcial) ---
    pasos_prov = [p for p in pasos_data if texto in p.get("provincia", "").lower()]
    if pasos_prov:
        msg = f"Estado de los pasos de la provincia {pasos_prov[0].get('provincia','')}:\n"
        for p in pasos_prov:
            msg += (f"\nPaso internacional {p.get('nombre','')}\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 4) Buscar por país limítrofe (parcial) ---
    pasos_pais = [p for p in pasos_data if texto in p.get("pais", "").lower()]
    if pasos_pais:
        msg = f"Estado de los pasos con {pasos_pais[0].get('pais','')}:\n"
        for p in pasos_pais:
            msg += (f"\nPaso internacional {p.get('nombre','')}\n"
                    f"{p.get('localidades','')}\n"
                    f"{p.get('estado','')}\n"
                    f"{p.get('ultima_actualizacion','')}\n")
        return msg.strip()

    # --- 5) Mensaje de bienvenida si no se encontró nada ---
    return ("Consultá el estado de los pasos internacionales de Argentina en tiempo real. "
            "Ingresá el nombre del paso, provincia o país vecino que quieras consultar.")

# --- WEBHOOK DE VERIFICACIÓN ---
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge
    return "Error de verificación", 403


# --- FUNCIÓN AUXILIAR PARA ENVIAR RESPUESTAS ---
def enviar_respuesta(numero, texto):
    url = f"https://graph.facebook.com/v20.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Error al enviar mensaje: {e}")


# --- RECEPCIÓN DE MENSAJES ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    try:
        if not data or "entry" not in data:
            return "EVENT_IGNORED", 200

        for entry in data["entry"]:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])

                for message in messages:
                    tipo = message.get("type", "")
                    from_number = message.get("from")

                    # --- Ignora stickers, audios, etc., pero sin romper el flujo ---
                    if tipo != "text":
                        print(f"Ignorado mensaje tipo '{tipo}' de {from_number}")
                        enviar_respuesta(from_number, "Por ahora solo puedo responder a mensajes de texto 😊")
                        continue

                    user_text = message["text"]["body"].strip()

                    # Consultar scrapper
                    try:
                        resp = requests.get(SCRAPER_URL, timeout=10)
                        pasos_data = resp.json() if resp.status_code == 200 else []
                    except Exception as e:
                        print(f"Error al consultar scrapper: {e}")
                        pasos_data = []

                    # Generar respuesta según lógica
                    resultado = procesar_mensaje(user_text, pasos_data)

                    # Enviar respuesta
                    enviar_respuesta(from_number, resultado)

        return "EVENT_RECEIVED", 200

    except Exception as e:
        print(f"Error general en webhook: {e}")
        return "EVENT_ERROR", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
