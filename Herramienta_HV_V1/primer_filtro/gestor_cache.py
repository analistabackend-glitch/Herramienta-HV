"""
gestor_cache.py
===============
Gestión de caché para CVs descargados y configuraciones anteriores.
"""

import json
from pathlib import Path
from datetime import datetime

from config import (
    CACHE_DIR,
    CACHE_PDF,
    CACHE_JSON_CV,
    CACHE_JSON_VACANTE,
    CONFIG_CACHE_FILE,
    RESULTS_CACHE_FILE,
)


def cache_existe():
    """
    Verifica si existe caché válido en cualquier nivel:
    - json_cv/  → hay JSONs del segundo filtro (modo F3)
    - pdf/      → hay PDFs descargados (modo F2)
    
    Returns:
        bool: True si hay algo reutilizable en caché.
    """
    tiene_jsons = CACHE_JSON_CV.exists() and bool(list(CACHE_JSON_CV.glob("*.json")))
    tiene_pdfs  = CACHE_PDF.exists() and (
        bool(list(CACHE_PDF.glob("*.pdf"))) or
        bool(list(CACHE_PDF.glob("*.docx")))
    )
    return tiene_jsons or tiene_pdfs


def guardar_en_cache(tipo, id_candidato, datos):
    """
    Guarda datos en caché.
    
    Args:
        tipo: Tipo de datos ('cv', 'vacante').
        id_candidato: ID único del candidato.
        datos: Datos a guardar (dict).
    """
    if tipo == 'cv':
        carpeta = CACHE_JSON_CV
    elif tipo == 'vacante':
        carpeta = CACHE_JSON_VACANTE
    else:
        return
    
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{id_candidato}.json"
    
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def obtener_del_cache(tipo, id_candidato):
    """
    Recupera datos del caché.
    
    Args:
        tipo: Tipo de datos ('cv', 'vacante').
        id_candidato: ID único del candidato.
        
    Returns:
        dict: Datos recuperados, o None si no existe.
    """
    if tipo == 'cv':
        carpeta = CACHE_JSON_CV
    elif tipo == 'vacante':
        carpeta = CACHE_JSON_VACANTE
    else:
        return None
    
    ruta = carpeta / f"{id_candidato}.json"
    
    if not ruta.exists():
        return None
    
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo caché {ruta}: {e}")
        return None


def obtener_config_guardada():
    """
    Obtiene la configuración guardada de la última ejecución.
    
    Returns:
        dict: Configuración, o None si no existe.
    """
    if not CONFIG_CACHE_FILE.exists():
        return None
    
    try:
        with open(CONFIG_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo configuración en caché: {e}")
        return None


def guardar_config(config):
    """
    Guarda la configuración para reutilizar en siguientes ejecuciones.
    
    Args:
        config: Diccionario con la configuración.
    """
    CONFIG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def obtener_archivos_cache(tipo='cv'):
    """
    Obtiene la lista de archivos en caché.
    
    Args:
        tipo: Tipo de caché ('cv', 'vacante', 'pdf').
        
    Returns:
        list: Lista de rutas a archivos en caché.
    """
    if tipo == 'cv':
        carpeta = CACHE_JSON_CV
    elif tipo == 'vacante':
        carpeta = CACHE_JSON_VACANTE
    elif tipo == 'pdf':
        carpeta = CACHE_PDF
    else:
        return []
    
    if not carpeta.exists():
        return []
    
    return list(carpeta.glob("*"))


def invalidar_cache(tipo=None):
    """
    Invalida el caché (borra archivos).
    
    Args:
        tipo: Tipo de caché a invalidar. Si es None, invalida todo.
    """
    import shutil
    
    if tipo is None:
        # Borrar todo el caché
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
    else:
        if tipo == 'cv':
            carpeta = CACHE_JSON_CV
        elif tipo == 'vacante':
            carpeta = CACHE_JSON_VACANTE
        elif tipo == 'pdf':
            carpeta = CACHE_PDF
        else:
            return
        
        if carpeta.exists():
            shutil.rmtree(carpeta)
            carpeta.mkdir(parents=True, exist_ok=True)


def mostrar_info_cache():
    """
    Muestra información sobre el caché actual.
    """
    print("\n" + "="*50)
    print("INFORMACIÓN DEL CACHÉ")
    print("="*50)
    
    # CVs en caché
    cvs = obtener_archivos_cache('cv')
    print(f"CVs en caché: {len(cvs)}")
    
    # PDFs en caché
    pdfs = obtener_archivos_cache('pdf')
    print(f"PDFs en caché: {len(pdfs)}")
    
    # Configuración guardada
    config = obtener_config_guardada()
    if config:
        print(f"\nÚltima configuración:")
        print(f"  Vacante: {config.get('vacante', 'N/A')}")
        print(f"  Edad: {config.get('edad_min', 'N/A')} - {config.get('edad_max', 'N/A')}")
        print(f"  Salario: ${config.get('sal_min', 'N/A'):,} - ${config.get('sal_max', 'N/A'):,}")
    
    print("="*50 + "\n")


def configuracion_cambio(config_nueva):
    """
    Verifica si la configuración cambió respecto a la anterior.
    
    Args:
        config_nueva: Nueva configuración.
        
    Returns:
        tuple: (cambió, motivo)
    """
    config_vieja = obtener_config_guardada()
    
    if not config_vieja:
        return False, "Sin caché anterior"
    
    # Campos que invalidan caché si cambian
    campos_criticos = [
        'vacante',
        'url_vacante',
        'edad_min',
        'edad_max',
        'sal_min',
        'sal_max',
        'requiere_sabados',
    ]
    
    for campo in campos_criticos:
        if config_vieja.get(campo) != config_nueva.get(campo):
            return True, f"Campo '{campo}' cambió"
    
    return False, "Configuración igual"


def limpiar_cache_antiguo(dias=7):
    """
    Elimina archivos en caché más antiguos de X días.
    
    Args:
        dias: Antigüedad en días para considerar como obsoleto.
    """
    from datetime import datetime, timedelta
    import time
    
    edad_limite = datetime.now() - timedelta(days=dias)
    contador = 0
    
    for archivo in obtener_archivos_cache('cv'):
        timestamp = datetime.fromtimestamp(archivo.stat().st_mtime)
        if timestamp < edad_limite:
            archivo.unlink()
            contador += 1
    
    if contador > 0:
        print(f"Limpiados {contador} archivos antiguos del caché")


def obtener_estadisticas_cache():
    """
    Obtiene estadísticas del caché.
    
    Returns:
        dict: Estadísticas del caché.
    """
    cvs = obtener_archivos_cache('cv')
    pdfs = obtener_archivos_cache('pdf')
    
    total_bytes_pdf = sum(p.stat().st_size for p in pdfs)
    
    return {
        'num_cvs': len(cvs),
        'num_pdfs': len(pdfs),
        'tamanio_pdfs_mb': round(total_bytes_pdf / (1024 * 1024), 2),
        'tiene_config': obtener_config_guardada() is not None,
    }

def guardar_ruta_ejecucion(carpetas: dict):
    """
    Guarda las rutas de la última ejecución para poder reutilizarlas
    cuando el usuario solo quiere re-ejecutar el tercer filtro con caché.

    carpetas: dict generado por crear_estructura_ejecucion()
    """
    datos = {k: str(v) for k, v in carpetas.items()}
    CONFIG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ruta = CONFIG_CACHE_FILE.parent / "ultima_ejecucion.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def obtener_ruta_ejecucion() -> dict | None:
    """
    Recupera las rutas de la última ejecución.
    Retorna un dict con Paths, o None si no existe o las carpetas ya no existen.
    """
    ruta = CONFIG_CACHE_FILE.parent / "ultima_ejecucion.json"
    if not ruta.exists():
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        carpetas = {k: Path(v) for k, v in datos.items()}
        # Verificar solo que la carpeta raíz exista
        # (las subcarpetas pueden estar en cache_hvs como fallback)
        if "raiz" in carpetas and not carpetas["raiz"].exists():
            return None
        if "intermedios" in carpetas and not carpetas["intermedios"].exists():
            return None
        return carpetas
    except Exception as e:
        print(f"Error leyendo última ejecución: {e}")
        return None

