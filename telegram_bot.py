import os
import requests
from flask import Flask, request, jsonify
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
APPS_SCRIPT_URL = os.environ['APPS_SCRIPT_URL']
DIRECTORIO_SHEET_ID = os.environ['DIRECTORIO_SHEET_ID']
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

sesiones = {}

def get_sheets_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ['GOOGLE_REFRESH_TOKEN'],
        client_id=os.environ['GOOGLE_CLIENT_ID'],
        client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
        token_uri='https://oauth2.googleapis.com/token',
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    creds.refresh(Request())
    return build('sheets', 'v4', credentials=creds)

def buscar_usuario(telefono):
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=DIRECTORIO_SHEET_ID,
            range='Hoja1!A:E'
        ).execute()
        rows = result.get('values', [])
        print(f"Total filas: {len(rows)}")
        print(f"Buscando telefono: [{telefono}] tipo: {type(telefono)}")
        for i, row in enumerate(rows[1:]):
            if len(row) >= 1:
                val = row[0].strip()
                print(f"Fila {i+2}: [{val}] len={len(val)} igual={val == str(telefono)}")
                if len(val) == len(str(telefono)):
                    for j, (a, b) in enumerate(zip(val, str(telefono))):
                        if a != b:
                            print(f"  Diferencia en pos {j}: [{ord(a)}] vs [{ord(b)}]")
                if len(row) >= 5 and val == str(telefono) and row[4].strip().upper() == 'TRUE':
                    return {
                        'telefono': row[0],
                        'nombre': row[1],
                        'rol': row[2].lower(),
                        'empresas': row[3].lower(),
                        'activo': True
                    }
    except Exception as e:
        print(f"Error buscando usuario: {e}")
    return None

def consultar_agente(pregunta, usuario):
    try:
        params = {
            'query': pregunta,
            'usuario': usuario['nombre'],
            'rol': usuario['rol'],
            'empresas': usuario['empresas']
        }
        resp = requests.get(APPS_SCRIPT_URL, params=params, timeout=30)
        return resp.text
    except Exception as e:
        return f"Error consultando al agente: {e}"

def send_message(chat_id, text, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

def request_phone(chat_id):
    reply_markup = {
        "keyboard": [[{"text": "📱 Compartir mi número", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    send_message(chat_id,
        "Hola! Soy Jarvis, el agente de Simón.\n\n"
        "Para verificar tu acceso necesito confirmar tu número de teléfono.\n"
        "Toca el botón para compartirlo de forma segura 👇",
        reply_markup=reply_markup)

def remove_keyboard(chat_id, text):
    send_message(chat_id, text, reply_markup={"remove_keyboard": True})

@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=['POST'])
def webhook():
    update = request.json
    if 'message' not in update:
        return jsonify({'ok': True})

    msg = update['message']
    chat_id = msg['chat']['id']
    user_id = msg['from']['id']
    texto = msg.get('text', '').strip()

    if 'contact' in msg:
        telefono = msg['contact']['phone_number'].replace('+', '').replace(' ', '')
        print(f"Número recibido de Telegram: [{telefono}]")
        if msg['contact'].get('user_id') and msg['contact']['user_id'] != user_id:
            send_message(chat_id, "⚠️ Por favor comparte tu propio número.")
            return jsonify({'ok': True})
        usuario = buscar_usuario(telefono)
        if usuario:
            sesiones[user_id] = usuario
            remove_keyboard(chat_id,
                f"✅ Acceso verificado. Hola {usuario['nombre'].split()[0]}!\n"
                "Ya puedes hacerme tus preguntas.")
        else:
            remove_keyboard(chat_id,
                f"❌ Número {telefono} no registrado.\n"
                "Contacta a Simón para solicitar acceso.")
        return jsonify({'ok': True})

    if texto == '/start':
        if user_id in sesiones:
            send_message(chat_id, f"Ya estás verificado. ¿En qué te puedo ayudar?")
        else:
            request_phone(chat_id)
        return jsonify({'ok': True})

    if not texto:
        return jsonify({'ok': True})

    if user_id not in sesiones:
        request_phone(chat_id)
        return jsonify({'ok': True})

    usuario = sesiones[user_id]
    send_message(chat_id, "Consultando... un momento ⏳")
    respuesta = consultar_agente(texto, usuario)
    send_message(chat_id, respuesta)
    return jsonify({'ok': True})

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
