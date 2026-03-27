"""
cache_runner.py
===============
Flujo de re-ejecución desde caché — Solo ejecuta el Tercer Filtro
reutilizando los PDFs y JSONs de una ejecución anterior.

Se invoca desde main.py cuando el usuario presiona el botón verde
(campos de filtro bloqueados, solo pesos/keywords modificables).
"""

import json
import shutil
import re
from datetime import datetime
from pathlib import Path
from email_notifier import enviar_correo_exito, enviar_correo_error
from token_tracker import calcular_costo

# ── Helpers de persistencia del resumen F1 ────────────────────────────────────

def guardar_resumen_f1(aprobados: list, rechazados: list):
    """Persiste aprobados y rechazados del primer filtro en cache_hvs/resumen_f1.json."""
    from config import CACHE_DIR
    ruta = CACHE_DIR / "resumen_f1.json"
    datos = {
        "aprobados" : aprobados,
        "rechazados": [{"candidato": c, "motivo": m} for c, m in rechazados],
    }
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] No se pudo guardar resumen F1: {e}")


def cargar_resumen_f1() -> tuple:
    """Carga aprobados y rechazados del primer filtro desde caché.
    Retorna (aprobados: list, rechazados: list[tuple])."""
    from config import CACHE_DIR
    ruta = CACHE_DIR / "resumen_f1.json"
    if not ruta.exists():
        return [], []
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        aprobados  = datos.get("aprobados", [])
        rechazados = [
            (item["candidato"], item["motivo"])
            for item in datos.get("rechazados", [])
        ]
        return aprobados, rechazados
    except Exception as e:
        print(f"[WARN] No se pudo leer resumen F1: {e}")
        return [], []


# ── Detección del modo de caché ───────────────────────────────────────────────

def detectar_modo_cache() -> tuple:
    """
    Detecta automáticamente desde qué fase se puede continuar.

    Retorna (modo, descripcion) donde modo es:
      "f3"   → hay JSONs en json_cv  → saltar F1 y F2, correr solo F3
      "f2"   → hay PDFs en cache_pdf → saltar F1, correr F2 + F3
      "full" → no hay nada en caché  → correr todo desde F1
    """
    from config import CACHE_JSON_CV, CACHE_PDF

    jsons = list(CACHE_JSON_CV.glob("*.json")) if CACHE_JSON_CV.exists() else []
    pdfs  = (list(CACHE_PDF.glob("*.pdf")) + list(CACHE_PDF.glob("*.docx"))) if CACHE_PDF.exists() else []

    if jsons:
        return "f3", f"{len(jsons)} hojas de vida ya analizadas por IA (ejecución anterior)"
    if pdfs:
        return "f2", f"{len(pdfs)} hojas de vida descargadas (ejecución anterior)"
    return "full", "Sin datos en caché — se ejecutará el flujo completo"


# ── Proceso principal desde caché ─────────────────────────────────────────────

def correr_proceso_desde_cache(config_filtros, ui):
    error_ocurrido = False
    error_mensaje = ""
    """
    Ejecuta SOLO el Tercer Filtro reutilizando los datos de la última ejecución.
    Se usa cuando el usuario solo cambia pesos o palabras clave.

    - Crea una nueva carpeta de resultados con timestamp propio.
    - Lee JSONs del segundo filtro desde la ejecución en caché o cache_hvs/json_cv/.
    - Lee PDFs desde la carpeta Primer Filtro de la ejecución en caché.
    - No abre Chrome.
    """
    from token_tracker import reset
    reset()

    from gestor_cache import obtener_ruta_ejecucion, guardar_ruta_ejecucion, guardar_config
    from config import CACHE_JSON_CV
    from main import (
        _slug, crear_logger,
        correr_tercer_filtro,
        crear_estructura_ejecucion,
    )

    # Detectar automáticamente desde qué fase continuar
    modo, descripcion_modo = detectar_modo_cache()
    carpetas_cache = obtener_ruta_ejecucion()

    if modo == "full":
        # Sin nada en caché → flujo completo
        from main import correr_proceso
        correr_proceso(config_filtros, ui)
        return

    if not carpetas_cache:
        # Hay datos en caché (json_cv o pdf) pero falta ultima_ejecucion.json
        # Construir carpetas_cache mínimas desde la config guardada
        from gestor_cache import obtener_config_guardada
        from config import EJECUCIONES, CACHE_JSON_CV, CACHE_PDF
        cfg_guardada = obtener_config_guardada()
        nombre_vacante = cfg_guardada.get("vacante", config_filtros.get("vacante", "vacante")) if cfg_guardada else config_filtros.get("vacante", "vacante")

        # Buscar la ejecución más reciente en Ejecuciones/ para esta vacante
        slug_vac = re.sub(r"[^\w\s-]", "", nombre_vacante.strip()).replace(" ", "_")[:40]
        candidatas = sorted(
            [p for p in EJECUCIONES.iterdir() if p.is_dir() and p.name.startswith(slug_vac)],
            key=lambda p: p.stat().st_mtime, reverse=True
        ) if EJECUCIONES.exists() else []

        if candidatas:
            raiz_found    = candidatas[0]
            intermedios_f = next((d for d in raiz_found.iterdir() if d.is_dir() and "intermedios" in d.name.lower()), None)
            carpetas_cache = {
                "raiz"          : raiz_found,
                "intermedios"   : intermedios_f or raiz_found,
                "primer_filtro" : (intermedios_f / "Primer Filtro") if intermedios_f else CACHE_PDF,
                "segundo_filtro": (intermedios_f / "Segundo Filtro") if intermedios_f else CACHE_JSON_CV,
            }
        else:
            # No hay ejecución anterior — usar directamente los cachés globales
            carpetas_cache = {
                "raiz"          : EJECUCIONES,
                "intermedios"   : EJECUCIONES,
                "primer_filtro" : CACHE_PDF,
                "segundo_filtro": CACHE_JSON_CV,
            }

    # ── Crear nueva carpeta de resultados ─────────────────────────────────────
    ts         = datetime.now().strftime("%d-%m-%y_%H-%M")
    slug       = _slug(config_filtros["vacante"])
    nombre_res = f"{slug}_{ts}"

    from config import EJECUCIONES
    raiz_nueva         = EJECUCIONES / nombre_res
    intermedios_nuevos = raiz_nueva / f"Archivos intermedios - {nombre_res}"
    resultados_nuevos  = raiz_nueva / f"Resultados - {nombre_res}"
    tercer_filtro_nuevo = intermedios_nuevos / "Tercer Filtro"

    for d in [
        intermedios_nuevos / "Primer Filtro",
        intermedios_nuevos / "Segundo Filtro",
        tercer_filtro_nuevo,
        resultados_nuevos / "Descartados",
        resultados_nuevos / "Opcionales",
        resultados_nuevos / "Probablemente Opcionados",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    ruta_log = intermedios_nuevos / "log.txt"
    log = crear_logger(ruta_log)

    modos_texto = {
        "f3": "RE-EVALUACIÓN DESDE CACHÉ (Solo Tercer Filtro)",
        "f2": "RE-EVALUACIÓN DESDE CACHÉ (Segundo + Tercer Filtro)",
    }
    log("\n" + "█" * 60)
    log(modos_texto.get(modo, "RE-EVALUACIÓN DESDE CACHÉ"))
    log("█" * 60)
    log(f"Vacante    : {config_filtros['vacante']}")
    log(f"Hora inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Modo       : {descripcion_modo}")
    log(f"Caché      : {carpetas_cache['raiz']}")
    log(f"Resultados : {resultados_nuevos}")

    guardar_config(config_filtros)

    # ── Resolver carpeta de JSONs del segundo filtro ──────────────────────────
    # Prioridad: carpeta de la ejecución en caché → cache_hvs/json_cv/ global
    carpeta_jsons_sf = carpetas_cache.get("segundo_filtro")
    if not carpeta_jsons_sf or not any(Path(carpeta_jsons_sf).glob("*.json")):
        carpeta_jsons_sf = CACHE_JSON_CV
        log(f"  JSONs F2 desde caché global: {CACHE_JSON_CV}")
        # Deduplicar: si el caché global tiene múltiples versiones del mismo
        # candidato (de ejecuciones anteriores), copiar solo la más reciente
        # a una carpeta temporal limpia
        import unicodedata as _ud
        def _norm_nombre(s):
            s = _ud.normalize("NFD", str(s).lower())
            return "".join(c for c in s if _ud.category(c) != "Mn" and c.isalnum())

        carpeta_sf_limpia = intermedios_nuevos / "Segundo Filtro"
        vistos = {}
        for j in sorted(Path(carpeta_jsons_sf).glob("*.pdf.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            clave = _norm_nombre(j.stem)
            if clave not in vistos:
                vistos[clave] = j
        for j in vistos.values():
            shutil.copy2(j, carpeta_sf_limpia / j.name)
        carpeta_jsons_sf = carpeta_sf_limpia
        log(f"  JSONs F2 deduplicados: {len(vistos)} candidatos únicos")
    else:
        log(f"  JSONs F2 desde ejecución anterior: {carpeta_jsons_sf}")

    # Resolver carpeta de PDFs: ejecución en caché → cache_hvs/pdf/ global
    from config import CACHE_PDF
    carpeta_pdfs = carpetas_cache.get("primer_filtro")
    if not carpeta_pdfs or not any(Path(carpeta_pdfs).glob("*.pdf")) and not any(Path(carpeta_pdfs).glob("*.docx")):
        carpeta_pdfs = CACHE_PDF
        log(f"  PDFs desde caché global: {CACHE_PDF}")
    else:
        log(f"  PDFs desde ejecución anterior: {carpeta_pdfs}")

    carpetas_tf = {
        "raiz"           : raiz_nueva,
        "intermedios"    : intermedios_nuevos,
        "segundo_filtro" : Path(carpeta_jsons_sf),
        "primer_filtro"  : Path(carpeta_pdfs),
        "tercer_filtro"  : tercer_filtro_nuevo,
        "resultados"     : resultados_nuevos,
        "descartados"    : resultados_nuevos / "Descartados",
        "opcionales"     : resultados_nuevos / "Opcionales",
        "prob_opcionados": resultados_nuevos / "Probablemente Opcionados",
        "log"            : ruta_log,
    }

    # ── Copiar descripcion_*.json al nuevo intermedios ────────────────────────
    # Buscar en: 1) intermedios de la ejecución en caché, 2) cache_hvs/json_vacante/
    from config import CACHE_JSON_VACANTE
    desc_encontrada = False

    # Primero buscar en la ejecución anterior
    if carpetas_cache.get("intermedios") and Path(carpetas_cache["intermedios"]).exists():
        for desc_json in Path(carpetas_cache["intermedios"]).glob("descripcion_*.json"):
            shutil.copy2(desc_json, intermedios_nuevos / desc_json.name)
            log(f"  Descripción copiada desde ejecución anterior: {desc_json.name}")
            desc_encontrada = True

    # Fallback: buscar en cache_hvs/json_vacante/
    if not desc_encontrada and CACHE_JSON_VACANTE.exists():
        desc_jsons = sorted(
            CACHE_JSON_VACANTE.glob("descripcion_*.json"),
            key=lambda p: p.stat().st_mtime, reverse=True
        )
        if desc_jsons:
            shutil.copy2(desc_jsons[0], intermedios_nuevos / desc_jsons[0].name)
            log(f"  Descripción copiada desde caché global: {desc_jsons[0].name}")
            desc_encontrada = True

    if not desc_encontrada:
        log("  [WARN] No se encontró descripcion_*.json — el tercer filtro no podrá evaluar")

    # ── Copiar PDFs a Primer Filtro/ (trazabilidad) ───────────────────────────
    carpeta_pf = intermedios_nuevos / "Primer Filtro"
    n_pdfs = 0
    for ext in ("*.pdf", "*.docx"):
        for f in Path(carpeta_pdfs).glob(ext):
            destino = carpeta_pf / f.name

            # ✅ MISMA VALIDACIÓN
            if f.resolve() != destino.resolve():
                shutil.copy2(f, destino)

            n_pdfs += 1
    log(f"  Primer Filtro: {n_pdfs} archivos copiados para trazabilidad")

    # ── Copiar JSONs del segundo filtro a Segundo Filtro/ (trazabilidad) ──────
    carpeta_sf_dest = intermedios_nuevos / "Segundo Filtro"
    n_jsons = 0

    for f in Path(carpeta_jsons_sf).glob("*.json"):
        destino = carpeta_sf_dest / f.name

        # ✅ AQUÍ VA LA SOLUCIÓN
        if f.resolve() != destino.resolve():
            shutil.copy2(f, destino)

        n_jsons += 1

    # Actualizar carpetas_tf para que tercer filtro lea desde las copias locales
    carpetas_tf["primer_filtro"]  = carpeta_pf
    carpetas_tf["segundo_filtro"] = carpeta_sf_dest

    try:
        if modo == "f3":
            # ── Modo F3: saltar F1 y F2 completamente ────────────────────────
            ui.barra1_terminada()
            ui.barra2_terminada()

        elif modo == "f2":
            # ── Modo F2: saltar F1, correr F2 ────────────────────────────────
            ui.barra1_terminada()

            log("\n" + "=" * 60)
            log("FASE 2: SEGUNDO FILTRO — ANÁLISIS CON IA")
            log("=" * 60)
            try:
                from main import correr_segundo_filtro
                no_hv_lista = correr_segundo_filtro(
                    carpetas_tf, log, ui.actualizar_progreso_ia
                ) or []
                ui.barra2_terminada()
            except Exception as e:
                import traceback

                error_ocurrido = True
                error_mensaje += "\n[Segundo filtro]\n" + traceback.format_exc()

                log(f"  [ERROR] Segundo filtro falló: {e}")
                log(traceback.format_exc())
                ui.barra2_terminada()

        log("\n" + "=" * 60)
        log("FASE 3: TERCER FILTRO — SCORING Y CLASIFICACIÓN")
        log("=" * 60)

        aprobados_cache, rechazados_cache = cargar_resumen_f1()

        # Si no hay resumen F1 guardado, reconstruir desde cache_hvs/json_cv
        if not aprobados_cache:
            log("  [WARN] No hay resumen_f1.json — reconstruyendo desde caché...")
            from config import CACHE_JSON_CV
            import json as _json
            for ruta_j in sorted(CACHE_JSON_CV.glob("*.json")):
                try:
                    with open(ruta_j, encoding="utf-8") as f:
                        datos = _json.load(f)
                    if datos.get("nombre") or datos.get("contacto"):
                        aprobados_cache.append(datos)
                except Exception:
                    pass
            log(f"  Reconstruidos {len(aprobados_cache)} candidatos desde caché")

        log(f"  Trabajando con {len(aprobados_cache)} hojas de vida de la ejecución anterior")

        try:
            correr_tercer_filtro(
                carpetas_tf, config_filtros,
                aprobados_cache, rechazados_cache,
                [],
                log,
                ui.actualizar_progreso_clasificacion,
            )
            ui.barra3_terminada()
        except Exception as e:
            import traceback

            error_ocurrido = True
            error_mensaje += "\n[Tercer filtro]\n" + traceback.format_exc()

            log(f"  [ERROR] Tercer filtro falló: {e}")
            log(traceback.format_exc())
            ui.barra3_terminada()

        guardar_ruta_ejecucion(carpetas_tf)

        log("\n" + "█" * 60)
        log("RE-EVALUACIÓN COMPLETADA")
        log("█" * 60)

        # ✅ AGREGAR ESTO:
        from token_tracker import reporte
        reporte(log=log)

        # ── Subida a Google Drive ─────────────────────────────────────────
        try:
            from drive_uploader import subir_todo
            ui.barra4_iniciada()
            resultado_drive = subir_todo(carpetas_tf, nombre_res, log)
            ui.barra4_terminada(ok=resultado_drive["ok_usuario"])
            if resultado_drive["ok_usuario"]:
                log(f"📁 Resultados en tu Drive: {resultado_drive['link_usuario']}")
            else:
                log("⚠️  Resultados NO subidos al Drive del usuario — revisa las credenciales")
        except ImportError:
            log("  [WARN] drive_uploader.py no encontrado — omitiendo subida a Drive")
            log(f"📁 Resultados locales en: {resultados_nuevos}")
            ui.barra4_terminada(ok=False)
        except Exception as e:
            import traceback as _tb

            error_ocurrido = True
            error_mensaje += "\n[Drive]\n" + _tb.format_exc()

            log(f"  [WARN] Error en subida a Drive: {e}")
            log(_tb.format_exc())
            ui.barra4_terminada(ok=False)
        # ── Calcular costo ─────────────────────────────────────────
        costo = calcular_costo()

        # ── Enviar correo (ANTES de borrar TEMP) ───────────────────
        if error_ocurrido:
            enviar_correo_error(
                asunto=f"Auto. Filtrado HV — {config_filtros.get('vacante')} — ⚠️ Error cache",
                mensaje=error_mensaje,
                log=log,
                vacante=config_filtros.get("vacante"),
                fatal=False
            )
        else:
            enviar_correo_exito(
                vacante=config_filtros.get("vacante"),
                costo=costo,
                log=log,
                desde_cache=True,
                modo_cache=modo
            )

        # ── Limpiar carpeta TEMP ───────────────────────────────────
        try:
            import shutil as _sh
            log("  🗑  Eliminando carpeta TEMP...")
            _sh.rmtree(raiz_nueva, ignore_errors=True)
        except Exception as e:
            print(f"  [WARN] No se pudo eliminar TEMP: {e}")

        # ── Finalizar UI ───────────────────────────────────────────
        ui.proceso_terminado(True)
            

    except Exception as e:
        import traceback
        log(f"\n❌ ERROR FATAL: {e}")
        log(traceback.format_exc())
        enviar_correo_error(
            asunto=f"Auto. Filtrado HV — {config_filtros.get('vacante')} — ❌ Error fatal cache",
            mensaje=traceback.format_exc(),
            log=print,
            vacante=config_filtros.get("vacante"),
            fatal=True
        )
        ui.proceso_terminado(False)
