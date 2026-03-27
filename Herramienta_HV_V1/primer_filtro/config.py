"""
config.py
========
Configuración general y variables globales del sistema.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde la carpeta del proyecto (sube un nivel si hace falta)
_here = Path(__file__).parent
_dotenv = _here / ".env"
if not _dotenv.exists():
    _dotenv = _here.parent / ".env"
load_dotenv(_dotenv)

# ─────────────────────────────────────────
# CREDENCIALES COMPUTRABAJO
# ─────────────────────────────────────────
COMPUTRABAJO_EMAIL    = os.getenv("COMPUTRABAJO_EMAIL")
COMPUTRABAJO_PASSWORD = os.getenv("COMPUTRABAJO_PASSWORD")

if not COMPUTRABAJO_EMAIL or not COMPUTRABAJO_PASSWORD:
    raise EnvironmentError(
        f"Variables de entorno faltantes. Buscando .env en: {_dotenv}\n"
        f"  COMPUTRABAJO_EMAIL:    {'OK' if COMPUTRABAJO_EMAIL    else '❌ no encontrada'}\n"
        f"  COMPUTRABAJO_PASSWORD: {'OK' if COMPUTRABAJO_PASSWORD else '❌ no encontrada'}\n"
        f"Verifica que el archivo .env exista y contenga las dos variables."
    )

# ─────────────────────────────────────────
# DIRECTORIOS BASE
# ─────────────────────────────────────────
BASE_DIR    = Path(__file__).parent

# Caché oculto en AppData — persiste entre ejecuciones, invisible al usuario
_APPDATA    = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HVTool"
CACHE_DIR   = _APPDATA / "cache_hvs"

CACHE_PDF          = CACHE_DIR / "pdf"
CACHE_JSON_CV      = CACHE_DIR / "json_cv"
CACHE_JSON_VACANTE = CACHE_DIR / "json_vacante"

# Carpeta TEMP local — se usa durante el proceso y se borra al subir a Drive
# Vive en %TEMP%/HVTool/ para no ocupar espacio en el proyecto
_TEMP_BASE  = Path(os.environ.get("TEMP", BASE_DIR)) / "HVTool"
EJECUCIONES = _TEMP_BASE / "Ejecuciones"

# Carpeta de ejecución activa — se sobreescribe en main.py al iniciar el proceso
# Aquí se define un valor por defecto para que los imports no fallen
CARPETA_DESCARGA = EJECUCIONES  # placeholder; main.py asigna la ruta real

# Crear carpetas de caché si no existen
for d in [CACHE_PDF, CACHE_JSON_CV, CACHE_JSON_VACANTE]:
    d.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────
# CONFIGURACIÓN SELENIUM
# ─────────────────────────────────────────
CHROME_WINDOW_SIZE = "1920,1080"
CHROME_PAGE_LOAD_TIMEOUT = 20
SELENIUM_WAIT_TIMEOUT = 15

# ─────────────────────────────────────────
# CONFIGURACIÓN DE FILTROS
# ─────────────────────────────────────────
EDAD_MIN_DEFAULT = 20
EDAD_MAX_DEFAULT = 45
PESO_EXP_DEFAULT = 50
PESO_ACA_DEFAULT = 50

# ─────────────────────────────────────────
# CONFIGURACIÓN DE PDF
# ─────────────────────────────────────────
ENCODING_PDF = 'utf-8'
MAX_WORKERS_DESCARGA = 5  # Número de threads para descargar PDFs

# ─────────────────────────────────────────
# ARCHIVOS DE LOG Y CACHE
# ─────────────────────────────────────────
LOG_FILE = "log_filtrador.txt"
CONFIG_CACHE_FILE = CACHE_DIR / "config.json"
RESULTS_CACHE_FILE = CACHE_DIR / "resultados.json"

# ─────────────────────────────────────────
# URLS DE COMPUTRABAJO
# ─────────────────────────────────────────
COMPUTRABAJO_BASE_URL = "https://empresa.co.computrabajo.com"
COMPUTRABAJO_OFFERS_URL = f"{COMPUTRABAJO_BASE_URL}/Company/Offers"
