"""
filtrador_hv_simple.py
======================
Descarga HVs desde Computrabajo y sube a Drive solo los que pasan filtros iniciales.
Sin Claude — version liviana.

Instalar dependencias:
    pip install selenium webdriver-manager google-auth google-auth-oauthlib
                google-api-python-client requests

Configurar:
    1. Editar COMPUTRABAJO_EMAIL y COMPUTRABAJO_PASSWORD
    2. Tener credentials.json de Google Cloud en la misma carpeta
"""

import re, os, time, pickle, threading, tkinter as tk, json, shutil
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path

import requests, pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
'''from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload****'''

# ─────────────────────────────────────────
# CONFIGURACION
"""
filtrador_hv_simple.py
======================
Descarga HVs desde Computrabajo y sube a Drive solo los que pasan filtros iniciales.
Sin Claude — version liviana.

Instalar dependencias:
    pip install selenium webdriver-manager google-auth google-auth-oauthlib
                google-api-python-client requests

Configurar:
    1. Editar COMPUTRABAJO_EMAIL y COMPUTRABAJO_PASSWORD
    2. Tener credentials.json de Google Cloud en la misma carpeta
"""

import re, os, time, pickle, threading, tkinter as tk, json
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path

import requests, pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
'''from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload****'''

# ─────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────
COMPUTRABAJO_EMAIL    = os.getenv("COMPUTRABAJO_EMAIL")
COMPUTRABAJO_PASSWORD = os.getenv("COMPUTRABAJO_PASSWORD")
'''CREDENTIALS_FILE      = "credentials.json"
TOKEN_FILE            = "token.pickle"
DRIVE_ROOT_FOLDER = "DEPTO TECNOLOGIA E INNOVACION/AREA TI E INNOVACION/10. HERRAMIENTA AUTOMATIZACION HV/Descargue de HV de Computrabajo"
# ID directo de la carpeta "Descargue de HV de Computrabajo" en Drive compartido
# Esto evita que el script cree carpetas duplicadas
DRIVE_FOLDER_ID = "1qPcF-IQZrHwhnTq70dtp9QilQWvCth9y"
CARPETA_DESCARGA      = Path("descargas_temp")***'''
CARPETA_DESCARGA = Path("Resultados Primer Filtro") #***


'''# ══════════════════════════════════════════
#  GOOGLE DRIVE
# ══════════════════════════════════════════

def drive_autenticar():
    import pickle as pk
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pk.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, ["https://www.googleapis.com/auth/drive"])
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pk.dump(creds, f)
    return build("drive", "v3", credentials=creds)

def drive_folder(service, nombre, parent_id=None):
    q = f"name='{nombre}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"

    res = service.files().list(
        q=q, fields="files(id, ownedByMe)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        corpora="allDrives"
    ).execute()

    archivos = res.get("files", [])
    if archivos:
        # Preferir carpetas compartidas (ownedByMe=False) sobre las propias
        compartidas = [f for f in archivos if not f.get("ownedByMe", True)]
        return (compartidas[0] if compartidas else archivos[0])["id"]

    # No existe — crearla
    meta = {"name": nombre, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    return service.files().create(
        body=meta, fields="id", supportsAllDrives=True
    ).execute()["id"]

def drive_upload_pdf(service, ruta, folder_id):
    nombre = Path(ruta).name
    media  = MediaFileUpload(str(ruta), mimetype="application/pdf", resumable=True)
    meta   = {"name": nombre, "parents": [folder_id]}
    return service.files().create(
        body=meta, media_body=media, fields="id", supportsAllDrives=True
    ).execute()["id"]

def drive_upload_excel(service, ruta, folder_id):
    nombre = Path(ruta).name
    mime   = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    media  = MediaFileUpload(str(ruta), mimetype=mime, resumable=True)
    meta   = {"name": nombre, "parents": [folder_id]}
    return service.files().create(
        body=meta, media_body=media, fields="id", supportsAllDrives=True
    ).execute()["id"]****'''


# ══════════════════════════════════════════
#  SELENIUM
# ══════════════════════════════════════════

def crear_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_experimental_option("prefs", {"download.default_directory": str(CARPETA_DESCARGA.absolute())})
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def login(driver, log):
    log("Iniciando sesion en Computrabajo...")
    driver.get("https://empresa.co.computrabajo.com/Company/Offers")
    time.sleep(2)
    if "login" in driver.current_url.lower() or "account" in driver.current_url.lower():
        log("  Login requerido...")
        wait = WebDriverWait(driver, 15)
        try:
            campo_user = wait.until(EC.presence_of_element_located((By.ID, "UserName")))
            campo_user.clear()
            campo_user.send_keys(COMPUTRABAJO_EMAIL)
            campo_pass = driver.find_element(By.ID, "fiesta")
            campo_pass.clear()
            campo_pass.send_keys(COMPUTRABAJO_PASSWORD)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']").click()
            wait.until(lambda d: "login" not in d.current_url.lower())
            log("Login exitoso"); return True
        except TimeoutException:
            log("ERROR: Login fallido"); return False
    log("Sesion activa"); return True

def extraer_urls(driver, url_vacante, log):
    log("Obteniendo candidatos...")
    BASE = "https://empresa.co.computrabajo.com"
    SELECTOR = "a[href*='MatchCvDetail'],a[href*='MatchDetail'],a[href*='CvDetail']"
    urls = set(); pagina = 1
    while True:
        log(f"  Pagina {pagina}...")
        # Intentar hasta 3 veces por si la pagina carga lento
        encontrados = False
        for intento in range(3):
            driver.get(url_vacante if pagina == 1 else driver.current_url)
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR))
                )
                encontrados = True
                break
            except TimeoutException:
                log(f"  [WARN] Intento {intento+1}/3 sin candidatos, reintentando...")
                time.sleep(3)
        if not encontrados:
            log("  [WARN] No se detectaron candidatos tras 3 intentos, continuando...")
        time.sleep(1)
        for a in driver.find_elements(By.CSS_SELECTOR, SELECTOR):
            h = a.get_attribute("href")
            if not h: continue
            if h.startswith("/"): h = BASE + h
            urls.add(h)
        try:
            sig = driver.find_element(By.CSS_SELECTOR, "a.next-page,li.next a,.pagination a[rel='next']")
            if "disabled" in (sig.get_attribute("class") or ""): break
            sig.click(); time.sleep(2); pagina += 1
        except NoSuchElementException: break
    log(f"  {len(urls)} candidatos encontrados"); return list(urls)


def _num_col(t):
    t = re.sub(r"[^\d.,]", "", t.strip().replace(" ", ""))
    if not t: return None
    if t.count(".") > 1: t = t.replace(".", "")
    elif t.count(",") > 1: t = t.replace(",", "")
    elif "." in t and "," in t: t = t.replace(".", "").replace(",", "")
    elif "." in t: t = t.replace(".", "")
    elif "," in t: t = t.replace(",", "")
    try:
        v = int(t)
        if v < 1000: v *= 1000000
        elif v < 10000: v *= 1000
        return v
    except: return None

def parsear_salario(texto):
    """Extrae valor numerico de salario colombiano.
    Soporta: valor simple, rango (X a Y), prefijos como 'Aproximadamente'."""
    if not texto: return None
    # Quitar simbolos de moneda pero conservar letras (para detectar "a" del rango)
    limpio = re.sub(r"[$]", "", texto)
    # Extraer grupos numericos (ej: "3.500.000" o "4,000,000")
    grupos = re.findall(r"\d+(?:[.,]\d+)*", limpio)
    if not grupos: return None
    if len(grupos) >= 2:
        # Verificar que sea rango: separado por " a " o " - "
        if re.search(r"\d\s*(?:a|-)\s*\d", limpio, re.IGNORECASE):
            v1, v2 = _num_col(grupos[0]), _num_col(grupos[1])
            if v1 and v2: return min(v1, v2)
            return v1 or v2
    return _num_col(grupos[0])


def extraer_datos_y_filtrar(driver, url, cfg, log):
    """
    Entra al perfil, extrae edad, salario y disponibilidad sabados,
    aplica filtros y retorna dict con resultado.
    """
    driver.get(url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "candidato")))
    time.sleep(1)

    datos = {
        "url": url, "nombre": None, "url_pdf": None,
        "edad": None, "salario": None, "sabados": None,
        "pasa_filtro": False, "motivo_rechazo": None, "motivo_seleccion": None
    }

    # Nombre
    try:
        datos["nombre"] = driver.find_element(By.CSS_SELECTOR, "h1.fwB").text.replace("Hoja de vida de", "").strip()
    except: pass

    # Edad — aparece como "19 anos" o "19 years" en el sidebar
    try:
        texto_pagina = driver.find_element(By.TAG_NAME, "body").text
        m = re.search(r"(\d{1,2})\s*a[nñ]os?", texto_pagina, re.IGNORECASE)
        if m:
            datos["edad"] = int(m.group(1))
    except: pass

    # Preguntas de filtrado — buscar el bloque de preguntas
    try:
        texto_pagina = driver.find_element(By.TAG_NAME, "body").text

        # Buscar salario en preguntas de filtrado
        # Patron: "aspiracion salarial" seguido del valor en la siguiente linea
        m_sal = re.search(
            r"aspiraci[oó]n salarial[^\n]*\n\s*(?:[^\d$\n]*?)([\$\d.,]+(?:\s*a\s*[\$\d.,]+)?)",
            texto_pagina, re.IGNORECASE
        )
        if m_sal:
            datos["salario"] = parsear_salario(m_sal.group(1))

        # Buscar disponibilidad sabados
        m_sab = re.search(
            r"s[aá]bados?\s*\n\s*(\w+)",
            texto_pagina, re.IGNORECASE
        )
        if m_sab:
            respuesta = m_sab.group(1).strip().lower()
            datos["sabados"] = respuesta

    except: pass

    # URL del PDF
    try:
        a = driver.find_element(By.CSS_SELECTOR, "a.js_download_file")
        h = a.get_attribute("href")
        if h and h != "#":
            if h.startswith("/"): h = "https://empresa.co.computrabajo.com" + h
            datos["url_pdf"] = h
    except: pass

    log(f"  Edad: {datos['edad']} | Salario: {datos['salario']} | Sabados: {datos['sabados']}")

    # ── Aplicar filtros ──
    motivos = []

    # Filtro edad
    edad = datos["edad"]
    if edad is None:
        pass  # Si no se detecta, pasa
    elif edad < cfg["edad_min"] or edad > cfg["edad_max"]:
        motivos.append(f"Edad {edad} fuera del rango {cfg['edad_min']}-{cfg['edad_max']}")

    # Filtro salario
    salario = datos["salario"]
    if salario is None:
        pass  # No especifica -> pasa
    elif salario < cfg["sal_min"] or salario > cfg["sal_max"]:
        motivos.append(f"Salario ${salario:,} fuera del rango ${cfg['sal_min']:,}-${cfg['sal_max']:,}")

    # Filtro sabados
    sab = datos["sabados"]
    if cfg["requiere_sabados"] and sab is not None:
        rechazar_sab = sab.lower() in ["no", "no.", "no,", "nop", "nope"]
        if rechazar_sab:
            motivos.append("No disponible los sabados")

    if motivos:
        datos["pasa_filtro"]    = False
        datos["motivo_rechazo"] = " | ".join(motivos)
    else:
        datos["pasa_filtro"] = True
        razones = []
        if edad is None:
            razones.append("Edad no declarada (pasa automáticamente)")
        else:
            razones.append(f"Edad {edad} dentro del rango {cfg['edad_min']}-{cfg['edad_max']}")
        if salario is None:
            razones.append("Salario no declarado (pasa automáticamente)")
        else:
            razones.append(f"Salario ${salario:,} dentro del rango ${cfg['sal_min']:,}-${cfg['sal_max']:,}")
        if cfg["requiere_sabados"]:
            if sab is None:
                razones.append("Disponibilidad sábados no declarada (pasa automáticamente)")
            else:
                razones.append(f"Disponible los sábados ({sab})")
        datos["motivo_seleccion"] = " | ".join(razones)

    return datos


'''def drive_upload_hv(service, ruta, folder_id):
    ruta = Path(ruta)
    ext  = ruta.suffix.lower()
    mime = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    media = MediaFileUpload(str(ruta), mimetype=mime, resumable=True)
    meta  = {"name": ruta.name, "parents": [folder_id]}
    return service.files().create(body=meta, media_body=media, fields="id", supportsAllDrives=True).execute()["id"]***'''

def extraer_descripcion_vacante(driver, nombre_vacante, url_vacante_match, log, cfg=None, carpeta_destino=None):
    """Entra al formulario de la vacante y guarda la descripcion de tareas en JSON."""
    log("Extrayendo descripcion de la vacante...")
    try:
        m = re.search(r"[?&]oi=([A-Fa-f0-9]+)", url_vacante_match)
        if not m:
            log("  [WARN] No se pudo extraer oi de la URL.")
            return None
        oi = m.group(1)
        url_pub = f"https://empresa.co.computrabajo.com/Company/Offers/Publish?oi={oi}"
        driver.get(url_pub)
        time.sleep(4)

        descripcion = None
        # Estrategia A: textarea
        for ta in driver.find_elements(By.TAG_NAME, "textarea"):
            val = (ta.get_attribute("value") or ta.text or "").strip()
            if len(val) > 80:
                descripcion = val; break
        # Estrategia B: contenteditable
        if not descripcion:
            for el in driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true']"):
                val = (el.text or "").strip()
                if len(val) > 80:
                    descripcion = val; break
        # Estrategia C: iframe (TinyMCE / CKEditor)
        if not descripcion:
            for frame in driver.find_elements(By.TAG_NAME, "iframe"):
                try:
                    driver.switch_to.frame(frame)
                    val = (driver.find_element(By.TAG_NAME, "body").text or "").strip()
                    driver.switch_to.default_content()
                    if len(val) > 80:
                        descripcion = val; break
                except Exception:
                    driver.switch_to.default_content()

        if not descripcion:
            log("  [WARN] No se encontro la descripcion de tareas.")
            return None

        resultado = {
            "vacante"                  : nombre_vacante,
            "offer_id"                 : oi,
            "url_formulario"           : url_pub,
            "descripcion_tareas"       : descripcion,
            "peso_experiencia_laboral" : f"{cfg.get('peso_exp', '')} %" if cfg else "",
            "peso_formacion_academica" : f"{cfg.get('peso_aca', '')} %" if cfg else "",
            "palabras_clave"           : cfg.get("palabras_clave", "") if cfg else "",
            "fecha_extraccion"         : datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        nombre_limpio = re.sub(r"[^\w\s-]", "", nombre_vacante).strip().replace(" ", "_")[:60]
        destino_json = carpeta_destino if carpeta_destino else CARPETA_DESCARGA
        destino_json.mkdir(parents=True, exist_ok=True)
        json_path = destino_json / f"descripcion_{nombre_limpio}.json"
        with open(json_path, "w", encoding="utf-8") as _f:
            json.dump(resultado, _f, ensure_ascii=False, indent=2)
        log(f"  Descripcion guardada: {json_path.name}")
        return resultado
    except Exception as e:
        log(f"  [WARN] Error extrayendo descripcion: {e}")
        return None


def descargar_hv(driver, url_hv, nombre, carpeta=None):
    destino_dir = Path(carpeta) if carpeta else CARPETA_DESCARGA
    destino_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for c in driver.get_cookies():
        session.cookies.set(c["name"], c["value"])
    headers = {"User-Agent": driver.execute_script("return navigator.userAgent")}
    r = session.get(url_hv, headers=headers, stream=True, timeout=30)
    if r.status_code != 200:
        return None
    contenido = b"".join(r.iter_content(8192))
    if len(contenido) < 1000:
        return None
    ct = r.headers.get("Content-Type", "").lower()
    if contenido[:4] == b"%PDF":
        ext = ".pdf"
    elif contenido[:2] == b"PK":
        ext = ".docx"
    elif "pdf" in ct:
        ext = ".pdf"
    elif "wordprocessingml" in ct or "msword" in ct or url_hv.lower().endswith(".docx"):
        ext = ".docx"
    else:
        ext = ".pdf"
    ruta = destino_dir / f"{nombre}{ext}"
    with open(ruta, "wb") as f:
        f.write(contenido)
    return ruta


# ══════════════════════════════════════════
#  PROCESO PRINCIPAL
# ══════════════════════════════════════════

def correr_proceso(cfg, log, progress, done,
                   barra1_done=None, progress_ia=None, barra2_done=None,
                   progress_clas=None, barra3_done=None):
    try:
        # ── Carpeta raíz de la ejecución (fecha + hora) ───────────────────
        ts          = datetime.now().strftime("%d-%m-%y_%H-%M")
        nombre_vac  = re.sub(r"[^\w\s-]", "", cfg["vacante"]).strip().replace(" ", "_")[:40]
        sufijo      = f"{nombre_vac}_{ts}"
        raiz        = Path("Ejecuciones") / sufijo

        # Carpeta 1 — Archivos intermedios (para el desarrollador)
        dir_intermedios  = raiz / f"Archivos intermedios - {sufijo}"
        dir_primer       = dir_intermedios / f"Primer Filtro - {sufijo}"
        dir_segundo      = dir_intermedios / f"Segundo Filtro - {sufijo}"
        dir_tercero      = dir_intermedios / f"Tercer Filtro - {sufijo}"

        # Carpeta 2 — Resultados (entregable final)
        dir_resultados   = raiz / f"Resultados - {sufijo}"

        for d in (dir_primer, dir_segundo, dir_tercero,
                  dir_resultados / "Opcionados",
                  dir_resultados / "Probablemente Opcionados",
                  dir_resultados / "Descartados"):
            d.mkdir(parents=True, exist_ok=True)

        import logging
        log_path = dir_intermedios / "log_filtrador.txt"
        logging.basicConfig(
            filename=str(log_path),
            filemode="w",
            level=logging.INFO,
            format="%(asctime)s - %(message)s",
            encoding="utf-8"
        )
        log_original = log
        def log(msg):
            logging.info(msg)
            log_original(msg)

        log(f"Carpeta de ejecución: {raiz}")

        # carpeta_vacante = dir_primer (aquí van las HVs descargadas)
        carpeta_vacante = dir_primer

        driver = crear_driver()
        if not login(driver, log): driver.quit(); done(False); return

        urls  = extraer_urls(driver, cfg["url_vacante"], log)
        total = len(urls)
        if not total:
            log("Sin candidatos. Verifica la URL.")
            driver.quit(); done(False); return

        subidos = 0; rechazados = 0; sin_pdf = 0
        resumen = []

        for i, url in enumerate(urls, 1):
            progress(i, total)
            log(f"\n[{i}/{total}] Procesando...")
            try:
                datos  = extraer_datos_y_filtrar(driver, url, cfg, log)
                nombre = datos.get("nombre") or f"candidato_{i:03d}"
                log(f"  {nombre}")

                if not datos["pasa_filtro"]:
                    log(f"  RECHAZADO — {datos['motivo_rechazo']}")
                    datos["estado"] = "RECHAZADO"
                    rechazados += 1
                    resumen.append(datos); continue

                if not datos.get("url_pdf"):
                    log("  Paso filtros pero sin PDF — omitido")
                    datos["estado"] = "SIN PDF"
                    sin_pdf += 1
                    resumen.append(datos); continue

                nombre_f = re.sub(r"[^\w\s-]", "", nombre).strip().replace(" ", "_")
                ruta = descargar_hv(driver, datos["url_pdf"], nombre_f, carpeta=carpeta_vacante)

                if not ruta:
                    log("  PDF no descargable — omitido")
                    datos["estado"] = "PDF NO DESCARGABLE"
                    sin_pdf += 1
                    resumen.append(datos); continue

                subidos += 1
                datos["estado"] = "SUBIDO"
                datos["motivo"] = datos.get("motivo_seleccion", "")
                log(f"  Guardado localmente: {ruta}")

                resumen.append(datos)
                time.sleep(1.5)

            except Exception as e:
                log(f"  Error: {e}"); continue

        # Extraer descripcion de la vacante (se guarda en dir_primer)
        extraer_descripcion_vacante(driver, cfg["vacante"], cfg["url_vacante"], log, cfg, carpeta_vacante)

        driver.quit()

        log(f"\nListo.")
        log(f"   Total revisados  : {total}")
        log(f"   Subidos          : {subidos}")
        log(f"   Rechazados       : {rechazados}")
        log(f"   Sin PDF          : {sin_pdf}")

        # ── Barra 1 completada ────────────────────────────────────────
        if barra1_done:
            barra1_done()

        # ── Segundo Filtro ────────────────────────────────────────────
        log("\n" + "─" * 50)
        log("Iniciando SEGUNDO FILTRO (análisis IA de CVs)...")
        try:
            import segundo_filtro as sf
            sf.INPUT          = str(carpeta_vacante)
            sf.OUTPUT         = str(dir_segundo)
            sf.ARCHIVOS_NO_HV = []
            _archivos_ia = [
                f for f in os.listdir(str(carpeta_vacante))
                if f.lower().endswith((".pdf", ".docx")) and not f.startswith("~$")
            ]
            _total_ia = len(_archivos_ia) or 1
            sf._progress_ia_cb     = progress_ia
            sf._total_ia_para_prog = _total_ia
            sf.main()
            log("Segundo filtro completado.")
        except Exception as e:
            import traceback
            log(f"  Error en segundo filtro: {e}\n{traceback.format_exc()}")

        # ── Barra 2 completada ────────────────────────────────────────
        if barra2_done:
            barra2_done()

        # ── Tercer Filtro ─────────────────────────────────────────────
        log("\n" + "─" * 50)
        log("Iniciando TERCER FILTRO (scoring y clasificación)...")
        try:
            import tercer_filtro as tf
            tf.CARPETA_VACANTE_ACTIVA  = carpeta_vacante
            tf.DIR_SEGUNDO_FILTRO      = dir_segundo
            tf.DIR_TERCER_FILTRO       = dir_tercero
            tf.DIR_RESULTADOS          = dir_resultados
            tf.CFG_PRIMER_FILTRO       = cfg
            tf.RESUMEN_PRIMER_FILTRO   = resumen
            import segundo_filtro as sf2
            tf.ARCHIVOS_NO_HV = getattr(sf2, "ARCHIVOS_NO_HV", [])
            _archivos_clas = [
                f for f in (os.listdir(str(dir_segundo)) if dir_segundo.exists() else [])
                if f.endswith(".json")
            ]
            tf._progress_clas_cb     = progress_clas
            tf._total_clas_para_prog = len(_archivos_clas) or 1
            tf.main()
            log("Tercer filtro completado.")
        except Exception as e:
            import traceback
            log(f"  Error en tercer filtro: {e}\n{traceback.format_exc()}")

        # ── Barra 3 completada ────────────────────────────────────────
        if barra3_done:
            barra3_done()

        done(True)

    except Exception as e:
        import traceback
        log(f"\nERROR: {e}\n{traceback.format_exc()}")
        done(False)


# ══════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════

# Paleta corporativa
COR_NARANJA   = "#FF9900"
COR_NAR_DARK  = "#CC7A00"
COR_NAR_LIGHT = "#FFF3E0"
COR_BG        = "#FAFAFA"
COR_PANEL     = "#FFFFFF"
COR_BORDE     = "#E0E0E0"
COR_TEXTO     = "#212121"
COR_SUBTEXTO  = "#757575"
COR_SEP       = "#EEEEEE"
COR_HEADER_BG = "#FFFFFF"

class App:
    def __init__(self, root):
        self.root = root
        root.title("Filtrador de Hojas de Vida")
        root.geometry("680x620")
        root.resizable(False, False)
        root.configure(bg=COR_BG)
        self._build()

    def _build(self):
        # ── Header corporativo ──────────────────────────────────────────
        header = tk.Frame(self.root, bg=COR_HEADER_BG,
                          highlightbackground=COR_BORDE, highlightthickness=1)
        header.pack(fill="x")

        # Logo Fertrac (PNG junto al .py; si no existe, muestra texto)
        logo_frame = tk.Frame(header, bg=COR_HEADER_BG, padx=16, pady=10)
        logo_frame.pack(side="left")
        try:
            from PIL import Image, ImageTk
            _img_src = Image.open(Path(__file__).parent / "logo.png")
            ratio = 52 / _img_src.height
            _img_src = _img_src.resize((int(_img_src.width * ratio), 52), Image.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(_img_src)
            tk.Label(logo_frame, image=self._logo_img, bg=COR_HEADER_BG).pack()
        except Exception:
            tk.Label(logo_frame, text="Fertrac",
                     font=("Segoe UI", 14, "bold"),
                     bg=COR_HEADER_BG, fg=COR_NARANJA).pack()

        # Separador vertical
        tk.Frame(header, bg=COR_BORDE, width=1).pack(side="left", fill="y", pady=10)

        # Texto: departamento + nombre del sistema
        info_frame = tk.Frame(header, bg=COR_HEADER_BG, padx=16, pady=12)
        info_frame.pack(side="left", fill="both", expand=True)
        tk.Label(info_frame, text="DEPTO. TECNOLOGÍA E INNOVACIÓN",
                 font=("Segoe UI", 8, "bold"), bg=COR_HEADER_BG,
                 fg=COR_NARANJA).pack(anchor="w")
        tk.Label(info_frame, text="Filtrador de Hojas de Vida  ·  Computrabajo",
                 font=("Segoe UI", 12, "bold"), bg=COR_HEADER_BG,
                 fg=COR_TEXTO).pack(anchor="w")

        # Badge versión
        badge = tk.Frame(header, bg=COR_NARANJA, padx=10, pady=4)
        badge.pack(side="right", padx=18, pady=14)
        tk.Label(badge, text="v1.0", font=("Segoe UI", 8, "bold"),
                 bg=COR_NARANJA, fg="white").pack()

        # ── Cuerpo principal con scroll ─────────────────────────────────
        _outer = tk.Frame(self.root, bg=COR_BG)
        _outer.pack(fill="both", expand=True)

        _canvas = tk.Canvas(_outer, bg=COR_BG, highlightthickness=0)
        _canvas.pack(side="left", fill="both", expand=True)

        _vsb = ttk.Scrollbar(_outer, orient="vertical", command=_canvas.yview)
        _vsb.pack(side="right", fill="y")
        _canvas.configure(yscrollcommand=_vsb.set)

        body = tk.Frame(_canvas, bg=COR_BG, padx=24, pady=12)
        _canvas_win = _canvas.create_window((0, 0), window=body, anchor="nw")

        def _on_body_configure(e):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        def _on_canvas_configure(e):
            _canvas.itemconfig(_canvas_win, width=e.width)
        body.bind("<Configure>", _on_body_configure)
        _canvas.bind("<Configure>", _on_canvas_configure)

        # Scroll con rueda del ratón
        def _on_mousewheel(e):
            _canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        _canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def campo(parent, lbl, default="", w=28, tooltip=None):
            row = tk.Frame(parent, bg=COR_BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=lbl, bg=COR_BG,
                     font=("Segoe UI", 9), fg=COR_TEXTO,
                     width=26, anchor="w").pack(side="left")
            v = tk.StringVar(value=default)
            e = tk.Entry(row, textvariable=v, width=w,
                         font=("Segoe UI", 9),
                         relief="solid", bd=1,
                         highlightthickness=1,
                         highlightbackground=COR_BORDE,
                         highlightcolor=COR_NARANJA)
            e.pack(side="left", ipady=3)
            return v

        def campo_pct(parent, lbl, default="50"):
            """Campo de porcentaje con sufijo %."""
            row = tk.Frame(parent, bg=COR_BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=lbl, bg=COR_BG,
                     font=("Segoe UI", 9), fg=COR_TEXTO,
                     width=26, anchor="w").pack(side="left")
            v = tk.StringVar(value=default)
            e = tk.Entry(row, textvariable=v, width=6,
                         font=("Segoe UI", 9), justify="center",
                         relief="solid", bd=1,
                         highlightthickness=1,
                         highlightbackground=COR_BORDE,
                         highlightcolor=COR_NARANJA)
            e.pack(side="left", ipady=3)
            tk.Label(row, text="%", bg=COR_BG,
                     font=("Segoe UI", 9), fg=COR_SUBTEXTO).pack(side="left", padx=(4, 0))
            return v

        def campo_salario(parent, lbl, default_num):
            """Campo de salario con formato $1.500.000 en pantalla."""
            row = tk.Frame(parent, bg=COR_BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=lbl, bg=COR_BG,
                     font=("Segoe UI", 9), fg=COR_TEXTO,
                     width=26, anchor="w").pack(side="left")
            v = tk.StringVar()

            def _formatear(num_str):
                digits = num_str.replace(".", "").replace(",", "").replace("$", "").strip()
                if digits.isdigit():
                    return f"${int(digits):,.0f}".replace(",", ".")
                return num_str

            def _al_escribir(*_):
                raw = v.get()
                digits = raw.replace(".", "").replace(",", "").replace("$", "").strip()
                if not digits:
                    return
                # Guardar posición del cursor y solo reformatear si son puros dígitos
                if digits.isdigit():
                    formateado = f"${int(digits):,.0f}".replace(",", ".")
                    v.set(formateado)

            v.set(_formatear(str(default_num)))
            e = tk.Entry(row, textvariable=v, width=15,
                         font=("Segoe UI", 9),
                         relief="solid", bd=1,
                         highlightthickness=1,
                         highlightbackground=COR_BORDE,
                         highlightcolor=COR_NARANJA)
            e.pack(side="left", ipady=3)
            v.trace_add("write", _al_escribir)
            return v

        def divider(parent):
            tk.Frame(parent, bg=COR_SEP, height=1).pack(fill="x", pady=(8, 0))

        # ── helpers de layout ──────────────────────────────────────────
        def section_title(parent, texto):
            """Título de sección con línea naranja lateral."""
            row = tk.Frame(parent, bg=COR_BG)
            row.pack(fill="x", pady=(8, 4))
            tk.Frame(row, bg=COR_NARANJA, width=3).pack(side="left", fill="y", padx=(0, 8))
            tk.Label(row, text=texto, font=("Segoe UI", 9, "bold"),
                     bg=COR_BG, fg=COR_TEXTO).pack(side="left", anchor="w")

        # ── Sección: Vacante ────────────────────────────────────────────
        section_title(body, "INFORMACIÓN DE LA VACANTE")
        self.v_vacante = campo(body, "Nombre de la vacante:", "Analista Contable", w=30)
        self.v_url     = campo(body, "URL vacante Computrabajo:", w=30)

        # ── Sección: Filtros iniciales ──────────────────────────────────
        divider(body)
        section_title(body, "FILTROS INICIALES")

        # Edad y salario en dos columnas
        grid = tk.Frame(body, bg=COR_BG)
        grid.pack(fill="x")

        col_izq = tk.Frame(grid, bg=COR_BG)
        col_izq.pack(side="left", fill="both", expand=True)
        col_der = tk.Frame(grid, bg=COR_BG)
        col_der.pack(side="left", fill="both", expand=True)

        self.v_emin = campo(col_izq, "Edad mínima (años):", "20", w=10)
        self.v_smin = campo_salario(col_izq, "Salario mínimo ($):", 1750905)
        self.v_emax = campo(col_der, "Edad máxima (años):", "45", w=10)
        self.v_smax = campo_salario(col_der, "Salario máximo ($):", 3000000)

        row_sab = tk.Frame(body, bg=COR_BG)
        row_sab.pack(fill="x", pady=3)
        tk.Label(row_sab, text="Disponibilidad sábados:", bg=COR_BG,
                 font=("Segoe UI", 9), fg=COR_TEXTO,
                 width=26, anchor="w").pack(side="left")
        self.v_sab = tk.BooleanVar(value=True)
        for txt, val in [("Requerido", True), ("No importa", False)]:
            tk.Radiobutton(row_sab, text=txt, variable=self.v_sab, value=val,
                           bg=COR_BG, font=("Segoe UI", 9),
                           activebackground=COR_BG,
                           selectcolor=COR_NAR_LIGHT,
                           fg=COR_TEXTO).pack(side="left", padx=(0, 12))

        tk.Label(body, text="Candidatos sin salario o sin edad declarada pasan el filtro automáticamente.",
                 bg=COR_BG, fg=COR_SUBTEXTO, font=("Segoe UI", 8, "italic"),
                 wraplength=600, justify="left").pack(anchor="w", pady=(4, 0))

        # ── Sección: Pesos de evaluación ────────────────────────────────
        divider(body)
        section_title(body, "PESOS DE EVALUACIÓN")

        pesos_frame = tk.Frame(body, bg=COR_BG)
        pesos_frame.pack(fill="x")

        col_p1 = tk.Frame(pesos_frame, bg=COR_BG)
        col_p1.pack(side="left", fill="both", expand=True)
        col_p2 = tk.Frame(pesos_frame, bg=COR_BG)
        col_p2.pack(side="left", fill="both", expand=True)

        self.v_peso_exp = campo_pct(col_p1, "Peso experiencia laboral:", "50")
        self.v_peso_aca = campo_pct(col_p2, "Peso formación académica:", "50")

        tk.Label(body, text="La suma de los pesos debe ser 100 %. Se usan para la puntuación ponderada del candidato.",
                 bg=COR_BG, fg=COR_SUBTEXTO, font=("Segoe UI", 8, "italic"),
                 wraplength=600, justify="left").pack(anchor="w", pady=(4, 0))

        # ── Sección: Palabras clave de contexto ─────────────────────────
        divider(body)
        section_title(body, "PALABRAS CLAVE DE CONTEXTO  (opcional)")

        row_kw = tk.Frame(body, bg=COR_BG)
        row_kw.pack(fill="x", pady=(2, 0))
        tk.Label(row_kw, text="Palabras clave:", bg=COR_BG,
                 font=("Segoe UI", 9), fg=COR_TEXTO,
                 width=16, anchor="w").pack(side="left")
        self.v_keywords = tk.StringVar()
        tk.Entry(row_kw, textvariable=self.v_keywords, width=52,
                 font=("Segoe UI", 9),
                 relief="solid", bd=1,
                 highlightthickness=1,
                 highlightbackground=COR_BORDE,
                 highlightcolor=COR_NARANJA).pack(side="left", ipady=3)

        tk.Label(body,
                 text="Separadas por coma (,)  —  Ej: logística, operaciones, supply chain, almacén  ·  Generan bonus en el score.",
                 bg=COR_BG, fg=COR_SUBTEXTO, font=("Segoe UI", 8, "italic"),
                 wraplength=600, justify="left").pack(anchor="w", pady=(2, 0))

        # ── Barra de acción ─────────────────────────────────────────────
        divider(body)

        action_row = tk.Frame(body, bg=COR_BG)
        action_row.pack(fill="x", pady=(10, 4))

        self.btn = tk.Button(action_row,
                             text="  ▶  Iniciar filtrado de HVs",
                             font=("Segoe UI", 10, "bold"),
                             bg=COR_NARANJA, fg="white",
                             activebackground=COR_NAR_DARK,
                             activeforeground="white",
                             relief="flat", bd=0,
                             padx=24, pady=9,
                             cursor="hand2",
                             command=self.iniciar)
        self.btn.pack(side="left")

        # ── Barras de progreso ──────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Corp.Horizontal.TProgressbar",
                         troughcolor=COR_SEP,
                         background=COR_NARANJA,
                         thickness=8)

        barras_frame = tk.Frame(body, bg=COR_BG)
        barras_frame.pack(fill="x", pady=(8, 0))

        # — Barra 1: Descargando hojas de vida —
        fila1 = tk.Frame(barras_frame, bg=COR_BG)
        fila1.pack(fill="x", pady=(0, 2))
        self.lbl_barra1 = tk.Label(fila1, text="Descargando hojas de vida",
                                   bg=COR_BG, font=("Segoe UI", 9, "bold"),
                                   fg=COR_TEXTO, width=26, anchor="w")
        self.lbl_barra1.pack(side="left")
        self.lbl_cnt1 = tk.Label(fila1, text="",
                                 bg=COR_BG, font=("Segoe UI", 8), fg=COR_SUBTEXTO,
                                 width=10, anchor="w")
        self.lbl_cnt1.pack(side="left", padx=(4, 6))
        self.pv1 = tk.DoubleVar()
        self.pb1 = ttk.Progressbar(fila1, variable=self.pv1, maximum=100,
                                   length=320, style="Corp.Horizontal.TProgressbar")
        self.pb1.pack(side="left")
        self.lbl_check1 = tk.Label(fila1, text="", bg=COR_BG,
                                   font=("Segoe UI", 12), fg="#27AE60", width=3)
        self.lbl_check1.pack(side="left", padx=(6, 0))

        # — Barra 2: Revisando hojas de vida —
        fila2 = tk.Frame(barras_frame, bg=COR_BG)
        fila2.pack(fill="x", pady=(6, 2))
        self.lbl_barra2 = tk.Label(fila2, text="Revisando hojas de vida",
                                   bg=COR_BG, font=("Segoe UI", 9, "bold"),
                                   fg=COR_TEXTO, width=26, anchor="w")
        self.lbl_barra2.pack(side="left")
        self.lbl_cnt2 = tk.Label(fila2, text="",
                                 bg=COR_BG, font=("Segoe UI", 8), fg=COR_SUBTEXTO,
                                 width=10, anchor="w")
        self.lbl_cnt2.pack(side="left", padx=(4, 6))
        self.pv2 = tk.DoubleVar()
        self.pb2 = ttk.Progressbar(fila2, variable=self.pv2, maximum=100,
                                   length=320, style="Corp.Horizontal.TProgressbar")
        self.pb2.pack(side="left")
        self.lbl_check2 = tk.Label(fila2, text="", bg=COR_BG,
                                   font=("Segoe UI", 12), fg="#27AE60", width=3)
        self.lbl_check2.pack(side="left", padx=(6, 0))

        # — Barra 3: Clasificando hojas de vida —
        fila3 = tk.Frame(barras_frame, bg=COR_BG)
        fila3.pack(fill="x", pady=(6, 4))
        self.lbl_barra3 = tk.Label(fila3, text="Clasificando hojas de vida",
                                   bg=COR_BG, font=("Segoe UI", 9, "bold"),
                                   fg=COR_TEXTO, width=26, anchor="w")
        self.lbl_barra3.pack(side="left")
        self.lbl_cnt3 = tk.Label(fila3, text="",
                                 bg=COR_BG, font=("Segoe UI", 8), fg=COR_SUBTEXTO,
                                 width=10, anchor="w")
        self.lbl_cnt3.pack(side="left", padx=(4, 6))
        self.pv3 = tk.DoubleVar()
        self.pb3 = ttk.Progressbar(fila3, variable=self.pv3, maximum=100,
                                   length=320, style="Corp.Horizontal.TProgressbar")
        self.pb3.pack(side="left")
        self.lbl_check3 = tk.Label(fila3, text="", bg=COR_BG,
                                   font=("Segoe UI", 12), fg="#27AE60", width=3)
        self.lbl_check3.pack(side="left", padx=(6, 0))

        # ── Footer ──────────────────────────────────────────────────────
        footer = tk.Frame(self.root, bg=COR_NARANJA, height=4)
        footer.pack(fill="x", side="bottom")

        # Widget oculto para acumular log (necesario para que correr_proceso lo llame)
        self.log_text = tk.Text(self.root)   # no se empaqueta → invisible

    def log(self, msg):
        # Solo escribe al archivo (manejado en correr_proceso); no muestra nada en pantalla
        pass

    def actualizar_progreso(self, actual, total):
        """Barra 1 — Descargando hojas de vida."""
        pct = (actual / total) * 100
        self.pv1.set(pct)
        self.lbl_cnt1.config(text=f"{actual} de {total}")
        self.root.update_idletasks()

    def barra1_terminada(self):
        """Marca la barra 1 como completada con chulito."""
        self.pv1.set(100)
        self.lbl_check1.config(text="✅")
        self.lbl_cnt1.config(text="Finalizado")
        self.root.update_idletasks()

    def actualizar_progreso_ia(self, actual, total):
        """Barra 2 — Revisando hojas de vida con IA."""
        pct = (actual / total) * 100
        self.pv2.set(pct)
        self.lbl_cnt2.config(text=f"{actual} de {total}")
        self.root.update_idletasks()

    def barra2_terminada(self):
        """Marca la barra 2 como completada con chulito."""
        self.pv2.set(100)
        self.lbl_check2.config(text="✅")
        self.lbl_cnt2.config(text="Finalizado")
        self.root.update_idletasks()

    def actualizar_progreso_clasificacion(self, actual, total):
        """Barra 3 — Clasificando hojas de vida."""
        pct = (actual / total) * 100
        self.pv3.set(pct)
        self.lbl_cnt3.config(text=f"{actual} de {total}")
        self.root.update_idletasks()

    def barra3_terminada(self):
        """Marca la barra 3 como completada con chulito."""
        self.pv3.set(100)
        self.lbl_check3.config(text="✅")
        self.lbl_cnt3.config(text="Finalizado")
        self.root.update_idletasks()

    def proceso_terminado(self, ok):
        self.btn.config(state="normal", text="  ▶  Iniciar filtrado de HVs")
        if ok:
            messagebox.showinfo("Proceso completado",
                                "El filtrado finalizó correctamente.\n"
                                "Revisa la carpeta de resultados.")
        else:
            messagebox.showerror("Error en el proceso",
                                 "El proceso terminó con errores.\n"
                                 "Revisa el archivo log_filtrador.txt.")

    def iniciar(self):
        vacante = self.v_vacante.get().strip()
        url     = self.v_url.get().strip()
        if not vacante or not url:
            messagebox.showwarning("Campos requeridos",
                                   "Completa el nombre de la vacante y la URL.")
            return

        try:
            peso_exp = int(self.v_peso_exp.get())
            peso_aca = int(self.v_peso_aca.get())
        except ValueError:
            messagebox.showerror("Error", "Los pesos deben ser números enteros (ej: 60).")
            return

        if peso_exp + peso_aca != 100:
            messagebox.showwarning("Pesos inválidos",
                                   f"La suma de los pesos debe ser 100 %.\n"
                                   f"Actualmente: {peso_exp} + {peso_aca} = {peso_exp + peso_aca} %")
            return

        try:
            cfg = {
                "vacante"          : vacante,
                "url_vacante"      : url,
                "edad_min"         : int(self.v_emin.get()),
                "edad_max"         : int(self.v_emax.get()),
                "sal_min"          : int(self.v_smin.get().replace("$","").replace(".","").replace(",","").strip()),
                "sal_max"          : int(self.v_smax.get().replace("$","").replace(".","").replace(",","").strip()),
                "requiere_sabados" : self.v_sab.get(),
                "peso_exp"         : peso_exp,
                "peso_aca"         : peso_aca,
                "palabras_clave"   : self.v_keywords.get().strip(),
            }
        except ValueError:
            messagebox.showerror("Error", "Verifica que edad y salario sean números válidos.")
            return

        self.btn.config(state="disabled", text="  ⏳  Procesando...")
        self.pv1.set(0)
        self.pv2.set(0)
        self.pv3.set(0)
        self.lbl_check1.config(text="")
        self.lbl_check2.config(text="")
        self.lbl_check3.config(text="")
        self.lbl_cnt1.config(text="")
        self.lbl_cnt2.config(text="")
        self.lbl_cnt3.config(text="")

        threading.Thread(target=correr_proceso,
                         args=(cfg, self.log, self.actualizar_progreso,
                               self.proceso_terminado, self.barra1_terminada,
                               self.actualizar_progreso_ia, self.barra2_terminada,
                               self.actualizar_progreso_clasificacion, self.barra3_terminada),
                         daemon=True).start()


if __name__ == "__main__":
    CARPETA_DESCARGA.mkdir(exist_ok=True)
    root = tk.Tk()
    App(root)
    root.mainloop()
