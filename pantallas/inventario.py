import sqlite3
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from database import (
    agregar_categoria,
    agregar_producto,
    editar_producto,
    listar_categorias,
    listar_productos,
)
from pantallas.formato import formatear_pesos, leer_importe


FONDO = "#111315"
PANEL = "#1b1d1f"
PANEL_SECUNDARIO = "#202224"
BORDES = "#2c2f31"
TEXTO = "#eeeeee"
TEXTO_SUAVE = "#969a9d"
ACENTO = "#00c9b7"
ROJO = "#e36b72"


def _formatear_entrada_precio(evento: tk.Event) -> None:
    entrada = evento.widget
    texto = entrada.get()
    if not texto or any(not caracter.isdecimal() and caracter != "." for caracter in texto):
        return
    # Al agregar puntos de miles, el cursor se ubica según los dígitos que tenía antes.
    posicion = entrada.index(tk.INSERT)
    digitos_antes = sum(caracter.isdecimal() for caracter in texto[:posicion])
    digitos = "".join(caracter for caracter in texto if caracter.isdecimal())
    if not digitos:
        return
    valor = int(digitos)
    formateado = f"{valor:,}".replace(",", ".")
    nueva_posicion = 0
    digitos_contados = 0
    while nueva_posicion < len(formateado) and digitos_contados < digitos_antes:
        if formateado[nueva_posicion].isdecimal():
            digitos_contados += 1
        nueva_posicion += 1
    entrada.delete(0, "end")
    entrada.insert(0, formateado)
    entrada.icursor(nueva_posicion)


def _limpiar_entrada_numerica(evento: tk.Event) -> None:
    entrada = evento.widget
    # Al enfocar el campo se puede reemplazar el valor completo sin borrarlo a mano.
    entrada._valor_anterior = entrada.get()
    entrada.delete(0, "end")


def _restaurar_entrada_numerica(evento: tk.Event) -> None:
    entrada = evento.widget
    # Si no se escribió un valor nuevo, se conserva el que ya tenía el campo.
    if not entrada.get():
        entrada.insert(0, entrada._valor_anterior)


def _crear_pildora(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, color: str) -> None:
    # Se dibuja una cápsula con una linea central y extremos redondos.
    radio = min((x2 - x1) / 2, (y2 - y1) / 2)
    if x2 - x1 > 2 * radio:
        canvas.create_rectangle(
            x1 + radio, y1, x2 - radio, y2, fill=color, outline=color
        )
    canvas.create_oval(x1, y1, x1 + 2 * radio, y2, fill=color, outline=color)
    canvas.create_oval(x2 - 2 * radio, y1, x2, y2, fill=color, outline=color)


class PantallaInventario(ctk.CTkFrame):
    def __init__(self, master, mostrar_barra_lateral: bool = True):
        super().__init__(master, fg_color=FONDO, corner_radius=0)
        # Estos valores guardan los filtros actuales mientras se actualiza la tabla.
        self.categoria_seleccionada: int | None = None
        self.estado_seleccionado = "Todos los estados"
        self._temporizador_busqueda: str | None = None
        self._inicio_barra_categorias = 0.0
        self._fin_barra_categorias = 1.0
        self._desfase_barra_categorias = 0.0

        if mostrar_barra_lateral:
            self._crear_barra_lateral()
        self._crear_contenido()
        self.actualizar()

    def _crear_barra_lateral(self) -> None:
        # La barra lateral identifica la sección abierta y muestra la navegación.
        barra = ctk.CTkFrame(self, width=180, fg_color="#17191a", corner_radius=0)
        barra.pack(side="left", fill="y")
        barra.pack_propagate(False)

        marca = ctk.CTkFrame(barra, fg_color="transparent")
        marca.pack(fill="x", padx=16, pady=(20, 28))
        ctk.CTkLabel(
            marca,
            text="▣",
            text_color=ACENTO,
            font=("Arial", 24, "bold"),
        ).pack(side="left", padx=(0, 9))
        ctk.CTkLabel(
            marca, text="POS-Kontrol", text_color=TEXTO, font=("Arial", 16, "bold")
        ).pack(side="left")

        ctk.CTkLabel(
            barra, text="OPERACIÓN", text_color=TEXTO_SUAVE, anchor="w",
            font=("Arial", 10, "bold")
        ).pack(fill="x", padx=18, pady=(0, 8))

        for texto in ("Punto de venta", "Inventario", "Ventas"):
            activo = texto == "Inventario"
            ctk.CTkLabel(
                barra,
                text=f"  ◈  {texto}",
                anchor="w",
                height=36,
                corner_radius=7,
                fg_color="#123b37" if activo else "transparent",
                text_color=ACENTO if activo else TEXTO_SUAVE,
                font=("Arial", 12, "bold" if activo else "normal"),
            ).pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(
            barra, text="ADMINISTRACIÓN", text_color=TEXTO_SUAVE, anchor="w",
            font=("Arial", 10, "bold")
        ).pack(fill="x", padx=18, pady=(24, 8))
        for texto in ("Reportes", "Configuración"):
            ctk.CTkLabel(
                barra,
                text=f"  ◈  {texto}",
                anchor="w",
                height=34,
                text_color=TEXTO_SUAVE,
                font=("Arial", 12),
            ).pack(fill="x", padx=10, pady=1)

    def _crear_contenido(self) -> None:
        # Aquí se organizan la búsqueda, los filtros, los indicadores y la tabla.
        contenido = ctk.CTkFrame(self, fg_color=FONDO, corner_radius=0)
        contenido.pack(side="left", fill="both", expand=True, padx=20, pady=18)

        encabezado = ctk.CTkFrame(contenido, fg_color="transparent")
        encabezado.pack(fill="x", pady=(0, 14))
        textos = ctk.CTkFrame(encabezado, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            textos,
            text="Gestión de Inventario",
            text_color=TEXTO,
            font=("Arial", 25, "bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            textos,
            text="Consulta tus productos, existencias y precios.",
            text_color=TEXTO_SUAVE,
            font=("Arial", 12),
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))
        ctk.CTkButton(
            encabezado,
            text="Nuevo producto  +",
            width=150,
            height=38,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            font=("Arial", 12, "bold"),
            command=self._abrir_formulario_producto,
        ).pack(side="right", padx=(10, 0))

        controles = ctk.CTkFrame(contenido, fg_color="transparent")
        controles.pack(fill="x", pady=(0, 12))
        self.campo_busqueda = ctk.CTkEntry(
            controles,
            placeholder_text="Buscar por nombre, SKU o referencia...",
            placeholder_text_color=TEXTO_SUAVE,
            height=36,
        )
        self.campo_busqueda.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.campo_busqueda.bind("<KeyRelease>", self._programar_busqueda)
        self.filtro_estado = ctk.CTkOptionMenu(
            controles,
            values=["Todos los estados", "En stock", "Stock bajo"],
            width=150,
            height=36,
            fg_color=PANEL_SECUNDARIO,
            button_color=PANEL_SECUNDARIO,
            button_hover_color=BORDES,
            command=self._cambiar_estado,
        )
        self.filtro_estado.set(self.estado_seleccionado)
        self.filtro_estado.pack(side="right")

        fila_categorias = ctk.CTkFrame(contenido, fg_color="transparent")
        fila_categorias.pack(fill="x", pady=(0, 14))
        fila_categorias.grid_columnconfigure(0, weight=1)
        self.botones_categorias = ctk.CTkScrollableFrame(
            fila_categorias,
            height=42,
            orientation="horizontal",
            fg_color="transparent",
            scrollbar_fg_color="#303638",
            scrollbar_button_color=ACENTO,
            scrollbar_button_hover_color="#00ead6",
        )
        self.botones_categorias._scrollbar.grid_remove()
        self._barra_categorias = tk.Canvas(
            self.botones_categorias._parent_frame,
            height=12,
            bg=FONDO,
            highlightthickness=0,
            borderwidth=0,
        )
        # La barra nativa se oculta y se dibuja una cápsula para que combine con el tema.
        self._barra_categorias.grid(row=2, column=0, sticky="ew", padx=0, pady=1)
        self._barra_categorias.bind("<Configure>", self._redibujar_barra_categorias)
        self._barra_categorias.bind("<Button-1>", self._iniciar_desplazamiento_categorias)
        self._barra_categorias.bind("<B1-Motion>", self._desplazar_categorias)
        self.botones_categorias._parent_canvas.configure(
            xscrollcommand=self._actualizar_barra_categorias
        )
        self.botones_categorias.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            fila_categorias,
            text="+ Categoría",
            width=100,
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=BORDES,
            text_color=TEXTO,
            hover_color=PANEL_SECUNDARIO,
            command=self._abrir_formulario_categoria,
        ).grid(row=0, column=1, padx=(8, 0))

        self.tarjetas = ctk.CTkFrame(contenido, fg_color="transparent")
        self.tarjetas.pack(fill="x", pady=(0, 14))
        self.tarjetas.grid_columnconfigure((0, 1, 2), weight=1, uniform="tarjetas")

        self.tarjeta_total = self._crear_tarjeta(self.tarjetas, 0, "Productos")
        self.tarjeta_bajo = self._crear_tarjeta(self.tarjetas, 1, "Alerta de stock bajo")
        self.tarjeta_valor = self._crear_tarjeta(
            self.tarjetas, 2, "Valor del inventario (costo)"
        )

        tabla = ctk.CTkFrame(
            contenido,
            fg_color=PANEL,
            border_width=1,
            border_color=BORDES,
            corner_radius=9,
        )
        self.tabla = tabla
        tabla.pack(fill="both", expand=True)
        titulo_tabla = ctk.CTkFrame(tabla, fg_color="transparent")
        titulo_tabla.pack(fill="x", padx=14, pady=(10, 7))
        ctk.CTkLabel(
            titulo_tabla,
            text="Productos",
            text_color=TEXTO,
            font=("Arial", 14, "bold"),
        ).pack(side="left")
        self.etiqueta_cantidad = ctk.CTkLabel(
            titulo_tabla, text="", text_color=TEXTO_SUAVE, font=("Arial", 11)
        )
        self.etiqueta_cantidad.pack(side="left", padx=8)

        self.encabezado_tabla = ctk.CTkFrame(tabla, fg_color=PANEL_SECUNDARIO)
        self.encabezado_tabla.pack(fill="x", padx=(4, 21))
        columnas = [
            ("Código", 1.0),
            ("Nombre", 2.0),
            ("Categoría", 1.15),
            ("Stock", 0.65),
            ("Costo", 0.85),
            ("Venta", 0.85),
            ("Estado", 0.9),
            ("Acción", 0.7),
        ]
        # Los pesos mantienen proporciones y anchos compartidos entre títulos y filas.
        self._pesos_columnas = [peso for _, peso in columnas]
        for indice, (nombre, peso) in enumerate(columnas):
            self.encabezado_tabla.grid_columnconfigure(
                indice, weight=int(peso * 100)
            )
            ctk.CTkLabel(
                self.encabezado_tabla,
                text=nombre,
                text_color=TEXTO_SUAVE,
                font=("Arial", 10, "bold"),
                anchor="center",
                justify="center",
            ).grid(row=0, column=indice, sticky="ew", padx=4, pady=10)

        self.filas = ctk.CTkScrollableFrame(
            tabla, fg_color="transparent", corner_radius=0
        )
        self.filas.pack(fill="both", expand=True, padx=4, pady=3)
        for indice, (_, peso) in enumerate(columnas):
            self.filas.grid_columnconfigure(indice, weight=int(peso * 100))
        self._ajuste_columnas_programado = False
        tabla.bind("<Configure>", self._programar_ajuste_columnas)
        self.filas._parent_canvas.bind(
            "<Configure>", self._programar_ajuste_columnas, add="+"
        )
        self.after_idle(self._ajustar_columnas_tabla)

        self.etiqueta_pie = ctk.CTkLabel(
            tabla, text="", text_color=TEXTO_SUAVE, anchor="w", font=("Arial", 10)
        )
        self.etiqueta_pie.pack(fill="x", padx=14, pady=(4, 10))

    def _crear_tarjeta(
        self, contenedor: ctk.CTkFrame, columna: int, titulo: str
    ) -> ctk.CTkLabel:
        tarjeta = ctk.CTkFrame(
            contenedor,
            fg_color=PANEL,
            border_width=1,
            border_color=BORDES,
            corner_radius=9,
        )
        tarjeta.grid(row=0, column=columna, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(
            tarjeta, text=titulo, text_color=TEXTO_SUAVE, anchor="w",
            font=("Arial", 11)
        ).pack(fill="x", padx=14, pady=(12, 4))
        valor = ctk.CTkLabel(
            tarjeta, text="0", text_color=TEXTO, anchor="w",
            font=("Arial", 21, "bold")
        )
        valor.pack(fill="x", padx=14, pady=(0, 12))
        return valor

    def _programar_ajuste_columnas(self, evento: tk.Event) -> None:
        if (
            evento.widget in (self.tabla, self.filas._parent_canvas)
            and not self._ajuste_columnas_programado
        ):
            # Se espera a que termine el cambio de tamaño antes de medir las columnas.
            self._ajuste_columnas_programado = True
            self.after_idle(self._ajustar_columnas_tabla)

    def _ajustar_columnas_tabla(self) -> None:
        self._ajuste_columnas_programado = False
        self.update_idletasks()

        # Cada columna debe caber al menos en su dato más ancho o en su encabezado.
        anchos_minimos = [0] * len(self._pesos_columnas)
        for contenedor in (self.encabezado_tabla, self.filas):
            for widget in contenedor.grid_slaves():
                info = widget.grid_info()
                try:
                    columna = int(info["column"])
                    extension = int(info.get("columnspan", 1))
                except (KeyError, ValueError):
                    continue
                if extension != 1 or not 0 <= columna < len(anchos_minimos):
                    continue

                padx = info.get("padx", 0)
                espacio_lateral = (
                    sum(int(valor) for valor in padx)
                    if isinstance(padx, tuple)
                    else int(padx) * 2
                )
                anchos_minimos[columna] = max(
                    anchos_minimos[columna],
                    widget.winfo_reqwidth() + espacio_lateral,
                )

        # Se aplican los mismos anchos en el encabezado y en las filas.
        for indice, peso in enumerate(self._pesos_columnas):
            for contenedor in (self.encabezado_tabla, self.filas):
                contenedor.grid_columnconfigure(
                    indice,
                    minsize=anchos_minimos[indice],
                    weight=int(peso * 100),
                    uniform="",
                )

    def _redibujar_barra_categorias(self, evento: tk.Event) -> None:
        if evento.widget is self._barra_categorias:
            self._dibujar_barra_categorias()

    def _dibujar_barra_categorias(self) -> None:
        ancho = self._barra_categorias.winfo_width()
        alto = self._barra_categorias.winfo_height()
        if ancho <= 1 or alto <= 1:
            return

        margen = 2
        y1 = margen
        y2 = alto - margen
        self._barra_categorias.delete("all")
        _crear_pildora(self._barra_categorias, 0, y1, ancho, y2, "#303638")

        # El control turquesa representa la parte de categorías que se ve en pantalla.
        ancho_control = max(
            y2 - y1,
            ancho * (self._fin_barra_categorias - self._inicio_barra_categorias),
        )
        inicio = ancho * self._inicio_barra_categorias
        fin = inicio + ancho_control
        fin = min(ancho, fin)
        inicio = max(0, fin - ancho_control)
        _crear_pildora(self._barra_categorias, inicio, y1, fin, y2, ACENTO)

    def _actualizar_barra_categorias(self, inicio: str, fin: str) -> None:
        self._inicio_barra_categorias = float(inicio)
        self._fin_barra_categorias = float(fin)
        self._dibujar_barra_categorias()

    def _iniciar_desplazamiento_categorias(self, evento: tk.Event) -> None:
        ancho = self._barra_categorias.winfo_width()
        fraccion_visible = self._fin_barra_categorias - self._inicio_barra_categorias
        ancho_control = ancho * fraccion_visible
        posicion_control = ancho * self._inicio_barra_categorias
        if posicion_control <= evento.x <= posicion_control + ancho_control:
            # Se conserva dónde se tomó el control para que no salte al arrastrarlo.
            self._desfase_barra_categorias = evento.x - posicion_control
        else:
            # Si se hace clic fuera del control, se centra en ese punto.
            self._desfase_barra_categorias = ancho_control / 2
            self._mover_barra_categorias(evento.x)

    def _desplazar_categorias(self, evento: tk.Event) -> None:
        self._mover_barra_categorias(evento.x)

    def _mover_barra_categorias(self, posicion: int) -> None:
        ancho = self._barra_categorias.winfo_width()
        if ancho <= 0:
            return
        fraccion_visible = self._fin_barra_categorias - self._inicio_barra_categorias
        maximo_inicio = 1 - fraccion_visible
        inicio = (posicion - self._desfase_barra_categorias) / ancho
        # Se limita el desplazamiento para que no queden espacios vacíos en los extremos.
        inicio = max(0.0, min(maximo_inicio, inicio))
        self.botones_categorias._parent_canvas.xview_moveto(inicio)

    def _programar_busqueda(self, _evento: tk.Event) -> None:
        if _evento.widget is not self.campo_busqueda._entry:
            return
        # Se espera un momento después de cada tecla para evitar consultas innecesarias.
        if self._temporizador_busqueda is not None:
            self.after_cancel(self._temporizador_busqueda)
        self._temporizador_busqueda = self.after(250, self.actualizar)

    def _cambiar_estado(self, estado: str) -> None:
        self.estado_seleccionado = estado
        self.actualizar()

    def _seleccionar_categoria(self, categoria_id: int | None) -> None:
        self.categoria_seleccionada = categoria_id
        self.actualizar()

    def _actualizar_filtros_categoria(self, categorias, productos) -> None:
        for widget in self.botones_categorias.winfo_children():
            widget.destroy()

        # Se cuenta cuántos productos hay en cada categoría para mostrarlo en el filtro.
        conteos = {}
        for producto in productos:
            categoria_id = producto["categoria_id"]
            conteos[categoria_id] = conteos.get(categoria_id, 0) + 1

        filtros = [(None, f"Todos  {len(productos)}")]
        filtros.extend(
            (categoria["id"], f"{categoria['nombre']}  {conteos.get(categoria['id'], 0)}")
            for categoria in categorias
        )
        for categoria_id, texto in filtros:
            activo = categoria_id == self.categoria_seleccionada
            ctk.CTkButton(
                self.botones_categorias,
                text=texto,
                width=max(72, min(150, len(texto) * 8)),
                height=30,
                fg_color="#123b37" if activo else "transparent",
                border_width=1,
                border_color=ACENTO if activo else BORDES,
                text_color=ACENTO if activo else TEXTO,
                hover_color=PANEL_SECUNDARIO,
                command=lambda valor=categoria_id: self._seleccionar_categoria(valor),
            ).pack(side="left", padx=(0, 6))

    def actualizar(self) -> None:
        self._temporizador_busqueda = None
        try:
            # Se cargan todos los productos para las tarjetas y los resultados de búsqueda.
            categorias = listar_categorias()
            todos = listar_productos()
            resultados = listar_productos(self.campo_busqueda.get())
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo cargar el inventario:\n{error}",
                parent=self.winfo_toplevel(),
            )
            return

        if self.categoria_seleccionada is not None and not any(
            categoria["id"] == self.categoria_seleccionada
            for categoria in categorias
        ):
            self.categoria_seleccionada = None

        self._actualizar_filtros_categoria(categorias, todos)
        bajos = [
            producto for producto in todos
            if producto["stock"] <= producto["stock_minimo"]
        ]
        valor_inventario = sum(
            producto["stock"] * producto["precio_costo"] for producto in todos
        )
        self.tarjeta_total.configure(text=str(len(todos)))
        self.tarjeta_bajo.configure(
            text=f"{len(bajos)} requieren reposición",
            text_color=ROJO if bajos else TEXTO,
        )
        self.tarjeta_valor.configure(text=formatear_pesos(valor_inventario))

        # La búsqueda, la categoría y el estado se aplican juntos a la lista visible.
        filtrados = resultados
        if self.categoria_seleccionada is not None:
            filtrados = [
                producto for producto in filtrados
                if producto["categoria_id"] == self.categoria_seleccionada
            ]
        if self.estado_seleccionado == "En stock":
            filtrados = [
                producto for producto in filtrados
                if producto["stock"] > producto["stock_minimo"]
            ]
        elif self.estado_seleccionado == "Stock bajo":
            filtrados = [
                producto for producto in filtrados
                if producto["stock"] <= producto["stock_minimo"]
            ]

        for widget in self.filas.winfo_children():
            widget.destroy()
        if filtrados:
            for numero, producto in enumerate(filtrados):
                self._crear_fila_producto(numero, producto)
        else:
            ctk.CTkLabel(
                self.filas,
                text="No hay productos para mostrar. Agrega uno para comenzar.",
                text_color=TEXTO_SUAVE,
                font=("Arial", 12),
            ).grid(row=0, column=0, columnspan=8, pady=36)

        self.etiqueta_cantidad.configure(text=str(len(filtrados)))
        self.etiqueta_pie.configure(
            text=f"Mostrando {len(filtrados)} de {len(todos)} productos"
        )
        self.after_idle(self._ajustar_columnas_tabla)

    def _crear_fila_producto(self, numero: int, producto) -> None:
        ctk.CTkLabel(
            self.filas, text=producto["codigo"], text_color=TEXTO_SUAVE,
            anchor="center", font=("Arial", 10)
        ).grid(row=numero, column=0, sticky="ew", padx=4, pady=11)
        ctk.CTkLabel(
            self.filas, text=producto["nombre"], text_color=TEXTO,
            anchor="center", font=("Arial", 11)
        ).grid(row=numero, column=1, sticky="ew", padx=4, pady=11)
        ctk.CTkLabel(
            self.filas, text=producto["categoria"], text_color=TEXTO_SUAVE,
            anchor="center", font=("Arial", 10)
        ).grid(row=numero, column=2, sticky="ew", padx=4, pady=11)
        ctk.CTkLabel(
            self.filas, text=f"{producto['stock']} uds.", text_color=(
                ROJO if producto["stock"] <= producto["stock_minimo"] else TEXTO
            ),
            anchor="center", font=("Arial", 10, "bold")
        ).grid(row=numero, column=3, sticky="ew", padx=4, pady=11)
        ctk.CTkLabel(
            self.filas, text=formatear_pesos(producto["precio_costo"]),
            text_color=TEXTO_SUAVE, anchor="center", font=("Arial", 10)
        ).grid(row=numero, column=4, sticky="ew", padx=4, pady=11)
        ctk.CTkLabel(
            self.filas, text=formatear_pesos(producto["precio_venta"]),
            text_color=TEXTO_SUAVE, anchor="center", font=("Arial", 10)
        ).grid(row=numero, column=5, sticky="ew", padx=4, pady=11)
        # El estado depende del mínimo que se configuró para este producto.
        bajo = producto["stock"] <= producto["stock_minimo"]
        ctk.CTkLabel(
            self.filas,
            text="Stock bajo" if bajo else "En stock",
            text_color=ROJO if bajo else ACENTO,
            fg_color="#3a2427" if bajo else "#123b37",
            corner_radius=5,
            font=("Arial", 9),
        ).grid(row=numero, column=6, pady=8)
        ctk.CTkButton(
            self.filas,
            text="Editar",
            width=54,
            height=28,
            fg_color="transparent",
            hover_color=PANEL_SECUNDARIO,
            text_color=ACENTO,
            command=lambda item=producto: self._abrir_formulario_producto(item),
        ).grid(row=numero, column=7, pady=7)
        ctk.CTkFrame(
            self.filas, height=1, fg_color=BORDES
        ).grid(row=numero, column=0, columnspan=8, sticky="sew")
        self.filas.grid_rowconfigure(numero, weight=0)

    def _abrir_formulario_categoria(self) -> None:
        # La ventana es modal para completar la categoría antes de volver al inventario.
        ventana = ctk.CTkToplevel(self)
        ventana.title("Nueva categoría")
        ventana.geometry("360x190")
        ventana.resizable(False, False)
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        ctk.CTkLabel(
            ventana, text="Crear categoría", font=("Arial", 18, "bold")
        ).pack(anchor="w", padx=20, pady=(20, 12))
        entrada = ctk.CTkEntry(ventana, placeholder_text="Nombre de la categoría")
        entrada.pack(fill="x", padx=20)
        entrada.focus()

        def guardar() -> None:
            try:
                categoria_id = agregar_categoria(entrada.get())
            except ValueError as error:
                messagebox.showwarning("Dato requerido", str(error), parent=ventana)
            except sqlite3.IntegrityError:
                messagebox.showwarning(
                    "Categoría existente",
                    "Ya hay una categoría con ese nombre.",
                    parent=ventana,
                )
            else:
                self.categoria_seleccionada = categoria_id
                ventana.destroy()
                self.actualizar()

        ctk.CTkButton(
            ventana, text="Guardar categoría", command=guardar,
            fg_color=ACENTO, text_color="#101616"
        ).pack(anchor="e", padx=20, pady=16)

    def _abrir_formulario_producto(self, producto=None) -> None:
        # El mismo formulario sirve para registrar un producto nuevo o editar uno existente.
        categorias = listar_categorias()
        if not categorias:
            messagebox.showinfo(
                "Falta una categoría",
                "Crea una categoría antes de registrar un producto.",
                parent=self.winfo_toplevel(),
            )
            self._abrir_formulario_categoria()
            return

        ventana = ctk.CTkToplevel(self)
        ventana.title("Editar producto" if producto else "Nuevo producto")
        ventana.geometry("440x640")
        ventana.resizable(False, False)
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        ctk.CTkLabel(
            ventana,
            text="Editar producto" if producto else "Nuevo producto",
            font=("Arial", 19, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 14))

        # El selector muestra nombres, pero se guarda el identificador de la categoría.
        nombres_categoria = {
            categoria["nombre"]: categoria["id"] for categoria in categorias
        }
        valores = {
            "Nombre del producto": producto["nombre"] if producto else "",
            "Existencias": str(producto["stock"]) if producto else "0",
            "Precio de costo": (
                str(producto["precio_costo"]) if producto else "0"
            ),
            "Precio de venta": (
                str(producto["precio_venta"]) if producto else "0"
            ),
            "Stock mínimo": (
                str(producto["stock_minimo"]) if producto else "2"
            ),
            "Código de barras (opcional)": (
                producto["codigo_barras"] or "" if producto else ""
            ),
        }
        entradas = {}
        for etiqueta, valor in valores.items():
            ctk.CTkLabel(
                ventana, text=etiqueta, text_color=TEXTO_SUAVE,
                anchor="w", font=("Arial", 11)
            ).pack(fill="x", padx=22, pady=(5, 3))
            entrada = ctk.CTkEntry(ventana, height=34)
            entrada.insert(0, valor)
            entrada.pack(fill="x", padx=22)
            if etiqueta in (
                "Existencias",
                "Precio de costo",
                "Precio de venta",
                "Stock mínimo",
            ):
                # Al enfocar un campo numérico se limpia; si queda vacío se restaura el valor.
                entrada._valor_anterior = valor
                entrada.bind("<FocusIn>", _limpiar_entrada_numerica)
                entrada.bind("<FocusOut>", _restaurar_entrada_numerica)
            if etiqueta in ("Precio de costo", "Precio de venta"):
                entrada.bind("<KeyRelease>", _formatear_entrada_precio)
                entrada.bind("<FocusOut>", _formatear_entrada_precio, add="+")
            entradas[etiqueta] = entrada

        ctk.CTkLabel(
            ventana, text="Categoría", text_color=TEXTO_SUAVE,
            anchor="w", font=("Arial", 11)
        ).pack(fill="x", padx=22, pady=(8, 3))
        categoria_var = tk.StringVar(
            value=producto["categoria"]
            if producto
            else categorias[0]["nombre"]
        )
        selector_categoria = ctk.CTkOptionMenu(
            ventana,
            variable=categoria_var,
            values=list(nombres_categoria),
            height=34,
            fg_color=PANEL_SECUNDARIO,
            button_color=BORDES,
            button_hover_color="#3a3e40",
            text_color=TEXTO,
            dropdown_fg_color=PANEL,
            dropdown_hover_color="#123b37",
            dropdown_text_color=TEXTO,
            font=("Arial", 11),
            dropdown_font=("Arial", 11),
        )
        selector_categoria.pack(fill="x", padx=22)
        selector_categoria._dropdown_menu.configure(min_character_width=48)

        def guardar() -> None:
            try:
                # Se leen y validan todos los campos antes de llamar a la base de datos.
                datos = (
                    entradas["Nombre del producto"].get(),
                    nombres_categoria[categoria_var.get()],
                    int(entradas["Existencias"].get()),
                    leer_importe(entradas["Precio de costo"].get()),
                    leer_importe(entradas["Precio de venta"].get()),
                    int(entradas["Stock mínimo"].get()),
                    entradas["Código de barras (opcional)"].get(),
                )
                if producto:
                    editar_producto(producto["id"], *datos)
                else:
                    codigo_sku = agregar_producto(*datos)
            except ValueError as error:
                messagebox.showwarning(
                    "Revisa los datos",
                    f"Verifica que los campos numéricos sean enteros y no negativos.\n{error}",
                    parent=ventana,
                )
            except sqlite3.IntegrityError:
                messagebox.showwarning(
                    "No se pudo guardar",
                    "El código de barras ya está asignado a otro producto "
                    "o la categoría no es válida.",
                    parent=ventana,
                )
            except LookupError as error:
                messagebox.showwarning("Producto no encontrado", str(error), parent=ventana)
            else:
                ventana.destroy()
                self.actualizar()
                if not producto:
                    messagebox.showinfo(
                        "Producto registrado",
                        f"El SKU asignado es {codigo_sku}.",
                        parent=self.winfo_toplevel(),
                    )

        ctk.CTkButton(
            ventana,
            text="Guardar cambios" if producto else "Guardar producto",
            height=38,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            command=guardar,
        ).pack(fill="x", padx=22, pady=18)
