"""
main.py
=======
Módulo principal — Orquestación del proceso de filtrado completo.

Estructura de carpetas generada por ejecución:
─────────────────────────────────────────────
📁 Ejecuciones/
└── 📁 <vacante>_<dd-mm-aa>_<hh-mm>/
    ├── 
    ├── 📁 Archivos intermedios - <vacante>_<dd-mm-aa>_<hh-mm>/
    │   ├── 📁 Primer Filtro/        ← PDFs de aprobados
    │   ├── 📁 Segundo Filtro/       ← JSONs (uso futuro)
    │   └── 📁 Tercer Filtro/        ← JSONs (uso futuro)
    |   └──📄 log.txt
        └──📄 Descripción <vacante>.JSON
    └── 📁 Resultados - <vacante>_<dd-mm-aa>_<hh-mm>/
        ├── 📁 Descartados/
        ├── 📁 Opcionales/
        ├── 📁 Probablemente Opcionados/
        └── 📄 Resumen Resultados <vacante>.xsl
"""

import os
import re
import threading
from datetime import datetime
from pathlib import Path
import sys

import config as _cfg  # importar módulo para poder mutar CARPETA_DESCARGA
from config import EJECUCIONES, CACHE_DIR, CACHE_PDF, CACHE_JSON_CV, LOG_FILE
from selenium_handler import (
    crear_driver, login, extraer_urls,
    extraer_datos_y_filtrar, descargar_hvs_en_paralelo,
)
from filtro_base import aplicar_filtros_basicos
from gestor_cache import guardar_en_cache, obtener_del_cache, guardar_config, guardar_ruta_ejecucion, obtener_ruta_ejecucion
import sys
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "Segundo Filtro"))
from token_tracker import reporte, reset

reset()

# ══════════════════════════════════════════════════════════════════════════════
#  ESTRUCTURA DE CARPETAS
# ══════════════════════════════════════════════════════════════════════════════

def _slug(texto, max_len=40):
    """Convierte texto en nombre de carpeta seguro."""
    limpio = re.sub(r"[^\w\s-]", "", texto.strip())
    return re.sub(r"\s+", "_", limpio)[:max_len]


def crear_estructura_ejecucion(nombre_vacante):
    """
    Crea la estructura de carpetas para una ejecución y retorna un dict con las rutas.

    📁 Ejecuciones/
    └── 📁 <vacante>_<dd-mm-aa>_<hh-mm>/
        ├── 📄 log.txt
        ├── 📁 Archivos intermedios - .../
        │   ├── 📁 Primer Filtro/
        │   ├── 📁 Segundo Filtro/
        │   └── 📁 Tercer Filtro/
        └── 📁 Resultados - .../
            ├── 📁 Descartados/
            ├── 📁 Opcionales/
            ├── 📁 Probablemente Opcionados/
            └── (Resumen se crea al final)
    """
    ts        = datetime.now().strftime("%d-%m-%y_%H-%M")
    slug      = _slug(nombre_vacante)
    nombre_ej = f"{slug}_{ts}"

    raiz         = EJECUCIONES / nombre_ej
    intermedios  = raiz / f"Archivos intermedios - {nombre_ej}"
    resultados   = raiz / f"Resultados - {nombre_ej}"

    carpetas = {
        "raiz":                  raiz,
        "log":                   intermedios / "log.txt",
        "intermedios":           intermedios,
        "primer_filtro":         intermedios / "Primer Filtro",
        "segundo_filtro":        intermedios / "Segundo Filtro",
        "tercer_filtro":         intermedios / "Tercer Filtro",
        "resultados":            resultados,
        "descartados":           resultados / "Descartados",
        "opcionales":            resultados / "Opcionales",
        "prob_opcionados":       resultados / "Probablemente Opcionados",
    }

    for ruta in carpetas.values():
        if ruta.suffix == "":       # solo dirs, no archivos
            ruta.mkdir(parents=True, exist_ok=True)

    return carpetas


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGER
# ══════════════════════════════════════════════════════════════════════════════



class Tee:
    def __init__(self, archivo, consola):
        self.archivo = archivo
        self.consola = consola

    def write(self, mensaje):
        self.consola.write(mensaje)
        self.archivo.write(mensaje)

    def flush(self):
        self.consola.flush()
        self.archivo.flush()


def crear_logger(ruta_log: Path):
    ruta_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        ruta_log.unlink()
    except FileNotFoundError:
        pass

    log_file = open(ruta_log, "a", encoding="utf-8")

    # 🔥 CLAVE: redirige TODO lo que sale en consola
    sys.stdout = Tee(log_file, sys.__stdout__)
    sys.stderr = Tee(log_file, sys.__stderr__)

    def log(mensaje):
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {mensaje}")

    return log


# ══════════════════════════════════════════════════════════════════════════════
#  SCRAPING + FILTRADO + DESCARGA
# ══════════════════════════════════════════════════════════════════════════════

def procesar_candidatos(driver, urls, config_filtros, carpetas, log, callback_progreso):
    """
    Scraping secuencial con el driver principal (sesión garantizada)
    + descarga paralela de HVs con requests al final.

    Flujo:
      1. Visita cada perfil con el driver autenticado → extrae datos y filtra.
      2. Al terminar, descarga todas las HVs aprobadas en paralelo (sin Selenium).

    Returns:
        tuple: (aprobados, rechazados)
    """
    log("\n" + "=" * 60)
    log("FASE 1: SCRAPING SECUENCIAL + DESCARGA PARALELA DE HVs")
    log("=" * 60)

    aprobados  = []
    rechazados = []
    total      = len(urls)

    # ── 1. Scraping secuencial con el driver principal ────────────────────────
    for i, url in enumerate(urls):
        callback_progreso(i, total)
        log(f"\n  [{i+1}/{total}] Procesando candidato...")

        try:
            datos = extraer_datos_y_filtrar(driver, url, config_filtros, log)
            nombre = datos.get("nombre") or f"cand_{i+1}"
            datos["id"] = nombre

            if datos["pasa_filtro"]:
                log(f"  ✅ APROBADO: {nombre}")
                log(f"     {datos.get('motivo_seleccion', '')}")
                guardar_en_cache("cv", re.sub(r"\W+", "_", nombre), datos)
                aprobados.append(datos)
            else:
                log(f"  ❌ RECHAZADO: {nombre}")
                log(f"     {datos.get('motivo_rechazo', '')}")
                rechazados.append((datos, datos.get("motivo_rechazo", "")))

        except Exception as e:
            import traceback
            log(f"  ERROR procesando {url}: {e}")
            log(traceback.format_exc())
            rechazados.append(({"url": url, "id": f"cand_{i+1}"}, f"Error: {e}"))

    # ── 2. Descarga paralela de HVs (requests reutiliza cookies del driver) ───
    log(f"\n  Descargando HVs de {len(aprobados)} aprobados en paralelo...")
    rutas_descargadas = descargar_hvs_en_paralelo(
        driver, aprobados, carpetas["primer_filtro"], log
    )

    # Mapear ruta descargada de vuelta a cada candidato aprobado
    rutas_por_nombre = {Path(r).stem: r for r in rutas_descargadas if r}
    for datos in aprobados:
        nombre_f = re.sub(r"[^\w\s-]", "", datos.get("nombre") or "candidato").strip()[:50]
        ruta = rutas_por_nombre.get(nombre_f)
        datos["ruta_hv"] = str(ruta) if ruta else None
        if not ruta and datos.get("url_pdf"):
            log(f"     [WARN] No se pudo descargar HV de: {datos.get('nombre', 'N/A')}")

    callback_progreso(total, total)
    log(f"\nResumen Fase 1:")
    log(f"  ✅ Aprobados:  {len(aprobados)}")
    log(f"  ❌ Rechazados: {len(rechazados)}")
    log(f"  📄 HVs descargadas: {len(rutas_descargadas)}")
    return aprobados, rechazados


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTE FINAL
# ══════════════════════════════════════════════════════════════════════════════





# ══════════════════════════════════════════════════════════════════════════════
#  SEGUNDO FILTRO (IA - Groq)
# ══════════════════════════════════════════════════════════════════════════════

def correr_segundo_filtro(carpetas, log, callback_progreso_ia):
    """
    Llama al segundo filtro pasando las rutas de la ejecución actual.

    - Input : carpetas["primer_filtro"]   (PDFs aprobados en fase 1)
    - Output: carpetas["segundo_filtro"]  (JSONs parseados por IA)
    """
    base        = Path(__file__).parent
    base_parent = base.parent
    sf = _cargar_modulo("segundo_filtro",
        str(base_parent / "Segundo Filtro"  / "segundo_filtro.py"),
        str(base_parent / "Segundo filtro"  / "segundo_filtro.py"),
        str(base_parent / "Segundo_Filtro"  / "segundo_filtro.py"),
        str(base        / "Segundo filtro"  / "segundo_filtro.py"),
        str(base        / "segundo_filtro.py"),
    )

    carpeta_input  = carpetas["primer_filtro"]
    carpeta_output = carpetas["segundo_filtro"]
    carpeta_output.mkdir(parents=True, exist_ok=True)

    # Inyectar rutas en el módulo
    sf.INPUT  = str(carpeta_input)
    sf.OUTPUT = str(carpeta_output)

    # Conectar barra de progreso de la UI
    sf._progress_ia_cb = callback_progreso_ia
    sf._contador_ia    = 0

    archivos = [
        str(p)
        for p in carpeta_input.iterdir()
        if p.suffix.lower() in (".pdf", ".docx") and not p.name.startswith("~$")
    ]

    if not archivos:
        log("  [WARN] Segundo filtro: no hay PDFs en Primer Filtro para procesar")
        return

    sf._total_ia_para_prog = len(archivos)
    log(f"  Segundo filtro: procesando {len(archivos)} HVs con IA...")

    resultados = sf.procesar_paralelo(archivos, max_workers=sf.MAX_WORKERS)

    ok      = sum(1 for r in resultados if r.get("resultado") == "ok")
    no_hv   = sum(1 for r in resultados if r.get("resultado", "").startswith("no_hv"))
    errores = sum(1 for r in resultados if "error" in r)

    log(f"  Segundo filtro finalizado — ✅ {ok} ok | 🚫 {no_hv} no-HV | ❌ {errores} errores")
    return list(sf.ARCHIVOS_NO_HV)   # para pasarlo al tercer filtro


# ══════════════════════════════════════════════════════════════════════════════
#  TERCER FILTRO (IA - Scoring y clasificación)
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_modulo(nombre, *rutas_candidatas):
    """Carga un módulo Python por ruta absoluta usando importlib."""
    import importlib.util
    ruta = next((p for p in rutas_candidatas if Path(p).exists()), None)
    if ruta is None:
        raise FileNotFoundError(
            f"No se encontró {nombre}.py. Buscado en: {list(rutas_candidatas)}"
        )
    carpeta = str(Path(ruta).parent)
    if carpeta not in sys.path:
        sys.path.insert(0, carpeta)
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def correr_tercer_filtro(carpetas, config_filtros, aprobados_f1, rechazados_f1, no_hv_lista, log, callback_progreso):
    """
    Llama al tercer filtro inyectando todas las rutas y datos de la ejecución actual.

    - Input JSONs : carpetas["segundo_filtro"]   (JSONs del segundo filtro)
    - Input PDFs  : carpetas["primer_filtro"]    (PDFs para copiar a resultados)
    - Output JSON : carpetas["tercer_filtro"]    (JSONs de evaluación por candidato)
    - Output final: carpetas["resultados"]       (HVs clasificadas + Excel)
    - Vacante JSON: carpetas["raiz"] / "descripcion_*.json"
    """
    base        = Path(__file__).parent
    base_parent = base.parent

    tf = _cargar_modulo("tercer_filtro",
        str(base_parent / "Tercer Filtro"  / "tercer_filtro.py"),
        str(base_parent / "Tercer_Filtro"  / "tercer_filtro.py"),
        str(base        / "Tercer Filtro"  / "tercer_filtro.py"),
        str(base        / "tercer_filtro.py"),
    )

    # Inyectar rutas
    tf.DIR_SEGUNDO_FILTRO      = carpetas["segundo_filtro"]
    tf.DIR_TERCER_FILTRO       = carpetas["tercer_filtro"]
    tf.DIR_RESULTADOS          = carpetas["resultados"]
    tf.CARPETA_VACANTE_ACTIVA  = carpetas["intermedios"]   # busca descripcion_*.json aquí
    tf.DIR_PDF_CANDIDATOS      = carpetas["primer_filtro"] # PDFs descargados en Fase 1

    # Inyectar datos del primer filtro para el Excel unificado
    tf.CFG_PRIMER_FILTRO     = config_filtros
    # Construir resumen completo (aprobados + rechazados) con el formato
    # que espera generador_excel_unificado.py (clave "estado")
    resumen_f1 = []
    for c in aprobados_f1:
        resumen_f1.append({
            "estado"           : "SUBIDO" if c.get("ruta_hv") else "SIN PDF",
            "nombre"           : c.get("nombre", c.get("id", "N/A")),
            "edad"             : c.get("edad"),
            "salario"          : c.get("salario"),
            "sabados"          : c.get("sabados"),
            "url"              : c.get("url"),
            "motivo_seleccion" : c.get("motivo_seleccion", ""),
        })
    for c, motivo in (rechazados_f1 or []):
        resumen_f1.append({
            "estado"         : "RECHAZADO",
            "nombre"         : c.get("nombre", c.get("id", "N/A")),
            "edad"           : c.get("edad"),
            "salario"        : c.get("salario"),
            "sabados"        : c.get("sabados"),
            "url"            : c.get("url"),
            "motivo_rechazo" : motivo,
        })
    tf.RESUMEN_PRIMER_FILTRO = resumen_f1
    tf.ARCHIVOS_NO_HV = no_hv_lista

    # Conectar barra de progreso 3 de la UI
    tf._progress_clas_cb      = callback_progreso
    tf._contador_clas         = 0

    jsons = list(carpetas["segundo_filtro"].glob("*.json"))
    tf._total_clas_para_prog  = len(jsons) if jsons else 1

    # Sobreescribir pesos y palabras clave en descripcion_*.json
    # para que tercer_filtro use los valores actuales de la UI, no los del JSON original
    try:
        import json as _json
        desc_files = list(carpetas["intermedios"].glob("descripcion_*.json"))
        if desc_files:
            desc_path = desc_files[0]
            with open(desc_path, encoding="utf-8") as f:
                desc = _json.load(f)
            desc["peso_experiencia_laboral"] = f"{config_filtros.get('peso_exp', 50)} %"
            desc["peso_formacion_academica"] = f"{config_filtros.get('peso_aca', 50)} %"
            desc["palabras_clave"]           = config_filtros.get("palabras_clave", "")
            with open(desc_path, "w", encoding="utf-8") as f:
                _json.dump(desc, f, ensure_ascii=False, indent=2)
            log(f"  Pesos actualizados: exp={desc['peso_experiencia_laboral']} | aca={desc['peso_formacion_academica']}")
            log(f"  Keywords: {desc['palabras_clave'] or '(ninguna)'}")
    except Exception as e:
        log(f"  [WARN] No se pudieron actualizar pesos: {e}")

    log(f"  Tercer filtro: evaluando {len(jsons)} candidatos con IA...")
    log(f"  Módulo cargado: tercer_filtro.py")

    tf.main()

    log("  Tercer filtro finalizado")



# ══════════════════════════════════════════════════════════════════════════════
#  PROCESO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def correr_proceso(config_filtros, ui):
    """Ejecuta el proceso completo de filtrado."""

    # 1. Crear estructura de carpetas para esta ejecución
    carpetas = crear_estructura_ejecucion(config_filtros["vacante"])

    # Exponer la carpeta raíz globalmente para que otros módulos puedan usarla
    _cfg.CARPETA_DESCARGA = carpetas["raiz"]

    log = crear_logger(carpetas["log"])

    try:
        log("\n" + "█" * 60)
        log("INICIANDO PROCESO DE FILTRADO DE CVs")
        log("█" * 60)
        log(f"Vacante    : {config_filtros['vacante']}")
        log(f"Hora inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log(f"Carpeta    : {carpetas['raiz']}")

        # 2. Verificar conexión con Google Drive ANTES de cualquier procesamiento
        log("\nVerificando conexión con Google Drive...")
        try:
            from drive_uploader import _servicio_usuario, _servicio_dev, _buscar_o_crear_carpeta
            from drive_uploader import CARPETA_RAIZ_USUARIO, CARPETA_RAIZ_DEV

            # Drive usuario — abre navegador si no hay token (OAuth)
            srv_usuario = _servicio_usuario()
            _buscar_o_crear_carpeta(srv_usuario, CARPETA_RAIZ_USUARIO)
            log("  ✅ Drive usuario: conectado")

            # Drive DEV — automático con Service Account
            srv_dev = _servicio_dev()
            _buscar_o_crear_carpeta(srv_dev, CARPETA_RAIZ_DEV)
            log("  ✅ Drive DEV: conectado")

        except ImportError:
            log("  [WARN] drive_uploader.py no encontrado — se omitirá la subida a Drive")
        except Exception as e:
            log(f"\n❌ ERROR: No se pudo conectar con Google Drive: {e}")
            log("  Verifica que client_secret.json y service_account.json estén en la carpeta del proyecto.")
            ui.proceso_terminado(False)
            return

        # 3. Guardar config en caché
        guardar_config(config_filtros)

        # 4. Crear driver y hacer login en Computrabajo
        driver = crear_driver()

        try:
            if not login(driver, log):
                ui.proceso_terminado(False)
                return

            # Limpiar json_cv ahora que confirmamos que vamos a correr todo
            try:
                import shutil as _shutil
                if CACHE_JSON_CV.exists():
                    _shutil.rmtree(CACHE_JSON_CV)
                CACHE_JSON_CV.mkdir(parents=True, exist_ok=True)
                log("  Caché json_cv limpiado para esta ejecución")
            except Exception as e:
                log(f"  [WARN] No se pudo limpiar caché json_cv: {e}")

            # 4a. Extraer descripción de la vacante (guarda JSON para el tercer filtro)
            log("\nExtrayendo descripción de la vacante...")
            try:
                from selenium_handler import extraer_descripcion_vacante
                extraer_descripcion_vacante(
                    driver,
                    config_filtros["vacante"],
                    config_filtros["url_vacante"],
                    log,
                    cfg=config_filtros,
                    carpeta_destino=carpetas["intermedios"],  # dentro de Archivos intermedios/
                )
            except Exception as e:
                log(f"  [WARN] No se pudo extraer descripción de vacante: {e}")

            # 4b. Extraer URLs de candidatos
            log("\nExtrayendo URLs de candidatos...")
            urls = extraer_urls(driver, config_filtros["url_vacante"], log)

            if not urls:
                log("ERROR: No se encontraron candidatos")
                ui.proceso_terminado(False)
                return

            # 5. Scraping + filtrado + descarga de HVs
            log(f"\nProcesando {len(urls)} candidatos...")
            aprobados, rechazados = procesar_candidatos(
                driver, urls, config_filtros, carpetas, log,
                ui.actualizar_progreso
            )
            ui.barra1_terminada()

            # 5b. Segundo filtro (IA)
            log("\n" + "=" * 60)
            log("FASE 2: SEGUNDO FILTRO — ANÁLISIS CON IA")
            log("=" * 60)

            no_hv_lista = []
            try:
                no_hv_lista = correr_segundo_filtro(carpetas, log, ui.actualizar_progreso_ia) or []
                ui.barra2_terminada()
            except Exception as e:
                import traceback
                log(f"  [ERROR] Segundo filtro falló: {e}")
                log(traceback.format_exc())
                log("  Continuando sin segundo filtro...")

            # 5c. Tercer filtro (scoring IA + clasificación)
            log("\n" + "=" * 60)
            log("FASE 3: TERCER FILTRO — SCORING Y CLASIFICACIÓN")
            log("=" * 60)
            try:
                correr_tercer_filtro(
                    carpetas, config_filtros, aprobados, rechazados,
                    no_hv_lista, log,
                    ui.actualizar_progreso_clasificacion
                )
                ui.barra3_terminada()
            except Exception as e:
                import traceback
                log(f"  [ERROR] Tercer filtro falló: {e}")
                log(traceback.format_exc())
                log("  Continuando sin tercer filtro...")
                ui.barra3_terminada()

            # Guardar rutas + resumen para reutilización con caché
            guardar_ruta_ejecucion(carpetas)
            from cache_runner import guardar_resumen_f1; guardar_resumen_f1(aprobados, rechazados)

            log("\n" + "█" * 60)
            log("PROCESO COMPLETADO EXITOSAMENTE")
            reporte()
            log("█" * 60)

            # ── Subida a Google Drive ─────────────────────────────────────
            try:
                from drive_uploader import subir_todo
                nombre_ej = carpetas["raiz"].name
                ui.barra4_iniciada()
                resultado_drive = subir_todo(carpetas, nombre_ej, log)
                ui.barra4_terminada(ok=resultado_drive["ok_usuario"])
                if resultado_drive["ok_usuario"]:
                    log(f"📁 Resultados en tu Drive: {resultado_drive['link_usuario']}")
                else:
                    log("⚠️  Resultados NO subidos al Drive del usuario — revisa las credenciales")
            except ImportError:
                log("  [WARN] drive_uploader.py no encontrado — omitiendo subida a Drive")
                log(f"📁 Resultados locales en: {carpetas['resultados']}")
                ui.barra4_terminada(ok=False)
            except Exception as e:
                import traceback as _tb
                log(f"  [WARN] Error en subida a Drive: {e}")
                log(_tb.format_exc())
                log(f"📁 Resultados locales en: {carpetas['resultados']}")
                ui.barra4_terminada(ok=False)

            # ── Limpiar carpeta TEMP ──────────────────────────────────────
            try:
                import shutil as _shutil
                log("  🗑  Eliminando carpeta TEMP...")
                _shutil.rmtree(carpetas["raiz"], ignore_errors=True)
            except Exception as e:
                log(f"  [WARN] No se pudo eliminar TEMP: {e}")

            ui.proceso_terminado(True)

        finally:
            driver.quit()

    except Exception as e:
        import traceback
        log(f"\n❌ ERROR FATAL: {e}")
        log(traceback.format_exc())
        ui.proceso_terminado(False)



def iniciar_proceso_thread(config_filtros, ui):
    """
    Inicia el proceso en un thread separado.
    Decide automáticamente qué flujo ejecutar:
      - _usar_cache=True  → solo Tercer Filtro (via cache_runner)
      - _usar_cache=False → flujo completo desde Fase 1
    """
    usar_cache = config_filtros.pop("_usar_cache", False)

    if usar_cache:
        from cache_runner import correr_proceso_desde_cache
        target = correr_proceso_desde_cache
    else:
        target = correr_proceso

    thread = threading.Thread(
        target=target,
        args=(config_filtros, ui),
        daemon=True
    )
    thread.start()
