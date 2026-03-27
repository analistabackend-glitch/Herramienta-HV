"""
ui.py
====
Interfaz gráfica del sistema de filtrado usando Tkinter.
Diseño basado en la identidad visual de Fertrac.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import sys
import os

def ruta_archivo(rel_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel_path)
    # Usar la carpeta donde está ui.py, no el cwd
    # Esto garantiza que funcione sin importar desde dónde se ejecute
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel_path)
# ── Paleta de colores Fertrac ──────────────────────────────────────────────────
COLOR_NARANJA        = "#F5A623"   # botones, acentos
COLOR_NARANJA_HOVER  = "#E8960F"
COLOR_NARANJA_DARK   = "#D4860A"
COLOR_HEADER_BG      = "#FFFFFF"
COLOR_HEADER_BORDER  = "#E0E0E0"
COLOR_SECTION_TITLE  = "#333333"
COLOR_SECTION_BAR    = "#F5A623"
COLOR_BG             = "#F4F4F4"
COLOR_WIDGET_BG      = "#FFFFFF"
COLOR_TEXT           = "#333333"
COLOR_TEXT_LIGHT     = "#777777"
COLOR_ENTRY_BG       = "#FFFFFF"
COLOR_ENTRY_BORDER   = "#CCCCCC"
COLOR_VERSION_BG     = "#F5A623"
COLOR_VERSION_FG     = "#FFFFFF"
COLOR_DEPTO_FG       = "#F5A623"
COLOR_SEPARATOR      = "#E5E5E5"

FONT_BOLD   = ("Segoe UI", 9, "bold")
FONT_NORMAL = ("Segoe UI", 9)
FONT_SMALL  = ("Segoe UI", 8)
FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_DEPTO  = ("Segoe UI", 8, "bold")


# ── Widgets personalizados ─────────────────────────────────────────────────────

class StyledEntry(tk.Entry):
    """Entry con bordes y colores personalizados."""

    def __init__(self, parent, width=18, **kw):
        super().__init__(
            parent,
            width=width,
            bg=COLOR_ENTRY_BG,
            fg=COLOR_TEXT,
            relief="solid",
            bd=1,
            font=FONT_NORMAL,
            highlightthickness=1,
            highlightbackground=COLOR_ENTRY_BORDER,
            highlightcolor=COLOR_NARANJA,
            insertbackground=COLOR_TEXT,
            **kw,
        )


class SectionFrame(tk.Frame):
    """Frame con barra naranja a la izquierda y título en mayúsculas."""

    def __init__(self, parent, title, **kw):
        super().__init__(parent, bg=COLOR_WIDGET_BG, **kw)

        # Línea naranja izquierda
        bar = tk.Frame(self, bg=COLOR_SECTION_BAR, width=4)
        bar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        tk.Label(
            self,
            text=title,
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_SECTION_TITLE,
            bg=COLOR_WIDGET_BG,
        ).pack(side=tk.LEFT, pady=6)


class OrangeButton(tk.Button):
    """Botón con fondo naranja estilo Fertrac."""

    def __init__(self, parent, **kwargs):
        font = kwargs.pop("font", FONT_BOLD)
        padx = kwargs.pop("padx", 14)
        pady = kwargs.pop("pady", 6)

        super().__init__(
            parent,
            bg=COLOR_NARANJA,
            fg="white",
            activebackground=COLOR_NARANJA_HOVER,
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=font,
            padx=padx,
            pady=pady,
            **kwargs,
        )

        # Guardar colores actuales (dinámicos)
        self.default_bg = self["bg"]
        self.hover_bg   = self["activebackground"]

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, e):
            self.config(bg=self.hover_bg)

    def _on_leave(self, e):
            self.config(bg=self.default_bg)


# ── Clase principal ────────────────────────────────────────────────────────────

class AppUI:
    """Interfaz gráfica principal – diseño Fertrac."""

    def __init__(self, root, callback_iniciar):
        self.root = root
        self.callback_iniciar = callback_iniciar
        self.usar_cache_filtros = False

        # Variables Tkinter
        self.v_vacante   = tk.StringVar()
        self.v_url       = tk.StringVar()
        self.v_emin      = tk.StringVar(value="20")
        self.v_emax      = tk.StringVar(value="45")
        self.v_smin      = tk.StringVar(value="$1.750.905")
        self.v_smax      = tk.StringVar(value="$3.000.000")
        self.v_sab       = tk.BooleanVar(value=True)
        self.v_peso_exp  = tk.StringVar(value="50")
        self.v_peso_aca  = tk.StringVar(value="50")
        self.v_keywords  = tk.StringVar()

        # Referencias a widgets
        self.entries_bloqueables = []
        self.radios_sab          = []
        self.btn_habilitar       = None
        self.btn_iniciar         = None
        self.pv1 = self.pv2 = self.pv3 = None
        self.lbl_check1 = self.lbl_check2 = self.lbl_check3 = None
        self.lbl_cnt1   = self.lbl_cnt2   = self.lbl_cnt3   = None
        self.text_log   = None

        self._construir_ui()
        self._verificar_y_cargar_cache()

    def validar_numeros(self, valor):
        """Permite solo dígitos enteros (para edad y pesos)."""
        return valor.isdigit() or valor == ""

    def _limpiar_moneda(self, valor):
        """Devuelve solo los dígitos de un valor con formato monetario."""
        return valor.replace("$", "").replace(".", "").replace(",", "").strip()

    def formatear_moneda(self, event, var, entry_widget):
        """Formatea en tiempo real mientras el usuario escribe."""
        raw = self._limpiar_moneda(var.get())

        if not raw:
            var.set("")
            return

        # Quitar cualquier carácter no numérico que se haya colado
        raw = "".join(c for c in raw if c.isdigit())
        if not raw:
            var.set("")
            return

        numero     = int(raw)
        formateado = "${:,.0f}".format(numero).replace(",", ".")

        # Guardar posición del cursor antes de sobreescribir
        try:
            pos = entry_widget.index(tk.INSERT)
        except Exception:
            pos = len(formateado)

        var.set(formateado)

        try:
            entry_widget.icursor(min(pos, len(formateado)))
        except Exception:
            pass

    def obtener_salario_int(self, var):
        """Devuelve el valor numérico entero de una variable de salario."""
        return int(self._limpiar_moneda(var.get()) or 0)
        

    # ── Construcción de la UI ──────────────────────────────────────────────────

    def _construir_ui(self):
        self.root.title("Filtrador de Hojas de Vida")
        self.root.geometry("690x780")
        self.root.resizable(True, True)
        self.root.configure(bg=COLOR_BG)
        self.root.minsize(620, 650)

        # Scroll contenedor
        outer = tk.Frame(self.root, bg=COLOR_BG)
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, bg=COLOR_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(canvas, bg=COLOR_BG)
        window_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")

        def on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(window_id, width=canvas.winfo_width())

        self.inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window_id, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self._build_header(self.inner)
        self._build_divider(self.inner)
        self._build_info_vacante(self.inner)
        self._build_filtros_iniciales(self.inner)
        self._build_pesos(self.inner)
        self._build_keywords(self.inner)
        self._build_btn_iniciar(self.inner)
        self._build_progreso(self.inner)

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=COLOR_HEADER_BG, pady=10)
        header.pack(fill=tk.X)

        # Logo area
        logo_frame = tk.Frame(header, bg=COLOR_HEADER_BG, padx=12)
        logo_frame.pack(side=tk.LEFT)

        # 🔥 LOGO REAL (reemplaza el canvas)
        from PIL import Image, ImageTk

        ruta_logo = ruta_archivo("logo.png")
        image = Image.open(ruta_logo)

        # Ajusta tamaño (clave para que se vea bien horizontal)
        image = image.resize((140, 48), Image.LANCZOS)

        self.logo_img = ImageTk.PhotoImage(image)

        logo_label = tk.Label(
            logo_frame,
            image=self.logo_img,
            bg=COLOR_HEADER_BG
        )
        logo_label.pack(side=tk.LEFT, padx=(0, 15), pady=5)

        # Separador vertical
        tk.Frame(header, bg=COLOR_SEPARATOR, width=1).pack(
            side=tk.LEFT, fill=tk.Y, pady=4, padx=8
        )

        # Textos centrales
        center = tk.Frame(header, bg=COLOR_HEADER_BG)
        center.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Label(
            center,
            text="DEPTO. TECNOLOGÍA E INNOVACIÓN",
            font=FONT_DEPTO,
            fg=COLOR_DEPTO_FG,
            bg=COLOR_HEADER_BG
        ).pack(anchor="w")

        title_row = tk.Frame(center, bg=COLOR_HEADER_BG)
        title_row.pack(anchor="w")

        tk.Label(
            title_row,
            text="Filtrador de Hojas de Vida",
            font=FONT_TITLE,
            fg=COLOR_TEXT,
            bg=COLOR_HEADER_BG
        ).pack(side=tk.LEFT)

        tk.Label(
            title_row,
            text=" · ",
            font=FONT_TITLE,
            fg=COLOR_TEXT_LIGHT,
            bg=COLOR_HEADER_BG
        ).pack(side=tk.LEFT)

        tk.Label(
            title_row,
            text="Computrabajo",
            font=FONT_TITLE,
            fg=COLOR_TEXT,
            bg=COLOR_HEADER_BG
        ).pack(side=tk.LEFT)

        # Badge versión
        badge = tk.Label(
            header,
            text="  v1.0  ",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_VERSION_FG,
            bg=COLOR_VERSION_BG,
            padx=8,
            pady=4,
            relief="flat"
        )
        badge.pack(side=tk.RIGHT, padx=12, anchor="center")

    def _build_divider(self, parent):
        tk.Frame(parent, bg=COLOR_SEPARATOR, height=1).pack(fill=tk.X)

    # ── Card helper ────────────────────────────────────────────────────────────

    def _card(self, parent, title):
        """Crea una tarjeta blanca con sección de título."""
        card = tk.Frame(parent, bg=COLOR_WIDGET_BG,
                        highlightbackground=COLOR_SEPARATOR,
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=14, pady=(10, 0))

        sec = SectionFrame(card, title)
        sec.pack(fill=tk.X, padx=0, pady=0)

        tk.Frame(card, bg=COLOR_SEPARATOR, height=1).pack(fill=tk.X)

        body = tk.Frame(card, bg=COLOR_WIDGET_BG, padx=14, pady=10)
        body.pack(fill=tk.X)

        return body

    # ── Información de la vacante ───────────────────────────────────────────────

    def _build_info_vacante(self, parent):
        body = self._card(parent, "INFORMACIÓN DE LA VACANTE")

        self._labeled_entry(body, "Nombre de la vacante:", self.v_vacante,
                            width=36, row=0)
        entry_url = self._labeled_entry(body, "URL vacante Computrabajo:", self.v_url,
                                         width=36, row=1)

        self.entries_bloqueables.extend([
            self._get_entry_from_labeled(body, 0),
            entry_url,
        ])

    def _labeled_entry(self, parent, label, var, width=24, row=0):
        lbl = tk.Label(parent, text=label, font=FONT_NORMAL,
                       fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, anchor="w", width=22)
        lbl.grid(row=row, column=0, sticky="w", pady=3)

        e = StyledEntry(parent, textvariable=var, width=width)
        e.grid(row=row, column=1, sticky="ew", pady=3, padx=(0, 4))
        parent.columnconfigure(1, weight=1)
        return e

    def _get_entry_from_labeled(self, parent, row):
        """Devuelve el widget Entry en la fila indicada del grid."""
        for widget in parent.winfo_children():
            info = widget.grid_info()
            if info.get("row") == row and info.get("column") == 1:
                return widget
        return None

    # ── Filtros iniciales ──────────────────────────────────────────────────────

    def _build_filtros_iniciales(self, parent):
        vcmd_numeros = (self.root.register(self.validar_numeros), "%P")
        body = self._card(parent, "FILTROS INICIALES")

        # Edad
        row0 = tk.Frame(body, bg=COLOR_WIDGET_BG)
        row0.pack(fill=tk.X, pady=3)

        tk.Label(row0, text="Edad mínima (años):", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=22, anchor="w").pack(side=tk.LEFT)
        e_emin = StyledEntry(
            row0, textvariable=self.v_emin, width=10,
            validate="key",
            validatecommand=vcmd_numeros
        )

        e_emin.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(row0, text="Edad máxima (años):", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=20, anchor="w").pack(side=tk.LEFT)
        e_emax = StyledEntry(
            row0, textvariable=self.v_emax, width=10,
            validate="key",
            validatecommand=vcmd_numeros
        )
        e_emax.pack(side=tk.LEFT)

        # Salario
        row1 = tk.Frame(body, bg=COLOR_WIDGET_BG)
        row1.pack(fill=tk.X, pady=3)

        tk.Label(row1, text="Salario mínimo ($):", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=22, anchor="w").pack(side=tk.LEFT)
        e_smin = StyledEntry(row1, textvariable=self.v_smin, width=14)
        e_smin.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(row1, text="Salario máximo ($):", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=20, anchor="w").pack(side=tk.LEFT)
        e_smax = StyledEntry(row1, textvariable=self.v_smax, width=14)
        e_smax.pack(side=tk.LEFT)

        e_smin.bind("<KeyRelease>", lambda e: self.formatear_moneda(e, self.v_smin, e_smin))
        e_smin.bind("<FocusOut>",   lambda e: self.formatear_moneda(e, self.v_smin, e_smin))

        e_smax.bind("<KeyRelease>", lambda e: self.formatear_moneda(e, self.v_smax, e_smax))
        e_smax.bind("<FocusOut>",   lambda e: self.formatear_moneda(e, self.v_smax, e_smax))

        # Disponibilidad sábados
        row2 = tk.Frame(body, bg=COLOR_WIDGET_BG)
        row2.pack(fill=tk.X, pady=3)

        tk.Label(row2, text="Disponibilidad sábados:", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=22, anchor="w").pack(side=tk.LEFT)

        rb_req = tk.Radiobutton(row2, text="Requerido", variable=self.v_sab,
                                value=True, bg=COLOR_WIDGET_BG, fg=COLOR_TEXT,
                                font=FONT_NORMAL, activebackground=COLOR_WIDGET_BG,
                                selectcolor=COLOR_WIDGET_BG)
        rb_req.pack(side=tk.LEFT, padx=(0, 10))

        rb_noi = tk.Radiobutton(row2, text="No importa", variable=self.v_sab,
                                value=False, bg=COLOR_WIDGET_BG, fg=COLOR_TEXT,
                                font=FONT_NORMAL, activebackground=COLOR_WIDGET_BG,
                                selectcolor=COLOR_WIDGET_BG)
        rb_noi.pack(side=tk.LEFT)

        self.radios_sab = [rb_req, rb_noi]

        # Nota informativa
        tk.Label(body,
                 text="Candidatos sin salario o sin edad declarada pasan el filtro automáticamente.",
                 font=FONT_SMALL, fg=COLOR_TEXT_LIGHT, bg=COLOR_WIDGET_BG,
                 anchor="w").pack(fill=tk.X, pady=(4, 2))

        # Botón habilitar configuración
        self.btn_habilitar = OrangeButton(
            body, text="Habilitar configuración",
            command=self._habilitar_config)
        self.btn_habilitar.pack(anchor="w", pady=(6, 2))

        # Guardar referencias para bloqueo
        self.entries_bloqueables += [e_emin, e_emax, e_smin, e_smax]
        self._entries_filtros = [e_emin, e_emax, e_smin, e_smax]

    # ── Pesos de evaluación ────────────────────────────────────────────────────

    def _build_pesos(self, parent):
        vcmd_numeros = (self.root.register(self.validar_numeros), "%P")
        body = self._card(parent, "PESOS DE EVALUACIÓN")

        row = tk.Frame(body, bg=COLOR_WIDGET_BG)
        row.pack(fill=tk.X, pady=3)

        tk.Label(row, text="Peso experiencia laboral:", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=24, anchor="w").pack(side=tk.LEFT)

        e_peso_exp = StyledEntry(
            row, textvariable=self.v_peso_exp, width=10,
            validate="key",
            validatecommand=vcmd_numeros
        )
        e_peso_exp.pack(side=tk.LEFT)
        tk.Label(row, text="%", font=FONT_NORMAL, fg=COLOR_TEXT,
                 bg=COLOR_WIDGET_BG).pack(side=tk.LEFT, padx=(2, 20))

        tk.Label(row, text="Peso formación académica:", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=24, anchor="w").pack(side=tk.LEFT)

        e_peso_aca = StyledEntry(
            row,
            textvariable=self.v_peso_aca,
            width=5,
            validate="key",
            validatecommand=vcmd_numeros
        )
        e_peso_aca.pack(side=tk.LEFT)
        tk.Label(row, text="%", font=FONT_NORMAL, fg=COLOR_TEXT,
                 bg=COLOR_WIDGET_BG).pack(side=tk.LEFT, padx=2)

        tk.Label(body,
                 text="La suma de los pesos debe ser 100 %. Se usan para la puntuación ponderada del candidato.",
                 font=FONT_SMALL, fg=COLOR_TEXT_LIGHT, bg=COLOR_WIDGET_BG,
                 anchor="w").pack(fill=tk.X, pady=(4, 2))

    # ── Palabras clave ─────────────────────────────────────────────────────────

    def _build_keywords(self, parent):
        body = self._card(parent, "PALABRAS CLAVE DE CONTEXTO  (opcional)")

        row = tk.Frame(body, bg=COLOR_WIDGET_BG)
        row.pack(fill=tk.X, pady=3)

        tk.Label(row, text="Palabras clave:", font=FONT_NORMAL,
                 fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=16, anchor="w").pack(side=tk.LEFT)

        self.entry_keywords = StyledEntry(row, textvariable=self.v_keywords, width=48)
        self.entry_keywords.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(body,
                 text="Separadas por coma (,)  —  Ej: logística, operaciones, supply chain, almacén  ·  Generan bonus en el score.",
                 font=FONT_SMALL, fg=COLOR_TEXT_LIGHT, bg=COLOR_WIDGET_BG,
                 anchor="w").pack(fill=tk.X, pady=(4, 2))

        # Espacio inferior
        tk.Frame(parent, bg=COLOR_BG, height=6).pack()

    # ── Botón iniciar ──────────────────────────────────────────────────────────

    def _build_btn_iniciar(self, parent):
        frame = tk.Frame(parent, bg=COLOR_BG)
        frame.pack(fill=tk.X, padx=14, pady=(6, 0))

        self.btn_iniciar = OrangeButton(
            frame,
            text="▶  Iniciar filtrado de HVs",
            command=self.iniciar,
            font=("Segoe UI", 11, "bold"),
            pady=10,
        )
        self.btn_iniciar.pack(fill=tk.X)

    # ── Progreso ───────────────────────────────────────────────────────────────

    def _build_progreso(self, parent):
        card = tk.Frame(parent, bg=COLOR_WIDGET_BG,
                        highlightbackground=COLOR_SEPARATOR,
                        highlightthickness=1)
        card.pack(fill=tk.X, padx=14, pady=(10, 14))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Fertrac.Horizontal.TProgressbar",
                        troughcolor=COLOR_SEPARATOR,
                        background=COLOR_NARANJA,
                        lightcolor=COLOR_NARANJA,
                        darkcolor=COLOR_NARANJA_DARK,
                        bordercolor=COLOR_SEPARATOR,
                        thickness=12)

        labels = [
            ("Descargando hojas de vida",   0),
            ("Revisando hojas de vida",      1),
            ("Clasificando hojas de vida",   2),
            ("Subiendo carpetas a Drive",    3),
        ]

        pbars  = []
        checks = []
        cnts   = []

        for text, idx in labels:
            row = tk.Frame(card, bg=COLOR_WIDGET_BG)
            row.pack(fill=tk.X, padx=14, pady=4)

            tk.Label(row, text=text, font=FONT_NORMAL,
                     fg=COLOR_TEXT, bg=COLOR_WIDGET_BG, width=28,
                     anchor="w").pack(side=tk.LEFT)

            pb = ttk.Progressbar(row, mode="determinate", length=260,
                                 style="Fertrac.Horizontal.TProgressbar")
            pb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            pbars.append(pb)

            chk = tk.Label(row, text="", font=("Segoe UI", 10),
                           fg=COLOR_NARANJA, bg=COLOR_WIDGET_BG, width=3)
            chk.pack(side=tk.LEFT)
            checks.append(chk)

            cnt = tk.Label(row, text="", font=FONT_SMALL,
                           fg=COLOR_TEXT_LIGHT, bg=COLOR_WIDGET_BG, width=12)
            cnt.pack(side=tk.LEFT)
            cnts.append(cnt)

        self.pv1, self.pv2, self.pv3, self.pv4 = pbars
        self.lbl_check1, self.lbl_check2, self.lbl_check3, self.lbl_check4 = checks
        self.lbl_cnt1,   self.lbl_cnt2,   self.lbl_cnt3,   self.lbl_cnt4   = cnts

    # ── Lógica de caché ────────────────────────────────────────────────────────

    def _habilitar_config(self):
        print("CLICK EN HABILITAR CONFIG")

        # 🔥 Desbloquear TODOS los entries
        for widget in self.root.winfo_children():
            self._desbloquear_recursivo(widget)

        # 🔥 Variables internas
        self.usar_cache_filtros = False

        # Opcional: cambiar apariencia para feedback visual
        self.btn_habilitar.config(
            text="✔ Configuración habilitada",
            bg=COLOR_NARANJA,
            activebackground=COLOR_NARANJA_HOVER
        )

        self.btn_habilitar.default_bg = COLOR_NARANJA
        self.btn_habilitar.hover_bg   = COLOR_NARANJA_HOVER

        # 🔥 Restaurar botón iniciar
        self.btn_iniciar.config(
            text="▶  Iniciar filtrado de HVs",
            bg=COLOR_NARANJA,
            activebackground=COLOR_NARANJA_HOVER
        )

        self.btn_iniciar.default_bg = COLOR_NARANJA
        self.btn_iniciar.hover_bg   = COLOR_NARANJA_HOVER
        
    def _desbloquear_recursivo(self, widget):
        try:
            if isinstance(widget, (tk.Entry, tk.Radiobutton)):
                widget.config(state="normal")
        except:
            pass

        for child in widget.winfo_children():
            self._desbloquear_recursivo(child)
    def _bloquear_filtros(self):
        """Bloquea los campos que invalidan la caché."""
        for e in self.entries_bloqueables:
            if e:
                try:
                    e.config(state="disabled")
                except Exception:
                    pass
        for rb in self.radios_sab:
            rb.config(state="disabled")

    def _verificar_y_cargar_cache(self):
        """Carga la caché si existe (requiere gestor_cache)."""
        try:
            from gestor_cache import (
                cache_existe, obtener_config_guardada,
                mostrar_info_cache,
            )
        except ImportError:
            return

        if cache_existe():
            mostrar_info_cache()
            config = obtener_config_guardada()
            if config:
                self.v_vacante.set(config.get("vacante", ""))
                self.v_url.set(config.get("url_vacante", ""))
                self.v_emin.set(str(config.get("edad_min", "20")))
                self.v_emax.set(str(config.get("edad_max", "45")))

                sal_min = config.get("sal_min", 1750905)
                sal_max = config.get("sal_max", 3000000)
                self.v_smin.set(f"${sal_min:,.0f}".replace(",", "."))
                self.v_smax.set(f"${sal_max:,.0f}".replace(",", "."))

                self.v_peso_exp.set(str(config.get("peso_exp", "50")))
                self.v_peso_aca.set(str(config.get("peso_aca", "50")))
                self.v_keywords.set(config.get("palabras_clave", ""))
                self.v_sab.set(config.get("requiere_sabados", True))

                self._bloquear_filtros()
                self.usar_cache_filtros = True

                # Detectar modo y mostrar texto apropiado
                try:
                    from cache_runner import detectar_modo_cache
                    modo_cache, desc_cache = detectar_modo_cache()
                    textos = {
                        "f3": "⚡  Re-evaluar con caché", #(solo Filtro 3)
                        "f2": "⚡  Re-evaluar con caché", #Filtro 2 (PDFs en caché)",
                    }
                    texto_btn = textos.get(modo_cache, "⚡  Re-evaluar con caché")
                except Exception:
                    texto_btn = "⚡  Re-evaluar con caché"
               # DESPUÉS
                self.btn_habilitar.pack(anchor="w", pady=(6, 2))
                self.btn_habilitar.config(
                    text="⚠ Habilitar configuración",
                    bg="#4CAF50",
                    activebackground="#43a047"
                )
                self.btn_habilitar.default_bg = "#4CAF50"
                self.btn_habilitar.hover_bg   = "#43a047"

                self.btn_iniciar.config(
                    text=texto_btn,
                    bg="#28A745",
                    activebackground="#218838"
                )
                self.btn_iniciar.default_bg = "#28A745"
                self.btn_iniciar.hover_bg   = "#218838"


    # ── Métodos públicos de progreso ────────────────────────────────────────────

    def log(self, mensaje):
        pass  # Sin widget de log visible en este diseño; úsese print

    def actualizar_progreso(self, actual, total):
        pct = (actual / total) * 100 if total > 0 else 0
        self.pv1["value"] = pct
        self.lbl_cnt1.config(text=f"{actual}/{total}")
        self.root.update_idletasks()

    def barra1_terminada(self):
        self.pv1["value"] = 100
        self.lbl_check1.config(text="✓")
        self.lbl_cnt1.config(text="Finalizado")
        self.root.update_idletasks()

    def actualizar_progreso_ia(self, actual, total):
        pct = (actual / total) * 100 if total > 0 else 0
        self.pv2["value"] = pct
        self.lbl_cnt2.config(text=f"{actual}/{total}")
        self.root.update_idletasks()

    def barra2_terminada(self):
        self.pv2["value"] = 100
        self.lbl_check2.config(text="✓")
        self.lbl_cnt2.config(text="Finalizado")
        self.root.update_idletasks()

    def actualizar_progreso_clasificacion(self, actual, total):
        pct = (actual / total) * 100 if total > 0 else 0
        self.pv3["value"] = pct
        self.lbl_cnt3.config(text=f"{actual}/{total}")
        self.root.update_idletasks()

    def barra3_terminada(self):
        self.pv3["value"] = 100
        self.lbl_check3.config(text="✓")
        self.lbl_cnt3.config(text="Finalizado")
        self.root.update_idletasks()

    def actualizar_progreso_drive(self, actual, total):
        """Actualiza la barra de subida a Drive. Llamar con (archivos_subidos, total)."""
        pct = (actual / total) * 100 if total > 0 else 0
        self.pv4["value"] = pct
        self.lbl_cnt4.config(text=f"{actual}/{total}")
        self.root.update_idletasks()

    def barra4_iniciada(self):
        """Muestra la barra 4 en modo indeterminado mientras se sube a Drive."""
        self.pv4.config(mode="indeterminate")
        self.pv4.start(15)
        self.lbl_cnt4.config(text="Subiendo…")
        self.root.update_idletasks()

    def barra4_terminada(self, ok=True):
        """Detiene y llena la barra 4 al terminar la subida a Drive."""
        self.pv4.stop()
        self.pv4.config(mode="determinate")
        self.pv4["value"] = 100
        self.lbl_check4.config(text="✓" if ok else "✗",
                               fg=COLOR_NARANJA if ok else "#CC0000")
        self.lbl_cnt4.config(text="Finalizado" if ok else "Error")
        self.root.update_idletasks()

    def proceso_terminado(self, ok):
        if ok:
            # Si se generó caché, cambiar botón a verde inmediatamente
            try:
                from gestor_cache import cache_existe, obtener_ruta_ejecucion
                if cache_existe() and obtener_ruta_ejecucion():
                    self.usar_cache_filtros = True
                    self._bloquear_filtros()
                    try:
                        from cache_runner import detectar_modo_cache
                        modo_cache, _ = detectar_modo_cache()
                        textos = {
                            "f3": "⚡  Re-evaluar con caché", #(solo Filtro 3)
                            "f2": "⚡  Re-evaluar con caché", #Filtro 2 (PDFs en caché)"
                        }
                        texto_btn = textos.get(modo_cache, "⚡  Re-evaluar con caché")
                    except Exception:
                        texto_btn = "⚡  Re-evaluar con caché"
                    # DESPUÉS
                    self.btn_habilitar.pack(anchor="w", pady=(6, 2))
                    self.btn_habilitar.config(
                        text="⚠ Habilitar configuración",
                        bg="#4CAF50",
                        activebackground="#43a047"
                    )
                    self.btn_habilitar.default_bg = "#4CAF50"
                    self.btn_habilitar.hover_bg   = "#43a047"

                    self.btn_iniciar.config(
                        state="normal",
                        text=texto_btn,
                        bg="#28A745",
                        activebackground="#218838"
                    )
                    self.btn_iniciar.default_bg = "#28A745"
                    self.btn_iniciar.hover_bg   = "#218838"
                else:
                    self.btn_iniciar.config(state="normal", text="▶  Iniciar filtrado de HVs")
            except Exception:
                self.btn_iniciar.config(state="normal", text="▶  Iniciar filtrado de HVs")
            messagebox.showinfo(
                "Proceso completado",
                "El filtrado finalizó correctamente.\nRevisa la carpeta de resultados.")
        else:
            self.btn_iniciar.config(state="normal", text="▶  Iniciar filtrado de HVs")
            messagebox.showerror(
                "Error en el proceso",
                "El proceso terminó con errores.\nRevisa el archivo log_filtrador.txt.")

    # ── Iniciar proceso ────────────────────────────────────────────────────────

    def iniciar(self):
        vacante = self.v_vacante.get().strip()
        url     = self.v_url.get().strip()

        if not vacante or not url:
            messagebox.showwarning(
                "Campos requeridos",
                "Completa el nombre de la vacante y la URL.")
            return

        try:
            peso_exp = int(self.v_peso_exp.get())
            peso_aca = int(self.v_peso_aca.get())
        except ValueError:
            messagebox.showerror("Error", "Los pesos deben ser números enteros.")
            return

        if peso_exp + peso_aca != 100:
            messagebox.showwarning(
                "Pesos inválidos",
                f"La suma de los pesos debe ser 100 %.\n"
                f"Actualmente: {peso_exp} + {peso_aca} = {peso_exp + peso_aca} %")
            return

        try:
            cfg = {
                "vacante":       vacante,
                "url_vacante":   url,

                "edad_min":      int(self.v_emin.get()),
                "edad_max":      int(self.v_emax.get()),

                "sal_min":       self.obtener_salario_int(self.v_smin),
                "sal_max":       self.obtener_salario_int(self.v_smax),

                # 🔥 NOMBRES CORRECTOS
                "sabados":             self.v_sab.get(),
                "peso_experiencia":    peso_exp,
                "peso_academico":      peso_aca,
                "keywords":            self.v_keywords.get().strip(),
            }
        except ValueError:
            messagebox.showerror("Error", "Verifica que edad y salario sean números válidos.")
            return

        self.btn_iniciar.config(state="disabled", text="⏳  Procesando…")
        for pb in (self.pv1, self.pv2, self.pv3, self.pv4):
            pb.config(mode="determinate")
            pb["value"] = 0
        for lbl in (self.lbl_check1, self.lbl_check2, self.lbl_check3, self.lbl_check4,
                    self.lbl_cnt1,   self.lbl_cnt2,   self.lbl_cnt3,   self.lbl_cnt4):
            lbl.config(text="")

        try:
            from gestor_cache import guardar_config
            guardar_config(cfg)
        except ImportError:
            pass

        cfg["_usar_cache"] = self.usar_cache_filtros

        print("🔥 BOTÓN PRESIONADO")
        print("CFG ENVIADO:", cfg)

        self.callback_iniciar(cfg, self)

# ── Entry point de prueba ──────────────────────────────────────────────────────

if __name__ == "__main__":
    from main import iniciar_proceso_thread  # 🔥 flujo real

    # --- Callback de prueba (NO BORRAR) ---
    def dummy_callback(cfg, ui):
        import threading, time

        def run():
            total = 20
            for i in range(1, total + 1):
                time.sleep(0.05)
                ui.actualizar_progreso(i, total)
            ui.barra1_terminada()

            for i in range(1, total + 1):
                time.sleep(0.05)
                ui.actualizar_progreso_ia(i, total)
            ui.barra2_terminada()

            for i in range(1, total + 1):
                time.sleep(0.05)
                ui.actualizar_progreso_clasificacion(i, total)
            ui.barra3_terminada()

            root.after(100, lambda: ui.proceso_terminado(True))

        threading.Thread(target=run, daemon=True).start()

    root = tk.Tk()

    # 🔥 USO REAL (PRODUCCIÓN)
    app = AppUI(root, iniciar_proceso_thread)

    # 👇 OPCIONAL: para pruebas visuales (solo si quieres)
    # app = AppUI(root, dummy_callback)

    root.mainloop()
