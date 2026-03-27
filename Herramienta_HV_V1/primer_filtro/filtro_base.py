"""
filtro_base.py
==============
Funciones para aplicar filtros básicos: edad, salario, experiencia, etc.
"""

import re
from datetime import datetime


def _num_col(texto):
    """
    Extrae un número de una cadena que contiene texto.
    
    Args:
        texto: Cadena que contiene un número.
        
    Returns:
        float: Número extraído, o None si no hay número.
    """
    texto = re.sub(r"[^\d.,]", "", texto.strip().replace(" ", ""))
    if not texto:
        return None
    
    # Detectar si usa coma o punto como separador decimal
    if texto.count(",") == 1 and texto.count(".") == 0:
        # Formato: 1,5 → 1.5
        return float(texto.replace(",", "."))
    elif texto.count(".") == 1 and texto.count(",") == 0:
        # Formato: 1.5 → 1.5 (ya está bien)
        return float(texto)
    elif texto.count(",") > 1 and texto.count(".") == 0:
        # Formato: 1,000,000 → 1000000
        return float(texto.replace(",", ""))
    elif texto.count(".") > 1 and texto.count(",") == 0:
        # Formato: 1.000.000 → 1000000
        return float(texto.replace(".", ""))
    
    return float(texto)


def filtrar_por_edad(edad_candidato, edad_min, edad_max):
    """
    Filtra un candidato por rango de edad.
    Candidatos sin edad declarada (None) pasan automáticamente.
    """
    if edad_candidato is None:
        return True  # sin dato → pasa
    
    try:
        edad = float(edad_candidato)
        return edad_min <= edad <= edad_max
    except (ValueError, TypeError):
        return True  # no parseable → pasa (beneficio de la duda)


def filtrar_por_salario(salario_candidato, salario_min, salario_max):
    """
    Filtra un candidato por rango salarial.
    Candidatos sin salario declarado (None) pasan automáticamente.
    """
    if salario_candidato is None:
        return True  # sin dato → pasa
    
    try:
        sal = _num_col(str(salario_candidato))
        if sal is None:
            return True  # no parseable → pasa
        return salario_min <= sal <= salario_max
    except (ValueError, TypeError):
        return True  # error de parseo → pasa


def filtrar_por_disponibilidad_sabados(disponible_sabados, requiere_sabados):
    """
    Filtra un candidato por disponibilidad de sábados.
    
    Args:
        disponible_sabados: True si el candidato está disponible los sábados.
        requiere_sabados: True si la vacante requiere disponibilidad de sábados.
        
    Returns:
        bool: True si el candidato pasa el filtro.
    """
    if requiere_sabados:
        return disponible_sabados is True
    return True


def filtrar_por_palabras_clave(texto_cv, palabras_clave):
    """
    Filtra un candidato por presencia de palabras clave en el CV.
    
    Args:
        texto_cv: Texto completo del CV del candidato.
        palabras_clave: String con palabras clave separadas por comas.
        
    Returns:
        bool: True si el candidato contiene al menos una palabra clave.
    """
    if not palabras_clave or not texto_cv:
        return True
    
    palabras = [p.strip().lower() for p in palabras_clave.split(",")]
    texto_lower = texto_cv.lower()
    
    return any(palabra in texto_lower for palabra in palabras)


def filtrar_por_experiencia(anos_experiencia, anos_min, anos_max=None):
    """
    Filtra un candidato por años de experiencia.
    
    Args:
        anos_experiencia: Años de experiencia del candidato.
        anos_min: Años mínimos requeridos.
        anos_max: Años máximos permitidos (None = sin límite).
        
    Returns:
        bool: True si el candidato pasa el filtro.
    """
    if anos_experiencia is None:
        return False
    
    try:
        anos = float(anos_experiencia)
        if anos < anos_min:
            return False
        if anos_max is not None and anos > anos_max:
            return False
        return True
    except (ValueError, TypeError):
        return False


def aplicar_filtros_basicos(candidato, config_filtros):
    """
    Aplica todos los filtros básicos a un candidato.
    
    Args:
        candidato: Diccionario con datos del candidato.
        config_filtros: Diccionario con configuración de filtros:
            - edad_min, edad_max
            - sal_min, sal_max
            - requiere_sabados
            - palabras_clave
            
    Returns:
        tuple: (bool, str) - (pasó filtro, motivo de rechazo si aplica)
    """
    # Filtro de edad
    if not filtrar_por_edad(
        candidato.get('edad'),
        config_filtros.get('edad_min', 20),
        config_filtros.get('edad_max', 45)
    ):
        return False, "Edad fuera de rango"
    
    # Filtro de salario
    if not filtrar_por_salario(
        candidato.get('salario'),
        config_filtros.get('sal_min', 0),
        config_filtros.get('sal_max', float('inf'))
    ):
        return False, "Salario fuera de rango"
    
    # Filtro de sábados
    if not filtrar_por_disponibilidad_sabados(
        candidato.get('disponible_sabados', False),
        config_filtros.get('requiere_sabados', False)
    ):
        return False, "No disponible los sábados"
    
    # Filtro de palabras clave
    if not filtrar_por_palabras_clave(
        candidato.get('texto_cv', ''),
        config_filtros.get('palabras_clave', '')
    ):
        return False, "No contiene palabras clave requeridas"
    
    return True, ""
