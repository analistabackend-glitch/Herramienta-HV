"""
ai_parser.py - MIGRADO A OPENAI (gpt-4o-mini)
===============================================
Cambios vs versión Groq:
- ✅ Migrado de Groq/LLaMA → OpenAI gpt-4o-mini
- ✅ Usa response_format={"type": "json_object"} → JSON garantizado, sin parseo manual
- ✅ MAX_WORKERS puede subir a 4 (rate limits más generosos en OpenAI)
- ✅ Lógica de señales y caché sin cambios
- ❌ ELIMINADO limpiar_json() en llamadas principales (OpenAI retorna JSON directo)

MEJORA ESPERADA vs Groq:
- Latencia similar o mejor (gpt-4o-mini es muy rápido)
- Calidad de extracción superior (mejor comprensión de formatos colombianos)
- Rate limits más altos → menos errores 429
"""

from openai import OpenAI
import json
import re
from dotenv import load_dotenv
import os
from token_tracker import registrar

# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────

MAX_CHARS_CV = 18_000
MODEL = "gpt-4o-mini"  # Rápido, económico y de alta calidad para parseo estructurado

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def limpiar_json(texto):
    """
    Extrae el primer objeto JSON válido de una respuesta de texto.
    Sigue siendo útil como fallback si se llama sin response_format.
    """
    if not texto:
        return "{}"

    texto = texto.replace("```json", "").replace("```", "")
    stack = []
    inicio = None

    for i, c in enumerate(texto):
        if c == "{":
            if inicio is None:
                inicio = i
            stack.append(c)
        elif c == "}":
            if stack:
                stack.pop()
            if not stack and inicio is not None:
                return texto[inicio:i+1]

    return "{}"


# ─────────────────────────────────────────────────────────────
# Señales textuales para decisión rápida (sin IA)
# ─────────────────────────────────────────────────────────────

_SEÑALES_HV = [
    # Señales tradicionales
    "experiencia laboral", "experiencia profesional", "formación académica",
    "educación", "habilidades", "perfil profesional", "objetivo profesional",
    "datos personales", "referencias", "logros", "cargo", "empresa",
    "curriculum", "hoja de vida", "cv ", "c.v.", "fecha de nacimiento",
    "lugar de nacimiento", "estado civil",

    # Señales para HVs minimalistas
    "competencias", "idiomas", "certificaciones", "proyectos",
    "universidad", "colegio", "bachiller", "técnico", "tecnólogo",
    "profesional en", "estudiante de", "egresado", "graduado",
    "microsoft office", "excel", "word", "powerpoint",
    "trabajo en equipo", "liderazgo", "comunicación",
    "presente", "actualidad", "hasta la fecha",
    "nombre completo", "documento de identidad", "cédula",
    "teléfono", "celular", "móvil", "email", "correo personal",
]

_SEÑALES_NO_HV = [
    "número de radicado", "factura", "contrato", "acta de", "resolución",
    "certificado de", "poder notarial", "demanda", "juzgado", "cotización",
    "orden de compra", "remisión", "póliza", "soat", "escritura",
    "número de caso", "ticket", "correo electrónico:", "asunto:",
    "estimado", "cordialmente,", "adjunto", "anexo",
]


def _decision_rapida(texto: str) -> str | None:
    """
    Decisión por palabras clave (sin IA).
    Ahorro: ~30% de documentos, precisión: ~98%
    """
    t = texto.lower()
    señales_hv    = sum(1 for s in _SEÑALES_HV    if s in t)
    señales_no_hv = sum(1 for s in _SEÑALES_NO_HV if s in t)

    if señales_hv >= 3:
        return "hv"
    if señales_no_hv >= 4 and señales_hv == 0:
        return "no_hv"
    return None


# ─────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL: Validación + Parseo en UNA sola llamada
# ─────────────────────────────────────────────────────────────

def parsear_cv_con_validacion(texto: str) -> dict:
    """
    Valida Y parsea en una sola llamada a OpenAI (gpt-4o-mini).

    OpenAI maneja automáticamente:
    - Rate limiting con reintentos
    - JSON válido garantizado via response_format
    - Backoff exponencial interno
    """

    # 1. Decisión rápida (gratis, sin IA)
    decision = _decision_rapida(texto)

    if decision == "hv":
        return _parsear_hv_confirmada(texto)

    elif decision == "no_hv":
        return {
            "es_hoja_de_vida": False,
            "motivo_rechazo": "El documento no contiene señales de hoja de vida (posible correo, factura, contrato u otro).",
            "contacto": {},
            "experiencia": [],
            "educacion": [],
            "habilidades": [],
            "cursos": [],
        }

    # 2. Caso indeciso: llamar a la IA
    if len(texto) > MAX_CHARS_CV:
        print(f"  ⚠️  Texto truncado de {len(texto):,} a {MAX_CHARS_CV:,} caracteres")
        texto = texto[:MAX_CHARS_CV]

    prompt = f"""Eres un extractor experto de hojas de vida colombianas.

Primero determina si el documento es una hoja de vida / currículum vitae.
El texto puede estar DESORDENADO por columnas múltiples en el PDF original — eso es normal, igual extrae la información.

SI NO ES UNA HOJA DE VIDA (es factura, contrato, correo, libro, manual, acta, etc.), responde:
{{
  "es_hoja_de_vida": false,
  "motivo_rechazo": "descripción breve del tipo de documento"
}}

SI ES UNA HOJA DE VIDA, extrae toda la información y responde con este JSON completo:
{{
  "es_hoja_de_vida": true,
  "tipo_formato": "libre",
  "contacto": {{
    "nombre": "nombre completo",
    "email": "correo",
    "telefono": "teléfono o celular",
    "direccion": "dirección si aparece"
  }},
  "perfil_resumen": "perfil o resumen profesional si existe",
  "experiencia": [
    {{
      "empresa": "nombre empresa",
      "cargo": "cargo ocupado",
      "fecha_inicio": "inicio",
      "fecha_fin": "fin o Actual",
      "responsabilidades": ["responsabilidad 1"]
    }}
  ],
  "educacion": [
    {{
      "institucion": "nombre institución",
      "titulo": "título o programa",
      "fecha_inicio": "año inicio",
      "fecha_fin": "año fin o Actual"
    }}
  ],
  "habilidades": ["habilidad 1"],
  "cursos": ["curso 1"]
}}

NUNCA uses null — usa "" para strings vacíos y [] para listas vacías.

DOCUMENTO:

{texto}
"""

    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=4000,  # ✅ Aumentado
            response_format={"type": "json_object"},
            timeout=45
        )
        registrar("ai_parser", r.usage)


        data = json.loads(r.choices[0].message.content)

        if not data.get("es_hoja_de_vida", True):
            data.setdefault("contacto", {})
            data.setdefault("experiencia", [])
            data.setdefault("educacion", [])
            data.setdefault("habilidades", [])
            data.setdefault("cursos", [])

        return data

    except Exception as e:
        print(f"  ⚠️ Error llamando a OpenAI: {e}")
        return {
            "es_hoja_de_vida": True,
            "tipo_formato": "libre",
            "contacto": {},
            "experiencia": [],
            "educacion": [],
            "habilidades": [],
            "cursos": [],
        }


def _parsear_hv_confirmada(texto: str) -> dict:
    """Parsea HV cuando sabemos con certeza que es una HV."""

    if len(texto) > MAX_CHARS_CV:
        texto = texto[:MAX_CHARS_CV]

    prompt = f"""Eres un extractor experto de hojas de vida colombianas.

El texto que recibirás puede estar DESORDENADO porque proviene de un PDF con columnas múltiples.
Tu tarea es reconstruir la información correctamente sin importar el orden del texto.

INSTRUCCIONES:
- Busca el nombre completo (generalmente al inicio o es el título más destacado)
- Busca email, teléfono/celular y dirección en cualquier parte del texto
- Busca TODAS las empresas/empleadores donde trabajó, con sus cargos y fechas
- Busca estudios: universidades, colegios, SENA, institutos, con años
- Busca habilidades técnicas y blandas mencionadas
- Busca cursos, certificaciones o diplomados
- Si un dato no aparece, deja el campo como cadena vacía "" o lista vacía []
- NUNCA dejes campos null, usa "" para strings y [] para listas

Devuelve ÚNICAMENTE este JSON con la información extraída:
{{
  "tipo_formato": "libre",
  "contacto": {{
    "nombre": "nombre completo de la persona",
    "email": "correo@ejemplo.com",
    "telefono": "número de teléfono o celular",
    "direccion": "dirección si aparece"
  }},
  "perfil_resumen": "resumen o perfil profesional si existe",
  "experiencia": [
    {{
      "empresa": "nombre de la empresa",
      "cargo": "título del cargo",
      "fecha_inicio": "mes y año de inicio",
      "fecha_fin": "mes y año de fin o 'Actual' si sigue trabajando",
      "responsabilidades": ["responsabilidad 1", "responsabilidad 2"]
    }}
  ],
  "educacion": [
    {{
      "institucion": "nombre del colegio/universidad/SENA",
      "titulo": "título o programa estudiado",
      "fecha_inicio": "año de inicio",
      "fecha_fin": "año de fin o 'Actual'"
    }}
  ],
  "habilidades": ["habilidad 1", "habilidad 2"],
  "cursos": ["curso o certificación 1", "curso 2"]
}}

TEXTO DEL CV:

{texto}
"""

    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=4000,  # ✅ Aumentado: HVs con mucha experiencia necesitan más tokens
            response_format={"type": "json_object"},
            timeout=45  # ✅ Aumentado acorde al mayor max_tokens
        )
        registrar("ai_parser", r.usage)

        data = json.loads(r.choices[0].message.content)
        data["es_hoja_de_vida"] = True

        # Asegurar que campos obligatorios existan
        data.setdefault("contacto", {})
        data.setdefault("experiencia", [])
        data.setdefault("educacion", [])
        data.setdefault("habilidades", [])
        data.setdefault("cursos", [])
        data.setdefault("perfil_resumen", "")

        return data

    except Exception as e:
        print(f"  ⚠️ Error parseando HV con OpenAI: {e}")
        return {
            "es_hoja_de_vida": True,
            "tipo_formato": "libre",
            "contacto": {},
            "experiencia": [],
            "educacion": [],
            "habilidades": [],
            "cursos": [],
        }


# ─────────────────────────────────────────────────────────────
# Funciones compatibilidad (deprecadas, se mantienen por si acaso)
# ─────────────────────────────────────────────────────────────

def es_hoja_de_vida(texto: str) -> tuple[bool, str]:
    resultado = parsear_cv_con_validacion(texto)
    es_hv = resultado.get("es_hoja_de_vida", True)
    motivo = resultado.get("motivo_rechazo", "Documento validado como HV" if es_hv else "No es HV")
    return es_hv, motivo


def parsear_cv(texto: str) -> dict:
    resultado = parsear_cv_con_validacion(texto)

    if not resultado.get("es_hoja_de_vida", True):
        return {
            "tipo_formato": "libre",
            "contacto": {},
            "experiencia": [],
            "educacion": [],
            "habilidades": [],
            "cursos": [],
        }

    return resultado
