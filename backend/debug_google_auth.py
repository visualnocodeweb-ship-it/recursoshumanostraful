import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'service_account.json')

print("--- Iniciando script de depuración de autenticación de Google ---")

try:
    print(f"Cargando credenciales desde: {SERVICE_ACCOUNT_FILE}")
    
    with open(SERVICE_ACCOUNT_FILE, 'r', encoding='utf-8') as f:
        service_account_data = json.load(f)

    print(f"Email de la cuenta de servicio: {service_account_data.get('client_email')}")

    service_account_data['private_key'] = service_account_data['private_key'].replace('\\n', '\n')

    creds = service_account.Credentials.from_service_account_info(service_account_data, scopes=SCOPES)
    print("Credenciales cargadas correctamente.")

    print("Construyendo servicio de Google Drive...")
    drive_service = build('drive', 'v3', credentials=creds)
    print("Servicio de Google Drive construido.")

    print("Intentando listar el primer archivo de Google Drive...")
    results = drive_service.files().list(pageSize=1, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        print("No se encontraron archivos en la raíz de Google Drive (o no hay permisos para verlos).")
    else:
        for item in items:
            print(f"Archivo encontrado: {item['name']} (ID: {item['id']})")
    
    print("--- El script de depuración finalizó con ÉXITO. La autenticación parece funcionar. ---")

except HttpError as error:
    print(f"ERROR HTTP: {error}")
    print("--- El script de depuración falló con un error HTTP. ---")
except Exception as e:
    print(f"ERROR GENERAL: {e}")
    print("--- El script de depuración falló con un error general. ---")
