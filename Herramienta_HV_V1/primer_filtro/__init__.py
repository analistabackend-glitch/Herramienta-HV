"""
Primer Filtro - Herramienta de filtrado de CVs desde Computrabajo
================================================================

Módulos:
    - config: Configuración y variables globales
    - selenium_handler: Gestión del navegador Selenium
    - pdf_extractor: Extracción y procesamiento de PDFs
    - filtro_base: Filtros básicos (edad, salario, etc)
    - ui: Interfaz gráfica (Tkinter)
    - main: Orquestación del proceso
"""

__version__ = "1.0.0"
__author__ = "Área de Gestión y Desarrollo FERTRAC"

from .config import CARPETA_DESCARGA, CACHE_DIR
from .selenium_handler import crear_driver, login, extraer_urls
from .pdf_extractor import descargar_pdf, extraer_texto_pdf
from .filtro_base import filtrar_por_edad, filtrar_por_salario

__all__ = [
    'CARPETA_DESCARGA',
    'CACHE_DIR',
    'crear_driver',
    'login',
    'extraer_urls',
    'descargar_pdf',
    'extraer_texto_pdf',
    'filtrar_por_edad',
    'filtrar_por_salario',
]
