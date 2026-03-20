"""
drive_uploader.py
=================
Sube archivos a dos Google Drives al final de cada ejecución:

  Drive USUARIO  → "Resultados HV/<ejecucion>/"   (OAuth 2.0, login único)
  Drive DEV      → "Intermedios HV/<ejecucion>/"  (Service Account, automático)

Dependencias:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Archivos de credenciales (junto a este módulo):
    client_secret.json      ← OAuth 2.0 (descarga de Google Cloud Console)
    service_account.json    ← Service Account (descarga de Google Cloud Console)

Token del usuario (renovación automática):
    %LOCALAPPDATA%/HVTool/token.json
"""

import os
import mimetypes
from pathlib import Path
from typing import Optional

# ── Rutas de credenciales ──────────────────────────────────────────────────────
_HERE                = Path(__file__).parent
CLIENT_SECRET_PATH   = _HERE / "client_secret.json"
SERVICE_ACCOUNT_PATH = _HERE / "service_account.json"

TOKEN_PATH = (
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HVTool" / "token.json"
)

SCOPES_USER = ["https://www.googleapis.com/auth/drive.file"]
SCOPES_SA   = ["https://www.googleapis.com/auth/drive"]

CARPETA_RAIZ_USUARIO = "Resultados HV"
CARPETA_RAIZ_DEV     = "Intermedios HV"

# ── ID del Shared Drive DEV ────────────────────────────────────────────────────
# Cómo obtener el ID:
#   1. Abre el Shared Drive en drive.google.com
#   2. La URL es: https://drive.google.com/drive/u/0/folders/<SHARED_DRIVE_ID>
#   3. Copia ese ID y pégalo aquí
#SHARED_DRIVE_ID = "17BHSo50UrYb1lUy5UlbiRnIJyohXRG9G"   # ← pega aquí el ID de tu Shared Drive


# ── Construcción de servicios ──────────────────────────────────────────────────

def _servicio_usuario():
    """Servicio Drive autenticado con OAuth 2.0 (abre navegador si no hay token)."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES_USER)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                raise FileNotFoundError(
                    f"No se encontró client_secret.json en:\n  {CLIENT_SECRET_PATH}\n"
                    "Descárgalo desde Google Cloud Console → APIs → Credenciales."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_PATH), SCOPES_USER
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def _servicio_dev():
    """Servicio Drive con Service Account (sin interacción del usuario)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if not SERVICE_ACCOUNT_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró service_account.json en:\n  {SERVICE_ACCOUNT_PATH}\n"
            "Descárgalo desde Google Cloud Console → IAM → Cuentas de servicio."
        )

    creds = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_PATH), scopes=SCOPES_SA
    )
    return build("drive", "v3", credentials=creds)


# ── Helpers de Drive ───────────────────────────────────────────────────────────

def _buscar_o_crear_carpeta(srv, nombre: str, padre_id: Optional[str] = None) -> str:
    q = (
        f"name='{nombre}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )

    if padre_id:
        q += f" and '{padre_id}' in parents"

    res = srv.files().list(
        q=q,
        spaces="drive",
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    hits = res.get("files", [])
    if hits:
        return hits[0]["id"]

    meta = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder"
    }

    if padre_id:
        meta["parents"] = [padre_id]

    return srv.files().create(
        body=meta,
        fields="id",
        supportsAllDrives=True,
    ).execute()["id"]

def _subir_archivo(srv, ruta: Path, carpeta_id: str) -> str:
    """Sube un archivo a la carpeta indicada. Retorna file ID."""
    from googleapiclient.http import MediaFileUpload

    mime  = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
    meta  = {"name": ruta.name, "parents": [carpeta_id]}
    media = MediaFileUpload(str(ruta), mimetype=mime, resumable=True)

    return srv.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()["id"]


def _subir_recursivo(srv, carpeta_local: Path, carpeta_drive_id: str, log=None):
    """Sube recursivamente el contenido de carpeta_local a Drive."""
    
    for item in sorted(carpeta_local.iterdir()):
        
        if item.is_dir():
            # Crear subcarpeta en Drive dentro de la carpeta actual
            sub_id = _buscar_o_crear_carpeta(srv, item.name, carpeta_drive_id)
            
            # Llamada recursiva
            _subir_recursivo(srv, item, sub_id, log)

        elif item.is_file():
            try:
                _subir_archivo(srv, item, carpeta_drive_id)
                
                if log:
                    log(f"    ✓ {item.name}")

            except Exception as e:
                if log:
                    log(f"    ⚠ Error subiendo {item.name}: {e}")


# ── API pública ────────────────────────────────────────────────────────────────

def subir_resultados_usuario(
    carpeta_resultados: Path, nombre_ejecucion: str, log=None
) -> Optional[str]:
    """
    Sube Resultados al Drive del usuario.

    Drive usuario:
      Resultados HV/
      └── <nombre_ejecucion>/
          ├── Descartados/
          ├── Opcionales/
          ├── Probablemente Opcionados/
          └── resumen_completo_*.xlsx

    Retorna el link de la carpeta en Drive, o None si falla.
    """
    if log:
        log("  Subiendo Resultados al Drive del usuario...")
    try:
        srv    = _servicio_usuario()
        raiz   = _buscar_o_crear_carpeta(srv, CARPETA_RAIZ_USUARIO)
        ej_id  = _buscar_o_crear_carpeta(srv, nombre_ejecucion, raiz)
        _subir_recursivo(srv, carpeta_resultados, ej_id, log)
        link = f"https://drive.google.com/drive/folders/{ej_id}"
        if log:
            log(f"  ✅ Resultados en Drive usuario: {link}")
        return link
    except Exception as e:
        if log:
            log(f"  ❌ Error subiendo al Drive usuario: {e}")
        return None


def subir_intermedios_dev(
    carpeta_intermedios: Path, nombre_ejecucion: str, log=None
) -> Optional[str]:

    if log:
        log("  Subiendo Intermedios al Drive DEV...")

    try:
        srv = _servicio_dev()

        # ✅ USAR DIRECTAMENTE EL ID DE LA CARPETA (NO driveId)
        raiz_id = "17BHSo50UrYb1lUy5UlbiRnIJyohXRG9G"

        # Crear carpeta de ejecución dentro de esa carpeta
        ej_id = _buscar_o_crear_carpeta(
            srv,
            nombre_ejecucion,
            padre_id=raiz_id
        )

        # Subir archivos
        _subir_recursivo(srv, carpeta_intermedios, ej_id, log)

        if log:
            log(f"  ✅ Intermedios en Drive DEV (id: {ej_id})")

        return ej_id

    except Exception as e:
        if log:
            log(f"  ❌ Error subiendo al Drive DEV: {e}")
        return None
    
def subir_todo(carpetas: dict, nombre_ejecucion: str, log=None) -> dict:
    """
    Punto de entrada llamado desde main.py al final del proceso.

    Parámetros:
        carpetas:         dict con claves 'resultados' e 'intermedios' (Path)
        nombre_ejecucion: "<vacante>_<dd-mm-aa>_<hh-mm>"

    Retorna:
        {
            "link_usuario": "https://drive.google.com/drive/folders/...",
            "folder_dev":   "<folder_id>",
            "ok_usuario":   True/False,
            "ok_dev":       True/False,
        }
    """
    if log:
        log("\n" + "═" * 60)
        log("SUBIDA A GOOGLE DRIVE")
        log("═" * 60)

    link_usuario = subir_resultados_usuario(
        carpetas["resultados"], nombre_ejecucion, log
    )
    folder_dev = subir_intermedios_dev(
        carpetas["intermedios"], nombre_ejecucion, log
    )

    resultado = {
        "link_usuario": link_usuario,
        "folder_dev"  : folder_dev,
        "ok_usuario"  : link_usuario is not None,
        "ok_dev"      : folder_dev   is not None,
    }

    if log:
        log("\n" + "═" * 60)
        if resultado["ok_usuario"] and resultado["ok_dev"]:
            log("✅ Subida completada en ambos Drives")
        elif resultado["ok_usuario"]:
            log("⚠️  Solo Drive usuario OK — Drive DEV falló")
        elif resultado["ok_dev"]:
            log("⚠️  Solo Drive DEV OK — Drive usuario falló")
        else:
            log("❌ Ambas subidas fallaron — revisa las credenciales")
        log("═" * 60)

    return resultado
