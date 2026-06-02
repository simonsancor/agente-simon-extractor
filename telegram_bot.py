import os
import requests
import time

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
APPS_SCRIPT_URL = os.environ['APPS_SCRIPT_URL']
DIRECTORIO_SHEET_ID = os.environ['DIRECTORIO_SHEET_ID']

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

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
        for row in rows[1:]:  # saltar encabezado
            if len(row) >= 5 and row[0].strip() == str(telefono) and row[4].strip().upper() == 'TRUE':
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

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={'chat_id': chat_id, 'text': text})

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {'timeout': 10, 'offset': offset}
    try:
        resp = requests.get(url, params=params, timeout=15)
        return resp.json()
    except:
        return {'result': []}

def main():
    print("Bot Jarvis Simón iniciado...")
    offset = None
    while True:
        updates = get_updates(offset)
        for update in updates.get('result', []):
            offset = update['update_id'] + 1
            if 'message' not in update:
                continue
            msg = update['message']
            chat_id = msg['chat']['id']
            telefono_raw = msg.get('contact', {}).get('phone_number') or str(msg['from']['id'])
            texto = msg.get('text', '').strip()
            if not texto or texto.startswith('/'):
                if texto == '/start':
                    send_message(chat_id,
                        "Hola! Soy Jarvis, el agente de Simón.\n"
                        "Escribe tu pregunta directamente y te respondo.")
                continue
            # Buscar por número de Telegram (usamos user_id como fallback)
            telefono = str(msg['from']['id'])
            # Intentar obtener número real si compartió contacto
            if 'contact' in msg:
                telefono = msg['contact']['phone_number'].replace('+', '')
            usuario = buscar_usuario(telefono)
            if not usuario:
                send_message(chat_id,
                    "No estás registrado para usar este agente.\n"
                    "Contacta a Simón para solicitar acceso.")
                continue
            send_message(chat_id, "Consultando... un momento ⏳")
            respuesta = consultar_agente(texto, usuario)
            send_message(chat_id, respuesta)
        time.sleep(1)

if __name__ == '__main__':
    main()
