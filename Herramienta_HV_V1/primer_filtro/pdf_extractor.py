"""
pdf_extractor.py
================
Funciones para descargar, extraer texto y procesar archivos PDF.
"""

import re
from pathlib import Path
import pdfplumber

from config import CACHE_PDF, ENCODING_PDF


def extraer_texto_pdf(ruta_pdf):
    """
    Extrae texto completo de un archivo PDF.
    
    Args:
        ruta_pdf: Ruta al archivo PDF.
        
    Returns:
        str: Texto extraído del PDF, o string vacío si hay error.
    """
    try:
        if not Path(ruta_pdf).exists():
            return ""
        
        texto = ""
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                texto += pagina.extract_text() or ""
        
        return texto
    except Exception as e:
        print(f"Error extrayendo PDF {ruta_pdf}: {e}")
        return ""


def extraer_texto_pdf_por_pagina(ruta_pdf):
    """
    Extrae texto de un PDF página por página.
    
    Args:
        ruta_pdf: Ruta al archivo PDF.
        
    Returns:
        list: Lista con el texto de cada página.
    """
    try:
        if not Path(ruta_pdf).exists():
            return []
        
        paginas = []
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                paginas.append(pagina.extract_text() or "")
        
        return paginas
    except Exception as e:
        print(f"Error extrayendo PDF {ruta_pdf}: {e}")
        return []


def guardar_pdf_en_cache(ruta_pdf, nombre_cache):
    """
    Guarda una copia del PDF en la carpeta de caché.
    
    Args:
        ruta_pdf: Ruta del PDF a guardar.
        nombre_cache: Nombre con el que guardar en caché.
        
    Returns:
        Path: Ruta del PDF guardado en caché.
    """
    try:
        ruta_cache = CACHE_PDF / nombre_cache
        import shutil
        shutil.copy2(ruta_pdf, ruta_cache)
        return ruta_cache
    except Exception as e:
        print(f"Error guardando PDF en caché: {e}")
        return None


def limpiar_texto_pdf(texto):
    """
    Limpia y normaliza el texto extraído de un PDF.
    
    Args:
        texto: Texto sin procesar.
        
    Returns:
        str: Texto limpio y normalizado.
    """
    # Remover espacios múltiples y saltos de línea excesivos
    texto = re.sub(r'\s+', ' ', texto)
    # Remover caracteres especiales problemáticos
    texto = re.sub(r'[^\w\s\-\.,:;()ñáéíóú]', '', texto)
    return texto.strip()


def extraer_emails_pdf(texto):
    """
    Extrae direcciones de email del texto.
    
    Args:
        texto: Texto donde buscar emails.
        
    Returns:
        list: Lista de emails encontrados.
    """
    patron = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(patron, texto)


def extraer_telefonos_pdf(texto):
    """
    Extrae números de teléfono del texto.
    
    Args:
        texto: Texto donde buscar teléfonos.
        
    Returns:
        list: Lista de teléfonos encontrados.
    """
    patron = r'\+?[0-9]{1,3}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,9}'
    return re.findall(patron, texto)


def obtener_info_basica_pdf(ruta_pdf):
    """
    Obtiene información básica del PDF (páginas, tamaño, etc).
    
    Args:
        ruta_pdf: Ruta al archivo PDF.
        
    Returns:
        dict: Diccionario con información del PDF.
    """
    try:
        ruta = Path(ruta_pdf)
        if not ruta.exists():
            return {}
        
        with pdfplumber.open(ruta_pdf) as pdf:
            return {
                'num_paginas': len(pdf.pages),
                'tamanio_bytes': ruta.stat().st_size,
                'nombre': ruta.name,
            }
    except Exception as e:
        print(f"Error obteniendo info PDF: {e}")
        return {}
