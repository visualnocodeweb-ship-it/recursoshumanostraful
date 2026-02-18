
# ... (Previous code remains unchanged until imports)

import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic import BaseModel
import resend
import base64
from apscheduler.schedulers.background import BackgroundScheduler # Nuevo
from sqlalchemy import create_engine, Column, String, DateTime, Integer # Nuevo
from sqlalchemy.ext.declarative import declarative_base # Nuevo
from sqlalchemy.orm import sessionmaker # Nuevo
from datetime import datetime # Nuevo

app = FastAPI()

# --- Configuración de Base de Datos (PostgreSQL) ---
# Usar la variable de entorno DATABASE_URL proporcionada por Render o la específica del usuario si no existe
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://base_datos_tablero_traful_pagina_general_user:bEKhclV6N026s8jNQcBDaH5sou0HZtmA@dpg-d64tk2i4d50c73eoksug-a.oregon-postgres.render.com/base_datos_tablero_traful_pagina_general")

# Fix para SQLAlchemy con URLs de Postgres de Render (postgres:// -> postgresql://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelo para rastrear registros procesados
class ProcessedRecord(Base):
    __tablename__ = "processed_records"

    id = Column(Integer, primary_key=True, index=True)
    sheet_name = Column(String, index=True) # Nombre de la hoja (e.g., 'certificado_medico')
    record_id = Column(String, index=True) # ID único del registro en la hoja (Columna A normalmente)
    processed_at = Column(DateTime, default=datetime.utcnow)

# Crear las tablas en la base de datos si no existen
Base.metadata.create_all(bind=engine)


# ... (Previous code)

# --- Configuración de Emails de Administradores ---
ADMIN_EMAILS = ["rrhhtraful@gmail.com", "comisiondefomentovillatraful@gmail.com", "emanueltula89@gmail.com"]

# ... (Rest of existing code)

# --- Lógica de Notificación Automática a Administradores ---

def get_sheet_all_values(spreadsheet_id, range_name):
    try:
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        return result.get('values', [])
    except Exception as e:
        print(f"Error reading sheet {range_name}: {e}")
        return []

def initialize_db_with_existing_records():
    """
    On first run (if DB is empty), populate it with all existing records from Sheets
    so they are NOT treated as 'new' and don't trigger emails.
    """
    db = SessionLocal()
    try:
        # Check if DB is empty
        count = db.query(ProcessedRecord).count()
        if count > 0:
            print("Base de datos ya inicializada. Saltando carga inicial.")
            return

        print("Base de datos vacía. Cargando registros existentes para evitar notificaciones masivas...")
        
        # Configuración de los hojas a monitorear (MISMA CONFIG QUE ABAJO)
        SPREADSHEET_ID = "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA"
        sheets_config = [
            {"name": "certificado_medico", "range": "certificado_medico!A1:Z"},
            {"name": "licencia", "range": "licencia!A1:Z"},
            {"name": "81_inciso_D", "range": "81_inciso_D!A1:Z"},
            {"name": "81_inciso_F", "range": "81_inciso_F!A1:Z"}
        ]

        records_to_add = []
        for sheet_conf in sheets_config:
            rows = get_sheet_all_values(SPREADSHEET_ID, sheet_conf["range"])
            if not rows: continue

            headers = rows[0]
            try:
                id_idx = [h.lower() for h in headers].index('id')
            except ValueError:
                continue

            for row in rows[1:]:
                if len(row) <= id_idx: continue
                record_id = row[id_idx]
                if not record_id: continue

                # Add to batch
                records_to_add.append(ProcessedRecord(
                    sheet_name=sheet_conf["name"],
                    record_id=record_id,
                    processed_at=datetime.utcnow()
                ))
        
        if records_to_add:
            db.bulk_save_objects(records_to_add)
            db.commit()
            print(f"Inicialización completa: {len(records_to_add)} registros antiguos marcados como procesados.")
        else:
            print("No se encontraron registros antiguos para cargar.")

    except Exception as e:
        print(f"Error durante la inicialización de DB: {e}")
    finally:
        db.close()


def check_and_notify_admins():
    print("Iniciando chequeo de nuevos registros para notificación a administradores...")
    db = SessionLocal()
    try:
        # Configuración de los hojas a monitorear
        # Estructura: (Nombre Hoja, Range para leer todo, Column Index del ID (0-based))
        # Asumiendo que 'id' es siempre la primera columna (índice 0) o buscando por nombre
        SPREADSHEET_ID = "1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA"
        
        sheets_config = [
            {"name": "certificado_medico", "range": "certificado_medico!A1:Z"},
            {"name": "licencia", "range": "licencia!A1:Z"},
            {"name": "81_inciso_D", "range": "81_inciso_D!A1:Z"},
            {"name": "81_inciso_F", "range": "81_inciso_F!A1:Z"}
        ]

        for sheet_conf in sheets_config:
            rows = get_sheet_all_values(SPREADSHEET_ID, sheet_conf["range"])
            if not rows:
                continue

            headers = rows[0]
            # Encontrar índice de columna 'id'
            try:
                id_idx = [h.lower() for h in headers].index('id')
            except ValueError:
                print(f"No se encontró columna 'id' en {sheet_conf['name']}, saltando.")
                continue

            # Encontrar otros índices útiles para el email (Nombre, Apellido, Fecha)
            # Adaptar nombres según la hoja si varían mucho
            try:
                name_idx = next(i for i, h in enumerate(headers) if h.lower() in ['nombre', 'name'])
                surname_idx = next(i for i, h in enumerate(headers) if h.lower() in ['apellido', 'surname', 'legajo'])
            except StopIteration:
                 # Si no encuentra nombres, usa índices genéricos o salta
                 name_idx, surname_idx = -1, -1

            for row in rows[1:]: # Saltar encabezado
                if len(row) <= id_idx: continue
                
                record_id = row[id_idx]
                if not record_id: continue # ID vacío
                
                # Chequear en DB si ya fue procesado
                exists = db.query(ProcessedRecord).filter_by(
                    sheet_name=sheet_conf["name"], 
                    record_id=record_id
                ).first()

                if not exists:
                    # Preparar datos para el email
                    nombre = row[name_idx] if name_idx != -1 and len(row) > name_idx else "Desconocido"
                    apellido = row[surname_idx] if surname_idx != -1 and len(row) > surname_idx else ""
                    
                    print(f"Nuevo registro encontrado en {sheet_conf['name']}: {record_id} ({nombre} {apellido}). Enviando notificación...")

                    # Enviar Email a Administradores
                    try:
                        r = resend.Emails.send({
                            "from": RESEND_FROM_EMAIL,
                            "to": ADMIN_EMAILS,
                            "subject": f"Nuevo Registro en {sheet_conf['name']}: {nombre} {apellido}",
                            "html": f"""
                                <h3>Nuevo Registro Detectado</h3>
                                <p><strong>Hoja:</strong> {sheet_conf['name']}</p>
                                <p><strong>ID Registro:</strong> {record_id}</p>
                                <p><strong>Nombre:</strong> {nombre} {apellido}</p>
                                <hr>
                                <p>Este es un mensaje automático del sistema de Recursos Humanos Traful.</p>
                            """
                        })
                        if r and r.get('id'):
                            # Marcar como procesado en DB
                            new_record = ProcessedRecord(
                                sheet_name=sheet_conf["name"],
                                record_id=record_id
                            )
                            db.add(new_record)
                            db.commit()
                            print(f"Notificación enviada y registro guardado: {record_id}")
                    except Exception as e:
                        print(f"Error enviando email admin para {record_id}: {e}")

    except Exception as e:
        print(f"Error en tarea programada: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


# Iniciar el Scheduler al arrancar
@app.on_event("startup")
def start_scheduler():
    # 1. Start Scheduler
    scheduler = BackgroundScheduler()
    # Ejecutar cada 5 minutos
    scheduler.add_job(check_and_notify_admins, 'interval', minutes=5)
    scheduler.start()
    print("Scheduler de notificaciones iniciado (cada 5 minutos).")
    
    # 2. Initialize DB to prevent spam on first run
    initialize_db_with_existing_records()


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

