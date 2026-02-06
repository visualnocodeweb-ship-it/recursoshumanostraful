import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic import BaseModel # Nuevo
import resend # Nuevo
import base64 # Nuevo

app = FastAPI()

# Configurar CORS para permitir que tu frontend de React se conecte
# Ajusta los orígenes según sea necesario para tu aplicación React
origins = [
    "http://localhost",
    "http://localhost:3000",  # El puerto por defecto de React
    "https://frontend-hxrk.onrender.com", # URL del frontend desplegado en Render
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de Google Sheets y Google Drive API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets', # Ahora con permisos de escritura para Sheets
    'https://www.googleapis.com/auth/drive.readonly' # Solo lectura para Drive
]
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), 'service_account.json') # Use absolute path

# --- Autenticación Google Sheets y Google Drive ---
# Leer el archivo JSON de credenciales una sola vez al inicio
try:
    with open(SERVICE_ACCOUNT_FILE, 'r', encoding='utf-8') as f:
        service_account_data = json.load(f)

    # El campo 'private_key' en el JSON viene con '\n' ya escapados como '\\n'
    # La función from_service_account_info espera la clave con '\n' reales.
    service_account_data['private_key'] = service_account_data['private_key'].replace('\\n', '\n')

    creds = service_account.Credentials.from_service_account_info(service_account_data, scopes=SCOPES)
    
except Exception as e:
    # Esta excepción se levantará si hay problemas con las credenciales o el archivo JSON.
    print(f"ERROR CRÍTICO: Fallo en la inicialización de credenciales de Google: {e}")
    # Considerar si quieres que la aplicación se detenga o intente continuar de alguna forma.
    # Para este caso, lanzaremos una excepción HTTP para que FastAPI lo maneje.
    raise HTTPException(status_code=500, detail=f"Error al cargar las credenciales: {e}. Por favor, verifica tu archivo 'service_account.json' y sus permisos.")

# Inicializar servicios de Google Sheets y Google Drive
sheet_service = build('sheets', 'v4', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds) # Nuevo servicio de Drive

# Resend API Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY") # Nuevo: obtener de variable de entorno
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL") # Nuevo: obtener de variable de entorno
resend.api_key = RESEND_API_KEY


# Pydantic model for the request body
class SendPdfEmailRequest(BaseModel):
    pdf_drive_id: str
    recipient_email: str
    subject: str = "Documento adjunto"
    body_text: str = "Adjunto el documento solicitado."
    filename: str = "document.pdf"
    sheet_row_number: int # Nuevo: número de fila en Google Sheet
    sheet_name: str # Nuevo: nombre de la hoja a actualizar (e.g., 'certificado_medico', 'licencia')
    update_column_letter: str # Nuevo: letra de la columna a actualizar (e.g., 'J', 'L')

# TEMPORARY TEST ENDPOINT TO DEBUG BASIC REACHABILITY
@app.get("/")
async def read_root_test():
    return {"message": "Test root endpoint reached successfully!"}

@app.post("/send_pdf_email")
async def send_pdf_email(request: SendPdfEmailRequest):
    try:
        # 1. Fetch PDF content from Google Drive
        request_drive_file = drive_service.files().get_media(fileId=request.pdf_drive_id)
        file_content = request_drive_file.execute()

        # 2. Encode PDF content to Base64
        encoded_file = base64.b64encode(file_content).decode('utf-8')

        # 3. Send email using Resend
        r = resend.Emails.send({
            "from": RESEND_FROM_EMAIL,
            "to": request.recipient_email,
            "subject": request.subject,
            "html": "<p>" + request.body_text.replace('\n', '<br>') + "</p>",
            "attachments": [
                {
                    "filename": request.filename,
                    "content": encoded_file,
                }
            ]
        })


        if r and r.get('id'): # Resend API typically returns an ID on success
            # Update Google Sheet
            spreadsheet_id = "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA" # Hardcoded from get_sheet_data
            range_to_update = f"{request.sheet_name}!{request.update_column_letter}{request.sheet_row_number}" # Dynamic update

            value_input_option = "USER_ENTERED"
            body = {
                'values': [
                    ['Enviado']
                ]
            }

            sheet_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_to_update,
                valueInputOption=value_input_option,
                body=body
            ).execute()

            return {"message": "Email enviado con éxito y hoja actualizada!", "email_id": r.get('id')}
        else:
            raise HTTPException(status_code=500, detail="Error al enviar el email: Respuesta inesperada de Resend.")

    except Exception as e:
        print(f"ERROR: Fallo al enviar el email: {e}")
        raise HTTPException(status_code=500, detail=f"Error al enviar el email: {str(e)}")


@app.get("/pdf/{file_id}")
async def get_pdf_link(file_id: str):
    """
    Redirige al enlace de visualización de un PDF en Google Drive dado su ID.
    """
    try:
        file_metadata = drive_service.files().get(fileId=file_id, fields='webViewLink').execute()
        web_view_link = file_metadata.get('webViewLink')

        if not web_view_link:
            raise HTTPException(status_code=404, detail="No se encontró un enlace de visualización para el archivo PDF o el archivo no es accesible.")
        
        return RedirectResponse(url=web_view_link, status_code=303)
    except Exception as e:
        print(f"ERROR: Fallo al obtener el enlace del PDF de Google Drive para {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al acceder al PDF: {e}. Asegúrate de que el ID es válido y tienes permisos de acceso.")

@app.get("/sheets/data")
async def get_sheet_data(request: Request):
    """
    Lee datos de una hoja de cálculo de Google y añade IDs de archivos de Google Drive para PDFs
    de forma eficiente.
    """
    # Los valores para spreadsheet_id y range_name se pueden pasar como query params
    # o usar estos valores por defecto.
    spreadsheet_id = request.query_params.get("spreadsheet_id", "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA")
    range_name = request.query_params.get("range_name", "certificado_medico!A1:J")
    
    DRIVE_FOLDER_ID = "1-VzmLOGyhuWp9d26VcxOdI1JL8q7c5bG"

    try:
        # 1. Obtener todos los archivos de la carpeta de Google Drive de una sola vez
        query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType = 'application/pdf' and trashed = false"
        drive_response = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        drive_files = drive_response.get('files', [])
        
        # 2. Crear un mapa en memoria (diccionario) para búsqueda rápida: { 'nombre_del_archivo.pdf': 'id_del_archivo' }
        # Se normaliza el nombre a minúsculas para evitar problemas de mayúsculas/minúsculas.
        pdf_name_to_id_map = {file['name'].lower(): file['id'] for file in drive_files}

        # 3. Obtener los datos de la hoja de cálculo
        sheet_result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name).execute()
        
        sheet_values = sheet_result.get('values', [])

        if not sheet_values:
            return {"headers": [], "data": [], "message": "No se encontraron datos en la hoja de cálculo."}
        
        headers = sheet_values[0]
        # Encontrar el índice de la columna 'id' (insensible a mayúsculas)
        try:
            id_column_index = [h.lower() for h in headers].index('id')
        except ValueError:
            # Si no hay columna 'id', no podemos asociar PDFs. Devolver los datos tal cual.
            data_rows = [dict(zip(headers, row)) for row in sheet_values[1:]]
            return {"headers": headers, "data": data_rows}

        # 4. Procesar las filas de la hoja y enriquecer con el ID del PDF desde el mapa
        data_with_drive_ids = []
        for i, row_values in enumerate(sheet_values[1:]): # Start enumerate from 0 for sheet_values[1:]
            sheet_row_number = i + 2 # +1 for header row, +1 for 0-based enumerate
            row_dict = {}
            # Rellenar con None si la fila es más corta que los encabezados
            for j, header in enumerate(headers):
                row_dict[header] = row_values[j] if j < len(row_values) else None

            # Obtener el nombre del PDF de la columna 'id'
            pdf_name_from_sheet = row_values[id_column_index] if id_column_index < len(row_values) else None
            
            pdf_drive_id = None
            if pdf_name_from_sheet:
                # Buscar en el mapa el nombre del archivo (con extensión .pdf y en minúsculas)
                # El nombre en la hoja puede o no tener la extensión, así que probamos ambas.
                lookup_name_with_ext = f"{pdf_name_from_sheet}.pdf".lower()
                lookup_name_as_is = f"{pdf_name_from_sheet}".lower()

                if lookup_name_with_ext in pdf_name_to_id_map:
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_with_ext]
                elif lookup_name_as_is in pdf_name_to_id_map: # Fallback si el nombre ya incluye .pdf
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_as_is]
            
            row_dict['pdf_drive_id'] = pdf_drive_id
            row_dict['sheet_row_number'] = sheet_row_number # Add this line
            data_with_drive_ids.append(row_dict)
        
        return {"headers": headers, "data": data_with_drive_ids}

    except Exception as e:
        print(f"ERROR: Fallo al procesar los datos: {e}")
        # Proporcionar un error más detallado puede ayudar en el desarrollo
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar datos de Google Sheets o Drive: {str(e)}. "
                   "Verifica que las credenciales son válidas, los IDs de hoja/carpeta son correctos "
                   "y la cuenta de servicio tiene acceso."
        )

@app.get("/sheets/licencia-data")
async def get_licencia_sheet_data(request: Request):
    """
    Lee datos de la hoja de cálculo 'licencia' de Google y añade IDs de archivos de Google Drive para PDFs
    de forma eficiente.
    """
    spreadsheet_id = "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA"
    range_name = "licencia!A1:L"
    
    DRIVE_FOLDER_ID = "13QIHa4FES-bXp0rZsc6FNpi3xgfDB7hH" # Nuevo ID de carpeta para licencias

    try:
        # 1. Obtener todos los archivos de la carpeta de Google Drive de una sola vez
        query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType = 'application/pdf' and trashed = false"
        drive_response = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        drive_files = drive_response.get('files', [])
        
        # 2. Crear un mapa en memoria (diccionario) para búsqueda rápida: { 'nombre_del_archivo.pdf': 'id_del_archivo' }
        # Se normaliza el nombre a minúsculas para evitar problemas de mayúsculas/minúsculas.
        pdf_name_to_id_map = {file['name'].lower(): file['id'] for file in drive_files}

        # 3. Obtener los datos de la hoja de cálculo
        sheet_result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name).execute()
        
        sheet_values = sheet_result.get('values', [])

        if not sheet_values:
            return {"headers": [], "data": [], "message": "No se encontraron datos en la hoja de cálculo."}
        
        headers = sheet_values[0]
        # Encontrar el índice de la columna 'id' (insensible a mayúsculas)
        try:
            id_column_index = [h.lower() for h in headers].index('id')
        except ValueError:
            # Si no hay columna 'id', no podemos asociar PDFs. Devolver los datos tal cual.
            data_rows = [dict(zip(headers, row)) for row in sheet_values[1:]]
            return {"headers": headers, "data": data_rows}

        # 4. Procesar las filas de la hoja y enriquecer con el ID del PDF desde el mapa
        data_with_drive_ids = []
        for i, row_values in enumerate(sheet_values[1:]): # Start enumerate from 0 for sheet_values[1:]
            sheet_row_number = i + 2 # +1 for header row, +1 for 0-based enumerate
            row_dict = {}
            # Rellenar con None si la fila es más corta que los encabezados
            for j, header in enumerate(headers):
                row_dict[header] = row_values[j] if j < len(row_values) else None

            # Obtener el nombre del PDF de la columna 'id'
            pdf_name_from_sheet = row_values[id_column_index] if id_column_index < len(row_values) else None
            
            pdf_drive_id = None
            if pdf_name_from_sheet:
                # Buscar en el mapa el nombre del archivo (con extensión .pdf y en minúsculas)
                # El nombre en la hoja puede o no tener la extensión, así que probamos ambas.
                lookup_name_with_ext = f"{pdf_name_from_sheet}.pdf".lower()
                lookup_name_as_is = f"{pdf_name_from_sheet}".lower()

                if lookup_name_with_ext in pdf_name_to_id_map:
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_with_ext]
                elif lookup_name_as_is in pdf_name_to_id_map: # Fallback si el nombre ya incluye .pdf
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_as_is]
            
            row_dict['pdf_drive_id'] = pdf_drive_id
            row_dict['sheet_row_number'] = sheet_row_number # Add this line
            data_with_drive_ids.append(row_dict)
        
        return {"headers": headers, "data": data_with_drive_ids}

    except Exception as e:
        print(f"ERROR: Fallo al procesar los datos: {e}")
        # Proporcionar un error más detallado puede ayudar en el desarrollo
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar datos de Google Sheets o Drive: {str(e)}. "
                   "Verifica que las credenciales son válidas, los IDs de hoja/carpeta son correctos "
                   "y la cuenta de servicio tiene acceso."
        )

@app.get("/sheets/formulario-81-d-data")
async def get_formulario_81_d_sheet_data(request: Request):
    """
    Lee datos de la hoja de cálculo '81_inciso_D' de Google y añade IDs de archivos de Google Drive para PDFs
    de forma eficiente.
    """
    spreadsheet_id = "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA"
    range_name = "81_inciso_D!A1:J"
    
    DRIVE_FOLDER_ID = "1QAwBtekeHsHU-6bUjn7ug2QgSElHtC8o" # ID de carpeta para Formulario 81_inciso_D

    try:
        # 1. Obtener todos los archivos de la carpeta de Google Drive de una sola vez
        query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType = 'application/pdf' and trashed = false"
        drive_response = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        drive_files = drive_response.get('files', [])
        
        # 2. Crear un mapa en memoria (diccionario) para búsqueda rápida: { 'nombre_del_archivo.pdf': 'id_del_archivo' }
        # Se normaliza el nombre a minúsculas para evitar problemas de mayúsculas/minúsculas.
        pdf_name_to_id_map = {file['name'].lower(): file['id'] for file in drive_files}

        # 3. Obtener los datos de la hoja de cálculo
        sheet_result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name).execute()
        
        sheet_values = sheet_result.get('values', [])

        if not sheet_values:
            return {"headers": [], "data": [], "message": "No se encontraron datos en la hoja de cálculo."}
        
        headers = sheet_values[0]
        # Encontrar el índice de la columna 'id' (insensible a mayúsculas)
        try:
            id_column_index = [h.lower() for h in headers].index('id')
        except ValueError:
            # Si no hay columna 'id', no podemos asociar PDFs. Devolver los datos tal cual.
            data_rows = [dict(zip(headers, row)) for row in sheet_values[1:]]
            return {"headers": headers, "data": data_rows}

        # 4. Procesar las filas de la hoja y enriquecer con el ID del PDF desde el mapa
        data_with_drive_ids = []
        for i, row_values in enumerate(sheet_values[1:]): # Start enumerate from 0 for sheet_values[1:]
            sheet_row_number = i + 2 # +1 for header row, +1 for 0-based enumerate
            row_dict = {}
            # Rellenar con None si la fila es más corta que los encabezados
            for j, header in enumerate(headers):
                row_dict[header] = row_values[j] if j < len(row_values) else None

            # Obtener el nombre del PDF de la columna 'id'
            pdf_name_from_sheet = row_values[id_column_index] if id_column_index < len(row_values) else None
            
            pdf_drive_id = None
            if pdf_name_from_sheet:
                # Buscar en el mapa el nombre del archivo (con extensión .pdf y en minúsculas)
                # El nombre en la hoja puede o no tener la extensión, así que probamos ambas.
                lookup_name_with_ext = f"{pdf_name_from_sheet}.pdf".lower()
                lookup_name_as_is = f"{pdf_name_from_sheet}".lower()

                if lookup_name_with_ext in pdf_name_to_id_map:
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_with_ext]
                elif lookup_name_as_is in pdf_name_to_id_map: # Fallback si el nombre ya incluye .pdf
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_as_is]
            
            row_dict['pdf_drive_id'] = pdf_drive_id
            row_dict['sheet_row_number'] = sheet_row_number # Add this line
            data_with_drive_ids.append(row_dict)
        
        return {"headers": headers, "data": data_with_drive_ids}

    except Exception as e:
        print(f"ERROR: Fallo al procesar los datos: {e}")
        # Proporcionar un error más detallado puede ayudar en el desarrollo
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar datos de Google Sheets o Drive: {str(e)}. "
                   "Verifica que las credenciales son válidas, los IDs de hoja/carpeta son correctos "
                   "y la cuenta de servicio tiene acceso."
        )

@app.get("/sheets/formulario-81-f-data")
async def get_formulario_81_f_sheet_data(request: Request):
    """
    Lee datos de la hoja de cálculo '81_inciso_F' de Google y añade IDs de archivos de Google Drive para PDFs
    de forma eficiente.
    """
    spreadsheet_id = "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA"
    range_name = "81_inciso_F!A1:J"
    
    DRIVE_FOLDER_ID = "1mi00TEyRbjaOosGwyFjsSo-OrFRGcF9d" # ID de carpeta para Formulario 81_inciso_F

    try:
        # 1. Obtener todos los archivos de la carpeta de Google Drive de una sola vez
        query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType = 'application/pdf' and trashed = false"
        drive_response = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        drive_files = drive_response.get('files', [])
        
        # 2. Crear un mapa en memoria (diccionario) para búsqueda rápida: { 'nombre_del_archivo.pdf': 'id_del_archivo' }
        # Se normaliza el nombre a minúsculas para evitar problemas de mayúsculas/minúsculas.
        pdf_name_to_id_map = {file['name'].lower(): file['id'] for file in drive_files}

        # 3. Obtener los datos de la hoja de cálculo
        sheet_result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name).execute()
        
        sheet_values = sheet_result.get('values', [])

        if not sheet_values:
            return {"headers": [], "data": [], "message": "No se encontraron datos en la hoja de cálculo."}
        
        headers = sheet_values[0]
        # Encontrar el índice de la columna 'id' (insensible a mayúsculas)
        try:
            id_column_index = [h.lower() for h in headers].index('id')
        except ValueError:
            # Si no hay columna 'id', no podemos asociar PDFs. Devolver los datos tal cual.
            data_rows = [dict(zip(headers, row)) for row in sheet_values[1:]]
            return {"headers": headers, "data": data_rows}

        # 4. Procesar las filas de la hoja y enriquecer con el ID del PDF desde el mapa
        data_with_drive_ids = []
        for i, row_values in enumerate(sheet_values[1:]): # Start enumerate from 0 for sheet_values[1:]
            sheet_row_number = i + 2 # +1 for header row, +1 for 0-based enumerate
            row_dict = {}
            # Rellenar con None si la fila es más corta que los encabezados
            for j, header in enumerate(headers):
                row_dict[header] = row_values[j] if j < len(row_values) else None

            # Obtener el nombre del PDF de la columna 'id'
            pdf_name_from_sheet = row_values[id_column_index] if id_column_index < len(row_values) else None
            
            pdf_drive_id = None
            if pdf_name_from_sheet:
                # Buscar en el mapa el nombre del archivo (con extensión .pdf y en minúsculas)
                # El nombre en la hoja puede o no tener la extensión, así que probamos ambas.
                lookup_name_with_ext = f"{pdf_name_from_sheet}.pdf".lower()
                lookup_name_as_is = f"{pdf_name_from_sheet}".lower()

                if lookup_name_with_ext in pdf_name_to_id_map:
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_with_ext]
                elif lookup_name_as_is in pdf_name_to_id_map: # Fallback si el nombre ya incluye .pdf
                    pdf_drive_id = pdf_name_to_id_map[lookup_name_as_is]
            
            row_dict['pdf_drive_id'] = pdf_drive_id
            row_dict['sheet_row_number'] = sheet_row_number # Add this line
            data_with_drive_ids.append(row_dict)
        
        return {"headers": headers, "data": data_with_drive_ids}

    except Exception as e:
        print(f"ERROR: Fallo al procesar los datos: {e}")
        # Proporcionar un error más detallado puede ayudar en el desarrollo
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar datos de Google Sheets o Drive: {str(e)}. "
                   "Verifica que las credenciales son válidas, los IDs de hoja/carpeta son correctos "
                   "y la cuenta de servicio tiene acceso."
        )

