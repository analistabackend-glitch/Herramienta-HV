"""
filtrador_hv_v2.py
==================
Filtrado automatico de HV desde Computrabajo con clasificacion via Claude API.

Instalar dependencias:
    pip install selenium webdriver-manager google-auth google-auth-oauthlib
                google-api-python-client pandas openpyxl pdfplumber anthropic

Configurar antes de correr:
    1. Editar COMPUTRABAJO_EMAIL y COMPUTRABAJO_PASSWORD
    2. Tener credentials.json de Google Cloud en la misma carpeta
    3. Configurar ANTHROPIC_API_KEY como variable de entorno:
         Windows:  set ANTHROPIC_API_KEY=sk-ant-...
         Mac/Linux: export ANTHROPIC_API_KEY=sk-ant-...
"""

import re, os, json, time, pickle, threading, tkinter as tk
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
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import anthropic as anthropic_sdk
except ImportError:
    anthropic_sdk = None

# ─────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────

try:
    from config_local import (
        COMPUTRABAJO_EMAIL,
        COMPUTRABAJO_PASSWORD,
        ANTHROPIC_API_KEY
    )
except ImportError:
    raise Exception("Falta config_local.py con las credenciales")

CREDENTIALS_FILE      = "credentials.json"
TOKEN_FILE            = "token.pickle"
DRIVE_ROOT_FOLDER     = "Computrabajo_Vacantes"
CARPETA_DESCARGA      = Path("descargas_temp")

# ══════════════════════════════════════════
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
    res = service.files().list(q=q, fields="files(id)").execute()
    if res.get("files"):
        return res["files"][0]["id"]
    meta = {"name": nombre, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    return service.files().create(body=meta, fields="id").execute()["id"]

def drive_upload(service, ruta, folder_id, mimetype):
    from googleapiclient.http import MediaFileUpload as MFU
    nombre = Path(ruta).name
    media = MFU(str(ruta), mimetype=mimetype, resumable=True)
    meta = {"name": nombre, "parents": [folder_id]}
    return service.files().create(body=meta, media_body=media, fields="id").execute()["id"]


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
    driver.get(url_vacante); time.sleep(2)
    urls = set(); pagina = 1
    BASE = "https://empresa.co.computrabajo.com"
    while True:
        log(f"  Pagina {pagina}...")
        for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='MatchCvDetail'],a[href*='MatchDetail'],a[href*='CvDetail']"):
            h = a.get_attribute("href")
            if not h: continue
            if h.startswith("/"): h = BASE + h
            urls.add(h)
        try:
            sig = driver.find_element(By.CSS_SELECTOR,"a.next-page,li.next a,.pagination a[rel='next']")
            if "disabled" in (sig.get_attribute("class") or ""): break
            sig.click(); time.sleep(2); pagina += 1
        except NoSuchElementException: break
    log(f"  {len(urls)} candidatos encontrados"); return list(urls)

def extraer_datos(driver, url, log):
    driver.get(url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "candidato")))
    time.sleep(1)
    d = {"url": url, "nombre": None, "email": None, "telefono": None, "whatsapp": None, "ciudad": None, "url_pdf": None, "fecha": datetime.now().isoformat()}
    try:
        d["nombre"] = driver.find_element(By.CSS_SELECTOR,"h1.fwB").text.replace("Hoja de vida de","").strip()
    except: pass
    try:
        sidebar = driver.find_element(By.CSS_SELECTOR,"article#candidato")
        texto = sidebar.text
        log(f"  SIDEBAR: {repr(texto[:200])}")
        m = re.search(r"[\w.\-]+@[\w.\-]+\.\w+", texto)
        if m: d["email"] = m.group(0)
        for el in driver.find_elements(By.CSS_SELECTOR,"li span.icon_phone ~ span,li .fs16"):
            t = el.text.strip()
            if re.match(r"[\d\s\+\-]{7,}", t): d["telefono"] = t; break
    except: pass
    try:
        wa = driver.find_element(By.CSS_SELECTOR,"a[href*='whatsapp']")
        d["whatsapp"] = wa.get_attribute("href")
    except: pass
    try:
        a = driver.find_element(By.CSS_SELECTOR,"a.js_download_file")
        h = a.get_attribute("href")
        if h and h != "#":
            if h.startswith("/"): h = "https://empresa.co.computrabajo.com" + h
            d["url_pdf"] = h
    except: pass
    return d

def descargar_pdf(driver, url_pdf, nombre):
    CARPETA_DESCARGA.mkdir(exist_ok=True)
    ruta = CARPETA_DESCARGA / f"{nombre}.pdf"
    session = requests.Session()
    for c in driver.get_cookies():
        session.cookies.set(c["name"], c["value"])
    headers = {"User-Agent": driver.execute_script("return navigator.userAgent")}
    r = session.get(url_pdf, headers=headers, stream=True, timeout=30)
    if r.status_code == 200:
        ct = r.headers.get("Content-Type","")
        if "pdf" in ct or "octet" in ct or len(r.content) > 1000:
            with open(ruta,"wb") as f:
                for chunk in r.iter_content(8192): f.write(chunk)
            with open(ruta,"rb") as f:
                if f.read(4) == b"%PDF": return ruta
            ruta.unlink()
    return None


# ══════════════════════════════════════════
#  TEXTO DEL PDF
# ══════════════════════════════════════════

def extraer_texto(ruta):
    if pdfplumber is None: return ""
    try:
        with pdfplumber.open(ruta) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except: return ""


# ══════════════════════════════════════════
#  CLASIFICACION CON CLAUDE
# ══════════════════════════════════════════

def system_prompt(cfg):
    crit = ""
    for i,c in enumerate(cfg["criterios_secundarios"],1):
        if c["nombre"].strip():
            crit += f"\n  {i}. {c['nombre']} (peso {c['peso']}%) — {c['descripcion']}"
    if not crit: crit = "\n  (ninguno configurado)"
    return (
        f"Eres un asistente experto en seleccion de personal colombiano. "
        f"Vacante: {cfg['vacante']}\n\n"
        "FILTROS INICIALES (eliminatorios). Si falla cualquiera -> DESCARTADO.\n\n"
        f"1. SALARIO: rango aceptado ${cfg['salario_min']:,}-${cfg['salario_max']:,} COP. "
        "Si no especifica -> PASA. Fuera del rango -> FALLA.\n\n"
        "2. SABADOS: disponibilidad requerida. "
        "PASA: si/eventualmente/se puede negociar. FALLA: no. Si no menciona -> PASA.\n\n"
        f"3. EDAD: rango {cfg['edad_min']}-{cfg['edad_max']} anios. Si no menciona -> PASA.\n\n"
        "REQUERIMIENTOS SECUNDARIOS (solo si paso etapa1).\n"
        "Puntaje 100% = OPCIONADO. Menos de 100% = POSIBLEMENTE_OPCIONADO.\n\n"
        "CRITERIO FIJO - Permanencia: en las ultimas 2 experiencias ninguna menor a 1 anio. "
        "Si no cumple -> restar 20 puntos.\n\n"
        f"CRITERIOS CONFIGURADOS:{crit}\n\n"
        "Responde SOLO con JSON valido sin markdown:\n"
        '{"etapa1":{"salario":"PASA|FALLA|NO_ESPECIFICA","sabados":"PASA|FALLA|NO_ESPECIFICA",'
        '"edad":"PASA|FALLA|NO_ESPECIFICA","resultado":"PASA|DESCARTADO","motivo_descarte":"texto o null"},'
        '"etapa2":{"permanencia":{"cumple":true,"detalle":"texto"},'
        '"criterios":[{"nombre":"texto","peso":0,"cumple":true,"detalle":"texto"}],'
        '"puntaje_total":0,"clasificacion":"OPCIONADO|POSIBLEMENTE_OPCIONADO","resumen":"texto"} }\n'
        "Si DESCARTADO en etapa1, etapa2 debe ser null."
    )

def clasificar(texto_pdf, cfg, log):
    if not texto_pdf.strip():
        return {"clasificacion":"DESCARTADO","motivo":"PDF sin texto legible","puntaje":0,"resumen":"PDF sin texto","raw":{}}
    if anthropic_sdk is None:
        log("  ERROR: libreria anthropic no instalada")
        return {"clasificacion":"POSIBLEMENTE_OPCIONADO","motivo":"anthropic no instalado","puntaje":0,"resumen":"Error","raw":{}}
    try:
        cliente = anthropic_sdk.Anthropic()
        resp = cliente.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system_prompt(cfg),
            messages=[{"role":"user","content":f"Hoja de vida:\n\n{texto_pdf[:4000]}"}]
        )
        txt = re.sub(r"```json\s*|\s*```","",resp.content[0].text.strip()).strip()
        data = json.loads(txt)
        e1 = data.get("etapa1",{})
        e2 = data.get("etapa2")
        if e1.get("resultado") == "DESCARTADO":
            return {"clasificacion":"DESCARTADO","motivo":e1.get("motivo_descarte","Filtro inicial"),"puntaje":0,"resumen":e1.get("motivo_descarte",""),"raw":data}
        puntaje = (e2 or {}).get("puntaje_total",0)
        clasif  = (e2 or {}).get("clasificacion","POSIBLEMENTE_OPCIONADO")
        resumen = (e2 or {}).get("resumen","")
        return {"clasificacion":clasif,"motivo":resumen,"puntaje":puntaje,"resumen":resumen,"raw":data}
    except json.JSONDecodeError as e:
        log(f"  Claude no devolvio JSON: {e}")
        return {"clasificacion":"POSIBLEMENTE_OPCIONADO","motivo":"Error JSON — revision manual","puntaje":0,"resumen":"Error JSON","raw":{}}
    except Exception as e:
        if "529" in str(e) or "overloaded" in str(e).lower():
            log("  API sobrecargada, esperando 30 segundos y reintentando...")
            time.sleep(30)
            try:
                cliente2 = anthropic_sdk.Anthropic()
                resp2 = cliente2.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=600,
                    system=system_prompt(cfg),
                    messages=[{"role":"user","content":f"Hoja de vida:{texto_pdf[:4000]}"}]
                )
                txt2 = re.sub(r"```json\s*|\s*```", "", resp2.content[0].text.strip()).strip()
                data2 = json.loads(txt2)
                e1b = data2.get("etapa1",{})
                e2b = data2.get("etapa2")
                if e1b.get("resultado") == "DESCARTADO":
                    return {"clasificacion":"DESCARTADO","motivo":e1b.get("motivo_descarte",""),"puntaje":0,"resumen":e1b.get("motivo_descarte",""),"raw":data2}
                puntaje2 = (e2b or {}).get("puntaje_total",0)
                clasif2  = (e2b or {}).get("clasificacion","POSIBLEMENTE_OPCIONADO")
                resumen2 = (e2b or {}).get("resumen","")
                return {"clasificacion":clasif2,"motivo":resumen2,"puntaje":puntaje2,"resumen":resumen2,"raw":data2}
            except Exception as e2:
                log(f"  Reintento fallido: {e2}")
        log(f"  Error API: {e}")
        return {"clasificacion":"POSIBLEMENTE_OPCIONADO","motivo":f"Error: {e} — revision manual","puntaje":0,"resumen":"Error API","raw":{}}


# ══════════════════════════════════════════
#  PROCESO PRINCIPAL
# ══════════════════════════════════════════

def correr_proceso(cfg, log, progress, done):
    try:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

        log("Conectando con Google Drive...")
        drive = drive_autenticar()
        vn     = f"{cfg['vacante']}_{datetime.now().strftime('%Y-%m')}"
        root   = drive_folder(drive, DRIVE_ROOT_FOLDER)
        vid    = drive_folder(drive, vn, root)
        c_ok   = drive_folder(drive, "1_Opcionados",              vid)
        c_pos  = drive_folder(drive, "2_Posiblemente_Opcionados", vid)
        c_des  = drive_folder(drive, "3_Descartados",             vid)
        log(f"Carpetas listas en Drive: {DRIVE_ROOT_FOLDER}/{vn}/")

        driver = crear_driver()
        if not login(driver, log): driver.quit(); done(False); return

        urls  = extraer_urls(driver, cfg["url_vacante"], log)
        total = len(urls)
        if not total: log("Sin candidatos. Verifica la URL."); driver.quit(); done(False); return

        resumen = []; conteos = {"OPCIONADO":0,"POSIBLEMENTE_OPCIONADO":0,"DESCARTADO":0}

        for i,url in enumerate(urls,1):
            progress(i,total)
            log(f"\n[{i}/{total}] Procesando...")
            try:
                datos = extraer_datos(driver, url, log)
                nombre = datos.get("nombre") or f"candidato_{i:03d}"
                log(f"  {nombre}")

                if not datos.get("url_pdf"):
                    datos.update({"clasificacion":"DESCARTADO","motivo":"Sin PDF","puntaje":0,"resumen":"Sin PDF","detalle":""})
                    conteos["DESCARTADO"] += 1; resumen.append(datos); continue

                nombre_f = re.sub(r"[^\w\s-]","",nombre).strip().replace(" ","_")
                ruta = descargar_pdf(driver, datos["url_pdf"], nombre_f)
                if not ruta:
                    datos.update({"clasificacion":"DESCARTADO","motivo":"PDF no descargable","puntaje":0,"resumen":"PDF no descargable","detalle":""})
                    conteos["DESCARTADO"] += 1; resumen.append(datos); continue

                texto = extraer_texto(ruta)
                log(f"  Texto: {len(texto)} caracteres")
                log("  Clasificando con Claude...")
                r = clasificar(texto, cfg, log)

                datos["clasificacion"]  = r["clasificacion"]
                datos["motivo"]         = r["motivo"]
                datos["puntaje"]        = r["puntaje"]
                datos["resumen"]        = r["resumen"]
                datos["detalle"]        = json.dumps(r.get("raw",{}), ensure_ascii=False)

                clasif = r["clasificacion"]
                log(f"  [{clasif}] {r['puntaje']}% — {r['resumen']}")

                mime_pdf = "application/pdf"
                if clasif == "OPCIONADO":
                    drive_upload(drive, ruta, c_ok,  mime_pdf); conteos["OPCIONADO"] += 1
                elif clasif == "POSIBLEMENTE_OPCIONADO":
                    drive_upload(drive, ruta, c_pos, mime_pdf); conteos["POSIBLEMENTE_OPCIONADO"] += 1
                else:
                    drive_upload(drive, ruta, c_des, mime_pdf); conteos["DESCARTADO"] += 1

                ruta.unlink(); resumen.append(datos); time.sleep(3)
            except Exception as e:
                log(f"  Error: {e}"); continue

        driver.quit()

        log("\nGenerando Excel...")
        filas = [{"Clasificacion":d.get("clasificacion"),"Puntaje (%)":d.get("puntaje"),
                  "Motivo/Resumen":d.get("resumen"),"Nombre":d.get("nombre"),
                  "Email":d.get("email"),"Telefono":d.get("telefono"),
                  "WhatsApp":d.get("whatsapp"),"Ciudad":d.get("ciudad"),
                  "URL":d.get("url"),"Fecha":d.get("fecha"),"Detalle Claude":d.get("detalle")}
                 for d in resumen]
        df = pd.DataFrame(filas)
        orden = {"OPCIONADO":0,"POSIBLEMENTE_OPCIONADO":1,"DESCARTADO":2}
        df["_o"] = df["Clasificacion"].map(orden).fillna(3)
        df = df.sort_values("_o").drop(columns=["_o"])
        xp = CARPETA_DESCARGA / f"resumen_{cfg['vacante'].replace(' ','_')}.xlsx"
        CARPETA_DESCARGA.mkdir(exist_ok=True)
        df.to_excel(xp, index=False, engine="openpyxl")
        drive_upload(drive, xp, vid, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        xp.unlink()
        log("Excel subido a Drive")
        log(f"\nListo. Total: {total} | OK: {conteos['OPCIONADO']} | Posibles: {conteos['POSIBLEMENTE_OPCIONADO']} | Descartados: {conteos['DESCARTADO']}")
        log(f"Drive: {DRIVE_ROOT_FOLDER}/{vn}/")
        done(True)
    except Exception as e:
        import traceback
        log(f"\nERROR: {e}\n{traceback.format_exc()}")
        done(False)


# ══════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════

class App:
    def __init__(self, root):
        self.root = root
        root.title("Filtrador de HV v2.0 — con Claude AI")
        root.geometry("700x950")
        root.resizable(False, True)
        root.configure(bg="#f0f4f8")
        self._row = 0
        self._build()

    def _build(self):
        tk.Label(self.root, text="Filtrador de HV  v2.0  —  Impulsado por Claude AI",
                 font=("Segoe UI",15,"bold"), bg="#1a3c5e", fg="white", pady=12).pack(fill="x")

        canvas = tk.Canvas(self.root, bg="#f0f4f8", highlightthickness=0)
        sb = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        fo = tk.Frame(canvas, bg="#f0f4f8")
        fo.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=fo, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.f = tk.Frame(fo, bg="#f0f4f8", padx=24, pady=16)
        self.f.pack(fill="both", expand=True)
        self._row = 0

        def nr(): r=self._row; self._row+=1; return r
        def sep(t):
            ttk.Separator(self.f,orient="horizontal").grid(row=nr(),column=0,columnspan=3,sticky="ew",pady=10)
            tk.Label(self.f,text=t,bg="#f0f4f8",font=("Segoe UI",11,"bold")).grid(row=nr(),column=0,columnspan=3,sticky="w")
        def campo(lbl, default="", w=36):
            r=nr()
            tk.Label(self.f,text=lbl,bg="#f0f4f8",font=("Segoe UI",10)).grid(row=r,column=0,sticky="w",pady=3)
            v=tk.StringVar(value=default)
            tk.Entry(self.f,textvariable=v,width=w,font=("Segoe UI",10)).grid(row=r,column=1,columnspan=2,sticky="w",padx=(8,0))
            return v

        self.v_vacante = campo("Nombre de la vacante:", "Analista Contable")
        self.v_url     = campo("URL vacante Computrabajo:")

        sep("FILTROS INICIALES  (eliminatorios)")
        self.v_emin = campo("Edad minima (anos):", "20")
        self.v_emax = campo("Edad maxima (anos):", "45")
        self.v_smin = campo("Salario minimo ($):", "1300000")
        self.v_smax = campo("Salario maximo ($):", "3000000")
        r=nr()
        tk.Label(self.f,text="Disponibilidad sabados:",bg="#f0f4f8",font=("Segoe UI",10)).grid(row=r,column=0,sticky="w",pady=3)
        self.v_sab = tk.BooleanVar(value=True)
        sf=tk.Frame(self.f,bg="#f0f4f8"); sf.grid(row=r,column=1,sticky="w",padx=(8,0))
        tk.Radiobutton(sf,text="Requerido", variable=self.v_sab,value=True, bg="#f0f4f8").pack(side="left")
        tk.Radiobutton(sf,text="No importa",variable=self.v_sab,value=False,bg="#f0f4f8").pack(side="left",padx=8)

        sep("REQUERIMIENTOS SECUNDARIOS  (pesos deben sumar 100%)")
        r=nr()
        tk.Label(self.f,text="Permanencia >1 ano en ultimas 2 experiencias: siempre se evalua (-20 pts si no cumple)",
                 bg="#f0f4f8",fg="#666",font=("Segoe UI",8,"italic"),wraplength=600).grid(row=r,column=0,columnspan=3,sticky="w",pady=(0,6))
        r=nr()
        for col,t,w in [(0,"Criterio",22),(1,"Descripcion / Detalle",28),(2,"Peso %",7)]:
            tk.Label(self.f,text=t,bg="#e2e8f0",font=("Segoe UI",9,"bold"),width=w,anchor="w",padx=4).grid(
                row=r,column=col,sticky="ew",padx=(0 if col==0 else 4,0),pady=(0,2))

        self.criterios=[]
        defaults=[("Experiencia especifica","minimo 2 anos en contabilidad","30"),
                  ("Formacion academica","tecnologo o profesional contable","25"),
                  ("Palabras clave","NIIF, causacion, conciliacion bancaria","25"),
                  ("Sector de experiencia","sector real, industria o servicios","20"),
                  ("","","0")]
        for nd,dd,pd in defaults:
            r=nr(); vn=tk.StringVar(value=nd); vd=tk.StringVar(value=dd); vp=tk.StringVar(value=pd)
            tk.Entry(self.f,textvariable=vn,width=22,font=("Segoe UI",9)).grid(row=r,column=0,sticky="w",pady=2)
            tk.Entry(self.f,textvariable=vd,width=28,font=("Segoe UI",9)).grid(row=r,column=1,sticky="w",padx=(4,0),pady=2)
            tk.Entry(self.f,textvariable=vp,width=7, font=("Segoe UI",9)).grid(row=r,column=2,sticky="w",padx=(4,0),pady=2)
            self.criterios.append((vn,vd,vp))

        r=nr()
        self.lbl_suma=tk.Label(self.f,text="Suma de pesos: 100%",bg="#f0f4f8",font=("Segoe UI",9,"bold"),fg="#16a34a")
        self.lbl_suma.grid(row=r,column=0,columnspan=3,sticky="w",pady=(4,0))
        for vn,vd,vp in self.criterios:
            vp.trace_add("write", lambda *a: self._suma())

        ttk.Separator(self.f,orient="horizontal").grid(row=nr(),column=0,columnspan=3,sticky="ew",pady=10)

        r=nr()
        self.btn=tk.Button(self.f,text="Iniciar filtrado",font=("Segoe UI",11,"bold"),
                           bg="#e85d04",fg="white",activebackground="#c44d04",
                           bd=0,padx=20,pady=8,cursor="hand2",command=self.iniciar)
        self.btn.grid(row=r,column=0,columnspan=3,pady=8)

        r=nr()
        self.pv=tk.DoubleVar()
        ttk.Progressbar(self.f,variable=self.pv,maximum=100,length=600).grid(row=r,column=0,columnspan=3,pady=(4,0))
        r=nr()
        self.lbl_prog=tk.Label(self.f,text="Esperando...",bg="#f0f4f8",font=("Segoe UI",9),fg="#555")
        self.lbl_prog.grid(row=r,column=0,columnspan=3)

        r=nr()
        tk.Label(self.f,text="Log:",bg="#f0f4f8",font=("Segoe UI",10,"bold")).grid(row=r,column=0,sticky="w",pady=(12,2))
        r=nr()
        self.log_text=tk.Text(self.f,height=12,width=72,font=("Consolas",9),bg="#1e1e2e",fg="#cdd6f4",bd=0,padx=8,pady=8)
        self.log_text.grid(row=r,column=0,columnspan=3)
        lsb=ttk.Scrollbar(self.f,command=self.log_text.yview)
        lsb.grid(row=r,column=3,sticky="ns")
        self.log_text["yscrollcommand"]=lsb.set

    def _suma(self):
        total=sum(int(vp.get() or 0) for _,_,vp in self.criterios if vp.get().isdigit())
        self.lbl_suma.config(text=f"Suma de pesos: {total}%",fg="#16a34a" if total==100 else "#dc2626")

    def log(self,msg):
        self.log_text.insert("end",msg+"\n"); self.log_text.see("end"); self.root.update_idletasks()

    def actualizar_progreso(self,actual,total):
        pct=(actual/total)*100; self.pv.set(pct)
        self.lbl_prog.config(text=f"Candidato {actual} de {total}  ({pct:.0f}%)"); self.root.update_idletasks()

    def proceso_terminado(self,ok):
        self.btn.config(state="normal",text="Iniciar filtrado")
        if ok:
            self.lbl_prog.config(text="Completado")
            messagebox.showinfo("Listo","Proceso completado.\nRevisa tu Google Drive.")
        else:
            self.lbl_prog.config(text="Termino con errores")
            messagebox.showerror("Error","Termino con errores.\nRevisa el log.")

    def iniciar(self):
        vacante=self.v_vacante.get().strip(); url=self.v_url.get().strip()
        if not vacante or not url:
            messagebox.showwarning("Faltan campos","Completa vacante y URL."); return

        total_p=0; crits=[]
        for vn,vd,vp in self.criterios:
            n=vn.get().strip(); d=vd.get().strip()
            try: p=int(vp.get() or 0)
            except: p=0
            if n: crits.append({"nombre":n,"descripcion":d,"peso":p}); total_p+=p

        if crits and total_p!=100:
            messagebox.showerror("Pesos incorrectos",f"Los pesos suman {total_p}%.\nDeben sumar 100%."); return

        try:
            cfg={
                "vacante":vacante,"url_vacante":url,
                "edad_min":int(self.v_emin.get()),"edad_max":int(self.v_emax.get()),
                "salario_min":int(self.v_smin.get().replace(",","").replace(".","")),
                "salario_max":int(self.v_smax.get().replace(",","").replace(".","")),
                "requiere_sabados":self.v_sab.get(),
                "criterios_secundarios":crits,
            }
        except ValueError:
            messagebox.showerror("Error","Verifica que edad y salario sean numeros validos."); return

        self.log_text.delete("1.0","end"); self.btn.config(state="disabled",text="Procesando...")
        self.pv.set(0); self.lbl_prog.config(text="Iniciando...")
        threading.Thread(target=correr_proceso,
                         args=(cfg,self.log,self.actualizar_progreso,self.proceso_terminado),
                         daemon=True).start()


if __name__ == "__main__":
    CARPETA_DESCARGA.mkdir(exist_ok=True)
    root = tk.Tk()
    App(root)
    root.mainloop()
