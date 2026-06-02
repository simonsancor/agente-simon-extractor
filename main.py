import os
import io
from flask import Flask, request, jsonify
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)

def get_drive_service():
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive.readonly'])
    return build('drive', 'v3', credentials=credentials)

def export_file_content(file_id, mime_type):
    service = get_drive_service()
    try:
        if mime_type == 'application/vnd.google-apps.document':
            result = service.files().export(fileId=file_id, mimeType='text/plain').execute()
            return result.decode('utf-8')[:4000]
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            result = service.files().export(fileId=file_id, mimeType='text/csv').execute()
            return result.decode('utf-8')[:4000]
        else:
            # Para Excel, Word, PDF — descargar y convertir
            file_meta = service.files().get(fileId=file_id, fields='name,mimeType').execute()
            request_obj = service.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request_obj)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buffer.seek(0)
            
            # Subir de nuevo con conversión a Google Doc
            from googleapiclient.http import MediaIoBaseUpload
            drive_service_rw = build('drive', 'v3', credentials=google.auth.default(
                scopes=['https://www.googleapis.com/auth/drive'])[0])
            
            if 'spreadsheet' in mime_type or 'excel' in mime_type or 'xlsx' in file_meta.get('name',''):
                target_mime = 'application/vnd.google-apps.spreadsheet'
                export_mime = 'text/csv'
            elif 'pdf' in mime_type:
                target_mime = 'application/vnd.google-apps.document'
                export_mime = 'text/plain'
            else:
                target_mime = 'application/vnd.google-apps.document'
                export_mime = 'text/plain'
            
            media = MediaIoBaseUpload(buffer, mimetype=mime_type, resumable=True)
            converted = drive_service_rw.files().create(
                body={'name': 'tmp_' + file_id, 'mimeType': target_mime},
                media_body=media,
                fields='id'
            ).execute()
            
            result = drive_service_rw.files().export(
                fileId=converted['id'], mimeType=export_mime).execute()
            
            drive_service_rw.files().delete(fileId=converted['id']).execute()
            
            return result.decode('utf-8')[:4000]
    except Exception as e:
        return f"Error extrayendo contenido: {str(e)}"

@app.route('/extract', methods=['GET'])
def extract():
    file_id = request.args.get('file_id', '')
    mime_type = request.args.get('mime_type', '')
    if not file_id:
        return jsonify({'error': 'file_id requerido'}), 400
    content = export_file_content(file_id, mime_type)
    return jsonify({'content': content})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
