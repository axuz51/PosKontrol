import sqlite3
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from database import (
    agregar_proveedor,
    editar_compra,
    listar_categorias,
    listar_compras,
    listar_ediciones_compra,
    listar_productos,
    listar_proveedores,
    obtener_detalle_compra,
    registrar_compra,
)
from pantallas.formato import (
    formatear_entrada_precio,
    formatear_numero,
    formatear_pesos,
    leer_importe,
)


FONDO = "#111315"
PANEL = "#1b1d1f"
PANEL_SECUNDARIO = "#202224"
BORDES = "#2c2f31"
TEXTO = "#eeeeee"
TEXTO_SUAVE = "#969a9d"
ACENTO = "#00c9b7"


# Esta pantalla sirve para guardar proveedores y registrar las compras que llegan al negocio.
class PantallaCompras(ctk.CTkFrame):
    def __init__(self, master, usuario: sqlite3.Row) -> None:
        super().__init__(master, fg_color=FONDO, corner_radius=0)
        self.usuario = usuario
        self._compra_seleccionada: int | None = None
        self._filas_compras: dict[int, ctk.CTkFrame] = {}
        self._crear_interfaz()
        self.actualizar()

    # Aquí se organizan la lista de proveedores y el historial de compras.
    def _crear_interfaz(self) -> None:
        encabezado = ctk.CTkFrame(self, fg_color="transparent")
        encabezado.pack(fill="x", padx=20, pady=(18, 12))

        textos = ctk.CTkFrame(encabezado, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            textos,
            text="Compras y proveedores",
            text_color=TEXTO,
            font=("Arial", 24, "bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            textos,
            text="Registra entradas de mercancía y actualiza las existencias.",
            text_color=TEXTO_SUAVE,
            font=("Arial", 12),
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        ctk.CTkButton(
            encabezado,
            text="Nuevo proveedor",
            width=135,
            height=36,
            fg_color="transparent",
            border_width=1,
            border_color=BORDES,
            text_color=TEXTO,
            hover_color=PANEL_SECUNDARIO,
            command=self._abrir_formulario_proveedor,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            encabezado,
            text="Registrar compra  +",
            width=155,
            height=36,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            command=self._abrir_formulario_compra,
        ).pack(side="right")

        self.panel_proveedores = ctk.CTkFrame(
            self, fg_color=PANEL, border_width=1, border_color=BORDES
        )
        self.panel_proveedores.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(
            self.panel_proveedores,
            text="Proveedores",
            text_color=TEXTO,
            font=("Arial", 14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 4))
        self.lista_proveedores = ctk.CTkScrollableFrame(
            self.panel_proveedores, height=105, fg_color="transparent"
        )
        self.lista_proveedores.pack(fill="x", padx=8, pady=(0, 8))

        self.panel_compras = ctk.CTkFrame(
            self, fg_color=PANEL, border_width=1, border_color=BORDES
        )
        self.panel_compras.pack(
            fill="both", expand=True, padx=20, pady=(0, 16)
        )
        contenido_compras = ctk.CTkFrame(
            self.panel_compras, fg_color="transparent"
        )
        contenido_compras.pack(fill="both", expand=True, padx=10, pady=10)
        contenido_compras.grid_columnconfigure(0, weight=4, uniform="panel_compras")
        contenido_compras.grid_columnconfigure(1, weight=6, uniform="panel_compras")
        contenido_compras.grid_rowconfigure(0, weight=1)

        panel_historial = ctk.CTkFrame(
            contenido_compras, fg_color="transparent"
        )
        panel_historial.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        titulo_compras = ctk.CTkFrame(panel_historial, fg_color="transparent")
        titulo_compras.pack(fill="x", padx=6, pady=(0, 5))
        ctk.CTkLabel(
            titulo_compras,
            text="Compras recientes",
            text_color=TEXTO,
            font=("Arial", 14, "bold"),
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            titulo_compras,
            text="Últimas 100",
            text_color=TEXTO_SUAVE,
            font=("Arial", 10),
        ).pack(side="left", padx=8)
        self.lista_compras = ctk.CTkScrollableFrame(
            panel_historial, fg_color="transparent"
        )
        self.lista_compras.pack(fill="both", expand=True)

        panel_detalle = ctk.CTkFrame(
            contenido_compras,
            fg_color=PANEL_SECUNDARIO,
            corner_radius=8,
        )
        panel_detalle.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(
            panel_detalle,
            text="Detalle de compra",
            text_color=TEXTO,
            font=("Arial", 14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 4))
        self.detalle_compra = ctk.CTkScrollableFrame(
            panel_detalle, fg_color="transparent"
        )
        self.detalle_compra.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # Se vuelven a cargar los datos para que aparezcan los cambios después de guardar.
    def actualizar(self, compra_seleccionada: int | None = None) -> None:
        try:
            proveedores = listar_proveedores()
            compras = listar_compras()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron cargar las compras y proveedores:\n{error}",
                parent=self,
            )
            return

        for widget in self.lista_proveedores.winfo_children():
            widget.destroy()
        if proveedores:
            for proveedor in proveedores:
                fila = ctk.CTkFrame(
                    self.lista_proveedores,
                    fg_color=PANEL_SECUNDARIO,
                    corner_radius=6,
                )
                fila.pack(fill="x", padx=3, pady=2)
                fila.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(
                    fila,
                    text=proveedor["nombre"],
                    text_color=TEXTO,
                    anchor="w",
                    font=("Arial", 11, "bold"),
                ).grid(row=0, column=0, sticky="ew", padx=10, pady=7)
                ctk.CTkLabel(
                    fila,
                    text=proveedor["telefono"] or "Sin teléfono",
                    text_color=TEXTO_SUAVE,
                    anchor="e",
                    font=("Arial", 10),
                ).grid(row=0, column=1, padx=10, pady=7)
        else:
            ctk.CTkLabel(
                self.lista_proveedores,
                text="Todavía no hay proveedores registrados.",
                text_color=TEXTO_SUAVE,
            ).pack(anchor="w", padx=8, pady=8)

        for widget in self.lista_compras.winfo_children():
            widget.destroy()
        self._filas_compras.clear()
        self._compra_seleccionada = None
        if compras:
            for compra in compras:
                fila = ctk.CTkFrame(
                    self.lista_compras,
                    fg_color=PANEL,
                    corner_radius=6,
                    cursor="hand2",
                )
                fila.pack(fill="x", padx=3, pady=3)
                fila.grid_columnconfigure(0, weight=1)
                fecha = ctk.CTkLabel(
                    fila,
                    text=f"Compra #{compra['id']} · {compra['fecha']}",
                    text_color=TEXTO_SUAVE,
                    anchor="w",
                    font=("Arial", 11),
                )
                fecha.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=(8, 2))
                total = ctk.CTkLabel(
                    fila,
                    text=formatear_pesos(compra["total"]),
                    text_color=TEXTO,
                    anchor="e",
                    font=("Arial", 12, "bold"),
                )
                total.grid(row=0, column=1, sticky="e", padx=(4, 10), pady=(8, 2))
                proveedor = ctk.CTkLabel(
                    fila,
                    text=compra["proveedor"],
                    text_color=TEXTO,
                    anchor="w",
                    font=("Arial", 12),
                )
                proveedor.grid(
                    row=1, column=0, columnspan=2, sticky="ew",
                    padx=10, pady=(0, 8)
                )
                seleccionar = lambda _evento, compra_id=compra["id"]: (
                    self._seleccionar_compra(compra_id)
                )
                for widget in (fila, fecha, total, proveedor):
                    widget.bind("<Button-1>", seleccionar)
                self._filas_compras[compra["id"]] = fila
            compra_a_mostrar = next(
                (
                    compra["id"]
                    for compra in compras
                    if compra["id"] == compra_seleccionada
                ),
                compras[0]["id"],
            )
            self._seleccionar_compra(compra_a_mostrar)
        else:
            ctk.CTkLabel(
                self.lista_compras,
                text="Todavía no hay compras registradas.",
                text_color=TEXTO_SUAVE,
            ).pack(anchor="w", padx=8, pady=18)
            self._mostrar_detalle_vacio("Selecciona una compra para ver sus productos.")

    # Al escoger una compra se carga su información sin abrir otra ventana.
    def _seleccionar_compra(self, compra_id: int) -> None:
        try:
            compra, productos = obtener_detalle_compra(compra_id)
            ediciones = listar_ediciones_compra(compra_id)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo cargar el detalle de la compra:\n{error}",
                parent=self,
            )
            return
        if not compra:
            messagebox.showwarning(
                "Compra no encontrada",
                "No se encontró el registro seleccionado.",
                parent=self,
            )
            return

        self._compra_seleccionada = compra_id
        for identificador, fila in self._filas_compras.items():
            fila.configure(
                fg_color="#123b37" if identificador == compra_id else PANEL
            )
        for widget in self.detalle_compra.winfo_children():
            widget.destroy()

        ctk.CTkLabel(
            self.detalle_compra,
            text=f"Compra #{compra['id']}",
            text_color=TEXTO,
            anchor="w",
            font=("Arial", 16, "bold"),
        ).pack(fill="x", padx=8, pady=(6, 10))
        ctk.CTkButton(
            self.detalle_compra,
            text="Corregir compra",
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=BORDES,
            text_color=ACENTO,
            hover_color=PANEL,
            command=lambda: self._abrir_formulario_edicion_compra(compra_id),
        ).pack(fill="x", padx=8, pady=(0, 10))
        for etiqueta, valor in (
            ("Fecha", compra["fecha"]),
            ("Proveedor", compra["proveedor"]),
            ("Registrada por", compra["usuario"]),
        ):
            ctk.CTkLabel(
                self.detalle_compra,
                text=f"{etiqueta}: {valor}",
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 12),
            ).pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(
            self.detalle_compra,
            text="Productos recibidos",
            text_color=TEXTO,
            anchor="w",
            font=("Arial", 13, "bold"),
        ).pack(fill="x", padx=8, pady=(14, 6))

        for producto in productos:
            fila = ctk.CTkFrame(
                self.detalle_compra,
                fg_color=PANEL,
                corner_radius=6,
            )
            fila.pack(fill="x", padx=4, pady=3)
            fila.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                fila,
                text=producto["nombre"],
                text_color=TEXTO,
                anchor="w",
                font=("Arial", 12, "bold"),
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
            ctk.CTkLabel(
                fila,
                text=f"Código: {producto['codigo']}",
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 10),
            ).grid(row=1, column=0, sticky="ew", padx=10, pady=1)
            ctk.CTkLabel(
                fila,
                text=(
                    f"{producto['cantidad']} unidades · Costo unitario: "
                    f"{formatear_pesos(producto['costo_unitario'])}"
                ),
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 11),
            ).grid(row=2, column=0, sticky="ew", padx=10, pady=1)
            precio_venta = (
                "Sin dato histórico"
                if producto["precio_venta"] is None
                else formatear_pesos(producto["precio_venta"])
            )
            ctk.CTkLabel(
                fila,
                text=f"Precio de venta registrado: {precio_venta}",
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 11),
            ).grid(row=3, column=0, sticky="ew", padx=10, pady=(1, 8))
            ctk.CTkLabel(
                fila,
                text=formatear_pesos(producto["subtotal"]),
                text_color=TEXTO,
                anchor="e",
                font=("Arial", 12, "bold"),
            ).grid(row=0, column=1, rowspan=4, padx=10)

        ctk.CTkLabel(
            self.detalle_compra,
            text=f"Total: {formatear_pesos(compra['total'])}",
            text_color=TEXTO,
            anchor="e",
            font=("Arial", 16, "bold"),
        ).pack(fill="x", padx=8, pady=(12, 8))
        ctk.CTkLabel(
            self.detalle_compra,
            text="Historial de correcciones",
            text_color=TEXTO,
            anchor="w",
            font=("Arial", 13, "bold"),
        ).pack(fill="x", padx=8, pady=(12, 5))
        if ediciones:
            nombres_campos = {
                "cantidad": "Cantidad",
                "costo_unitario": "Costo unitario",
                "precio_venta": "Precio de venta",
            }
            for edicion in ediciones:
                anterior = edicion["valor_anterior"]
                nuevo = edicion["valor_nuevo"]
                if edicion["campo"] == "cantidad":
                    anterior = "Sin dato" if anterior is None else str(anterior)
                    nuevo = str(nuevo)
                else:
                    anterior = (
                        "Sin dato"
                        if anterior is None
                        else formatear_pesos(anterior)
                    )
                    nuevo = formatear_pesos(nuevo)
                ctk.CTkLabel(
                    self.detalle_compra,
                    text=(
                        f"{edicion['fecha']} · {edicion['usuario']}\n"
                        f"{edicion['producto_nombre']} · "
                        f"{nombres_campos[edicion['campo']]}: "
                        f"{anterior} → {nuevo}"
                    ),
                    text_color=TEXTO_SUAVE,
                    anchor="w",
                    justify="left",
                    font=("Arial", 10),
                ).pack(fill="x", padx=8, pady=3)
        else:
            ctk.CTkLabel(
                self.detalle_compra,
                text="Esta compra todavía no tiene correcciones.",
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 10),
            ).pack(fill="x", padx=8, pady=3)

    # En esta ventana se corrigen las unidades y los precios de cada producto.
    def _abrir_formulario_edicion_compra(self, compra_id: int) -> None:
        try:
            compra, productos = obtener_detalle_compra(compra_id)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron cargar los datos para corregir:\n{error}",
                parent=self,
            )
            return
        if not compra:
            messagebox.showwarning(
                "Compra no encontrada",
                "No se encontró la compra seleccionada.",
                parent=self,
            )
            return

        ventana = ctk.CTkToplevel(self)
        ventana.title(f"Corregir compra #{compra_id}")
        ventana.geometry("820x620")
        ventana.minsize(700, 500)
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()
        ventana.grid_columnconfigure(0, weight=1)
        ventana.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(
            ventana,
            text=f"Corregir compra #{compra_id}",
            text_color=TEXTO,
            font=("Arial", 19, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 4))
        ctk.CTkLabel(
            ventana,
            text=(
                "Ajusta las unidades, el costo o el precio de venta. "
                "El stock se corregirá por la diferencia; no se permite dejarlo "
                "negativo. Una compra anterior no cambia los precios actuales "
                "si hay una compra más reciente."
            ),
            text_color=TEXTO_SUAVE,
            anchor="w",
            wraplength=760,
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))

        encabezado = ctk.CTkFrame(ventana, fg_color="transparent")
        encabezado.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 4))
        encabezado.grid_columnconfigure(0, weight=4)
        encabezado.grid_columnconfigure((1, 2, 3), weight=2, uniform="campos")
        for columna, texto in enumerate(
            ("Producto", "Unidades", "Costo unitario", "Precio de venta")
        ):
            ctk.CTkLabel(
                encabezado,
                text=texto,
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 10, "bold"),
            ).grid(row=0, column=columna, sticky="ew", padx=5)

        lista_edicion = ctk.CTkScrollableFrame(
            ventana, fg_color=PANEL, border_width=1, border_color=BORDES
        )
        lista_edicion.grid(
            row=3, column=0, sticky="nsew", padx=20, pady=(0, 8)
        )
        lista_edicion.grid_columnconfigure(0, weight=4)
        lista_edicion.grid_columnconfigure((1, 2, 3), weight=2, uniform="campos")
        entradas_lineas = []
        for indice, producto in enumerate(productos):
            ctk.CTkLabel(
                lista_edicion,
                text=f"{producto['nombre']}\nCódigo: {producto['codigo']}",
                text_color=TEXTO,
                anchor="w",
                justify="left",
                font=("Arial", 11, "bold"),
            ).grid(row=indice, column=0, sticky="ew", padx=5, pady=6)
            entrada_cantidad = ctk.CTkEntry(lista_edicion, height=32)
            entrada_cantidad.insert(0, str(producto["cantidad"]))
            entrada_cantidad.grid(
                row=indice, column=1, sticky="ew", padx=5, pady=6
            )
            entrada_costo = ctk.CTkEntry(lista_edicion, height=32)
            entrada_costo.insert(
                0, formatear_numero(producto["costo_unitario"])
            )
            entrada_costo.grid(
                row=indice, column=2, sticky="ew", padx=5, pady=6
            )
            entrada_precio_venta = ctk.CTkEntry(
                lista_edicion,
                height=32,
                placeholder_text=(
                    "Sin dato anterior"
                    if producto["precio_venta"] is None
                    else ""
                ),
            )
            if producto["precio_venta"] is not None:
                entrada_precio_venta.insert(
                    0, formatear_numero(producto["precio_venta"])
                )
            entrada_precio_venta.grid(
                row=indice, column=3, sticky="ew", padx=5, pady=6
            )
            for entrada in (entrada_costo, entrada_precio_venta):
                entrada.bind("<KeyRelease>", formatear_entrada_precio)
                entrada.bind(
                    "<FocusOut>", formatear_entrada_precio, add="+"
                )
            entradas_lineas.append(
                {
                    "detalle_id": producto["detalle_id"],
                    "cantidad": entrada_cantidad,
                    "costo_unitario": entrada_costo,
                    "precio_venta": entrada_precio_venta,
                }
            )

        if any(producto["precio_venta"] is None for producto in productos):
            ctk.CTkLabel(
                ventana,
                text=(
                    "En compras anteriores no se guardaba el precio de venta. "
                    "Deja el campo vacío si no quieres registrar una corrección."
                ),
                text_color=TEXTO_SUAVE,
                anchor="w",
                wraplength=760,
                font=("Arial", 10),
            ).grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 8))
            fila_boton = 5
        else:
            fila_boton = 4

        def guardar_correccion() -> None:
            cambios = []
            try:
                for entradas in entradas_lineas:
                    cantidad = int(entradas["cantidad"].get())
                    costo_unitario = leer_importe(
                        entradas["costo_unitario"].get()
                    )
                    texto_precio_venta = entradas["precio_venta"].get().strip()
                    precio_venta = (
                        leer_importe(texto_precio_venta)
                        if texto_precio_venta
                        else None
                    )
                    if cantidad <= 0:
                        raise ValueError(
                            "La cantidad de cada producto debe ser mayor que cero."
                        )
                    cambios.append(
                        {
                            "detalle_id": entradas["detalle_id"],
                            "cantidad": cantidad,
                            "costo_unitario": costo_unitario,
                            "precio_venta": precio_venta,
                        }
                    )
            except ValueError as error:
                messagebox.showwarning(
                    "Revisa los datos", str(error), parent=ventana
                )
                return

            try:
                total = editar_compra(
                    compra_id,
                    self.usuario["id"],
                    cambios,
                )
            except (ValueError, LookupError, PermissionError) as error:
                messagebox.showwarning(
                    "No se pudo corregir la compra",
                    str(error),
                    parent=ventana,
                )
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Error de base de datos",
                    f"No se pudo corregir la compra:\n{error}",
                    parent=ventana,
                )
            else:
                ventana.destroy()
                self.actualizar(compra_id)
                messagebox.showinfo(
                    "Compra corregida",
                    f"El nuevo total es {formatear_pesos(total)}.",
                    parent=self.winfo_toplevel(),
                )

        ctk.CTkButton(
            ventana,
            text="Guardar corrección",
            height=38,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            command=guardar_correccion,
        ).grid(
            row=fila_boton,
            column=0,
            sticky="e",
            padx=20,
            pady=(0, 14),
        )

    def _mostrar_detalle_vacio(self, mensaje: str) -> None:
        for widget in self.detalle_compra.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.detalle_compra,
            text=mensaje,
            text_color=TEXTO_SUAVE,
            anchor="center",
            justify="center",
            font=("Arial", 12),
        ).pack(fill="both", expand=True, padx=12, pady=20)

    # Este formulario guarda el nombre y el teléfono de contacto del proveedor.
    def _abrir_formulario_proveedor(self) -> None:
        ventana = ctk.CTkToplevel(self)
        ventana.title("Nuevo proveedor")
        ventana.geometry("400x250")
        ventana.resizable(False, False)
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        ctk.CTkLabel(
            ventana, text="Registrar proveedor", font=("Arial", 18, "bold")
        ).pack(anchor="w", padx=22, pady=(20, 12))
        ctk.CTkLabel(
            ventana,
            text="Nombre",
            text_color=TEXTO_SUAVE,
            anchor="w",
        ).pack(fill="x", padx=22, pady=(0, 3))
        entrada_nombre = ctk.CTkEntry(
            ventana, height=34, placeholder_text="Nombre del proveedor"
        )
        entrada_nombre.pack(fill="x", padx=22)
        ctk.CTkLabel(
            ventana,
            text="Teléfono (opcional)",
            text_color=TEXTO_SUAVE,
            anchor="w",
        ).pack(fill="x", padx=22, pady=(10, 3))
        entrada_telefono = ctk.CTkEntry(
            ventana, height=34, placeholder_text="Teléfono de contacto"
        )
        entrada_telefono.pack(fill="x", padx=22)

        # Si el nombre ya existe, se avisa para no registrar el mismo proveedor dos veces.
        def guardar() -> None:
            try:
                agregar_proveedor(entrada_nombre.get(), entrada_telefono.get())
            except ValueError as error:
                messagebox.showwarning(
                    "Revisa los datos", str(error), parent=ventana
                )
            except sqlite3.IntegrityError:
                messagebox.showwarning(
                    "Proveedor existente",
                    "Ya hay un proveedor con ese nombre.",
                    parent=ventana,
                )
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Error de base de datos",
                    f"No se pudo guardar el proveedor:\n{error}",
                    parent=ventana,
                )
            else:
                ventana.destroy()
                self.actualizar()

        ctk.CTkButton(
            ventana,
            text="Guardar proveedor",
            fg_color=ACENTO,
            text_color="#101616",
            command=guardar,
        ).pack(anchor="e", padx=22, pady=16)

    # En esta ventana se selecciona el proveedor y se agregan los productos recibidos.
    def _abrir_formulario_compra(self) -> None:
        try:
            proveedores = listar_proveedores()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron cargar los datos para la compra:\n{error}",
                parent=self,
            )
            return

        if not proveedores:
            messagebox.showinfo(
                "Falta un proveedor",
                "Registra un proveedor antes de crear una compra.",
                parent=self,
            )
            self._abrir_formulario_proveedor()
            return
        ventana = ctk.CTkToplevel(self)
        ventana.title("Registrar compra")
        ventana.geometry("600x1")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()
        ventana.grid_columnconfigure(0, weight=1)
        ventana.grid_rowconfigure(0, weight=1)

        # La ventana toma el alto que necesita el formulario, hasta el límite de la pantalla.
        contenido = ctk.CTkFrame(
            ventana, fg_color="transparent", corner_radius=0
        )
        contenido.grid(row=0, column=0, sticky="nsew")
        contenido.grid_columnconfigure(0, weight=1)
        contenido.grid_rowconfigure(8, weight=1)

        ctk.CTkLabel(
            contenido, text="Registrar compra", font=("Arial", 19, "bold")
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 10))
        ctk.CTkLabel(
            contenido, text="Proveedor", text_color=TEXTO_SUAVE, anchor="w"
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 4))

        proveedores_por_nombre = {
            proveedor["nombre"]: proveedor for proveedor in proveedores
        }
        proveedor_var = tk.StringVar(value=proveedores[0]["nombre"])
        ctk.CTkOptionMenu(
            contenido,
            variable=proveedor_var,
            values=list(proveedores_por_nombre),
            fg_color=PANEL_SECUNDARIO,
            button_color=BORDES,
            button_hover_color="#3a3e40",
        ).grid(row=2, column=0, sticky="ew", padx=20)

        etiqueta_producto = ctk.CTkLabel(
            contenido,
            text="Escribe para buscar y selecciona un producto.",
            text_color=TEXTO_SUAVE,
            anchor="w",
        )
        etiqueta_producto.grid(
            row=3, column=0, sticky="ew", padx=20, pady=(12, 2)
        )
        campo_busqueda = ctk.CTkEntry(
            contenido,
            height=36,
            placeholder_text="Buscar nombre, SKU o código de barras...",
        )
        campo_busqueda.grid(
            row=4, column=0, sticky="ew", padx=20, pady=(0, 4)
        )
        resultados_busqueda = ctk.CTkScrollableFrame(
            contenido, height=60, fg_color=PANEL_SECUNDARIO
        )
        resultados_busqueda.grid(
            row=5, column=0, sticky="ew", padx=20, pady=(0, 8)
        )
        producto_seleccionado: dict[str, sqlite3.Row | None] = {"producto": None}
        productos_encontrados: list[sqlite3.Row] = []
        temporizador_busqueda: list[str | None] = [None]

        ctk.CTkButton(
            contenido,
            text="+ Crear producto nuevo",
            height=30,
            fg_color="transparent",
            border_width=1,
            border_color=BORDES,
            text_color=ACENTO,
            hover_color=PANEL_SECUNDARIO,
            command=lambda: abrir_formulario_producto_nuevo(),
        ).grid(row=6, column=0, sticky="ew", padx=20)

        entradas = ctk.CTkFrame(contenido, fg_color="transparent")
        entradas.grid(row=7, column=0, sticky="ew", padx=20, pady=(12, 0))
        entradas.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(
            entradas, text="Cantidad recibida", text_color=TEXTO_SUAVE
        ).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 4))
        ctk.CTkLabel(
            entradas, text="Costo por unidad", text_color=TEXTO_SUAVE
        ).grid(row=0, column=1, sticky="w", padx=6, pady=(0, 4))
        ctk.CTkLabel(
            entradas, text="Precio de venta", text_color=TEXTO_SUAVE
        ).grid(row=0, column=2, sticky="w", padx=(6, 0), pady=(0, 4))
        entrada_cantidad = ctk.CTkEntry(entradas, height=34)
        entrada_cantidad.insert(0, "1")
        entrada_cantidad.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        entrada_costo = ctk.CTkEntry(entradas, height=34)
        entrada_costo.grid(row=1, column=1, sticky="ew", padx=6)
        entrada_precio_venta = ctk.CTkEntry(entradas, height=34)
        entrada_precio_venta.grid(row=1, column=2, sticky="ew", padx=(6, 0))
        for entrada in (entrada_costo, entrada_precio_venta):
            entrada.bind("<KeyRelease>", formatear_entrada_precio)
            entrada.bind("<FocusOut>", formatear_entrada_precio, add="+")

        lineas: list[dict] = []
        lista_lineas = ctk.CTkScrollableFrame(
            contenido,
            height=110,
            label_text="Productos de la compra",
            fg_color=PANEL,
            border_width=1,
            border_color=BORDES,
        )
        lista_lineas.grid(
            row=8, column=0, sticky="nsew", padx=20, pady=(12, 8)
        )
        etiqueta_total = ctk.CTkLabel(
            contenido,
            text="Total: $ 0",
            text_color=TEXTO,
            font=("Arial", 16, "bold"),
            anchor="e",
        )
        etiqueta_total.grid(row=9, column=0, sticky="ew", padx=20, pady=4)

        # Cuando se escoge un resultado se cargan sus precios actuales en el formulario.
        def seleccionar_producto(producto: sqlite3.Row) -> None:
            producto_seleccionado["producto"] = producto
            entrada_costo.delete(0, "end")
            entrada_costo.insert(0, formatear_numero(producto["precio_costo"]))
            entrada_precio_venta.delete(0, "end")
            entrada_precio_venta.insert(
                0, formatear_numero(producto["precio_venta"])
            )
            campo_busqueda.delete(0, "end")
            campo_busqueda.insert(
                0, f"{producto['codigo']} · {producto['nombre']}"
            )
            etiqueta_producto.configure(
                text=f"Seleccionado: {producto['nombre']} · "
                f"Stock actual: {producto['stock']}",
                text_color=ACENTO,
            )
            for widget in resultados_busqueda.winfo_children():
                widget.destroy()

        # La búsqueda consulta la base de datos y muestra solo los primeros resultados.
        def buscar_productos(_evento: tk.Event | None = None) -> None:
            producto_seleccionado["producto"] = None
            etiqueta_producto.configure(
                text="Escribe para buscar y selecciona un producto.",
                text_color=TEXTO_SUAVE,
            )
            if temporizador_busqueda[0]:
                ventana.after_cancel(temporizador_busqueda[0])
            temporizador_busqueda[0] = ventana.after(180, mostrar_resultados)

        def mostrar_resultados() -> None:
            temporizador_busqueda[0] = None
            busqueda = campo_busqueda.get().strip()
            for widget in resultados_busqueda.winfo_children():
                widget.destroy()
            productos_encontrados.clear()
            if not busqueda:
                ctk.CTkLabel(
                    resultados_busqueda,
                    text="Agrega un producto...",
                    text_color=TEXTO_SUAVE,
                    anchor="w",
                ).pack(fill="x", padx=8, pady=8)
                return
            try:
                encontrados = listar_productos(busqueda, limite=20)
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Error de base de datos",
                    f"No se pudieron buscar productos:\n{error}",
                    parent=ventana,
                )
                return
            productos_encontrados.extend(encontrados)
            if not encontrados:
                ctk.CTkLabel(
                    resultados_busqueda,
                    text="No se encontraron productos.",
                    text_color=TEXTO_SUAVE,
                    anchor="w",
                ).pack(fill="x", padx=8, pady=8)
                return
            for producto in encontrados:
                ctk.CTkButton(
                    resultados_busqueda,
                    text=f"{producto['codigo']} · {producto['nombre']} "
                    f"(stock: {producto['stock']})",
                    anchor="w",
                    height=30,
                    fg_color="transparent",
                    hover_color=BORDES,
                    text_color=TEXTO,
                    command=lambda item=producto: seleccionar_producto(item),
                ).pack(fill="x", padx=3, pady=1)

        campo_busqueda.bind("<KeyRelease>", buscar_productos)
        campo_busqueda.bind(
            "<Return>",
            lambda _evento: seleccionar_producto(productos_encontrados[0])
            if productos_encontrados
            else None,
        )
        mostrar_resultados()

        # Esta lista muestra las cantidades, costos y total antes de guardar la compra.
        def dibujar_lineas() -> None:
            for widget in lista_lineas.winfo_children():
                widget.destroy()
            total = 0
            for linea in lineas:
                cantidad = linea["cantidad"]
                costo = linea["costo_unitario"]
                precio_venta = linea["precio_venta"]
                total += cantidad * costo
                fila = ctk.CTkFrame(
                    lista_lineas, fg_color=PANEL_SECUNDARIO, corner_radius=6
                )
                fila.pack(fill="x", padx=4, pady=3)
                fila.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(
                    fila,
                    text=f"{linea['nombre']} · {cantidad} uds. × "
                    f"{formatear_pesos(costo)} = "
                    f"{formatear_pesos(cantidad * costo)} · "
                    f"Venta {formatear_pesos(precio_venta)}",
                    text_color=TEXTO,
                    anchor="w",
                    font=("Arial", 10),
                ).grid(row=0, column=0, sticky="ew", padx=8, pady=7)
                ctk.CTkButton(
                    fila,
                    text="Quitar",
                    width=58,
                    height=25,
                    fg_color="transparent",
                    text_color=ACENTO,
                    hover_color=BORDES,
                    command=lambda item=linea: quitar_linea(item),
                ).grid(row=0, column=1, padx=5)
            if not lineas:
                ctk.CTkLabel(
                    lista_lineas,
                    text="Agrega los productos que llegaron.",
                    text_color=TEXTO_SUAVE,
                ).pack(anchor="w", padx=8, pady=12)
            etiqueta_total.configure(text=f"Total: {formatear_pesos(total)}")

        # Se puede quitar una línea si se agregó el producto por error.
        def quitar_linea(linea: dict) -> None:
            lineas.remove(linea)
            dibujar_lineas()

        # Aquí se valida cada producto antes de sumarlo a la compra.
        def agregar_linea() -> None:
            producto = producto_seleccionado["producto"]
            if producto is None:
                messagebox.showinfo(
                    "Selecciona un producto",
                    "Busca y selecciona un producto o crea uno nuevo.",
                    parent=ventana,
                )
                return
            producto_id = producto["id"]
            if any(linea.get("producto_id") == producto_id for linea in lineas):
                messagebox.showwarning(
                    "Producto repetido",
                    "Ese producto ya está en la compra. Quita la línea si quieres cambiar sus datos.",
                    parent=ventana,
                )
                return
            try:
                cantidad = int(entrada_cantidad.get())
                costo = leer_importe(entrada_costo.get())
                precio_venta = leer_importe(entrada_precio_venta.get())
                if cantidad <= 0:
                    raise ValueError("La cantidad recibida debe ser mayor que cero.")
            except ValueError as error:
                messagebox.showwarning(
                    "Revisa los datos", str(error), parent=ventana
                )
                return
            lineas.append({
                "producto_id": producto_id,
                "nombre": producto["nombre"],
                "cantidad": cantidad,
                "costo_unitario": costo,
                "precio_venta": precio_venta,
            })
            dibujar_lineas()

        ctk.CTkButton(
            entradas,
            text="Agregar producto",
            height=38,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            font=("Arial", 12, "bold"),
            command=agregar_linea,
        ).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        # Este formulario pide los datos que necesita el inventario para un producto nuevo.
        def abrir_formulario_producto_nuevo() -> None:
            try:
                categorias = listar_categorias()
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Error de base de datos",
                    f"No se pudieron cargar las categorías:\n{error}",
                    parent=ventana,
                )
                return
            if not categorias:
                messagebox.showinfo(
                    "Falta una categoría",
                    "Crea una categoría desde Inventario antes de agregar un producto.",
                    parent=ventana,
                )
                return

            formulario = ctk.CTkToplevel(ventana)
            formulario.title("Producto nuevo para la compra")
            formulario.geometry("440x620")
            formulario.resizable(False, False)
            formulario.transient(ventana)
            formulario.grab_set()

            ctk.CTkLabel(
                formulario,
                text="Datos del producto nuevo",
                font=("Arial", 18, "bold"),
            ).pack(anchor="w", padx=22, pady=(18, 12))

            campos = {}
            for etiqueta, marcador, valor in (
                ("Nombre", "Nombre del producto", ""),
                ("Cantidad recibida", "Unidades que llegaron", "1"),
                ("Costo por unidad", "Costo pagado al proveedor", ""),
                ("Precio de venta", "Precio para el cliente", ""),
                ("Stock mínimo", "Nivel para alerta de inventario", "2"),
                ("Código de barras (opcional)", "Código de barras", ""),
            ):
                ctk.CTkLabel(
                    formulario,
                    text=etiqueta,
                    text_color=TEXTO_SUAVE,
                    anchor="w",
                    font=("Arial", 10),
                ).pack(fill="x", padx=22, pady=(4, 2))
                entrada = ctk.CTkEntry(
                    formulario, height=32, placeholder_text=marcador
                )
                if valor:
                    entrada.insert(0, valor)
                entrada.pack(fill="x", padx=22)
                if etiqueta in ("Costo por unidad", "Precio de venta"):
                    entrada.bind("<KeyRelease>", formatear_entrada_precio)
                    entrada.bind(
                        "<FocusOut>", formatear_entrada_precio, add="+"
                    )
                campos[etiqueta] = entrada

            ctk.CTkLabel(
                formulario,
                text="Categoría existente",
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 10),
            ).pack(fill="x", padx=22, pady=(7, 2))
            categorias_por_nombre = {
                categoria["nombre"]: categoria for categoria in categorias
            }
            categoria_var = tk.StringVar(value=categorias[0]["nombre"])
            ctk.CTkOptionMenu(
                formulario,
                variable=categoria_var,
                values=list(categorias_por_nombre),
                fg_color=PANEL_SECUNDARIO,
                button_color=BORDES,
                button_hover_color="#3a3e40",
            ).pack(fill="x", padx=22)

            def agregar_producto_a_compra() -> None:
                try:
                    nombre = campos["Nombre"].get().strip()
                    cantidad = int(campos["Cantidad recibida"].get())
                    costo = leer_importe(campos["Costo por unidad"].get())
                    precio_venta = leer_importe(
                        campos["Precio de venta"].get()
                    )
                    stock_minimo = int(campos["Stock mínimo"].get())
                    if not nombre:
                        raise ValueError("El nombre del producto es obligatorio.")
                    if cantidad <= 0:
                        raise ValueError(
                            "La cantidad recibida debe ser mayor que cero."
                        )
                    if stock_minimo < 0:
                        raise ValueError(
                            "El stock mínimo no puede ser negativo."
                        )
                except ValueError as error:
                    messagebox.showwarning(
                        "Revisa los datos", str(error), parent=formulario
                    )
                    return

                if any(
                    linea.get("nombre", "").casefold() == nombre.casefold()
                    and linea.get("nuevo")
                    for linea in lineas
                ):
                    messagebox.showwarning(
                        "Producto repetido",
                        "Ese producto nuevo ya está agregado a la compra.",
                        parent=formulario,
                    )
                    return

                categoria = categorias_por_nombre[categoria_var.get()]
                lineas.append(
                    {
                        "nuevo": True,
                        "nombre": nombre,
                        "categoria_id": categoria["id"],
                        "cantidad": cantidad,
                        "costo_unitario": costo,
                        "precio_venta": precio_venta,
                        "stock_minimo": stock_minimo,
                        "codigo_barras": campos[
                            "Código de barras (opcional)"
                        ].get().strip() or None,
                    }
                )
                formulario.destroy()
                dibujar_lineas()

            ctk.CTkButton(
                formulario,
                text="Agregar a la compra",
                height=36,
                fg_color=ACENTO,
                hover_color="#00ad9e",
                text_color="#101616",
                command=agregar_producto_a_compra,
            ).pack(fill="x", padx=22, pady=16)

        # Al guardar, la base de datos registra la compra y actualiza las existencias.
        def guardar() -> None:
            if not lineas:
                messagebox.showwarning(
                    "Compra vacía",
                    "Agrega al menos un producto antes de guardar.",
                    parent=ventana,
                )
                return
            datos = []
            for linea in lineas:
                if linea.get("nuevo"):
                    datos.append(
                        {
                            "nuevo": True,
                            "nombre": linea["nombre"],
                            "categoria_id": linea["categoria_id"],
                            "cantidad": linea["cantidad"],
                            "costo_unitario": linea["costo_unitario"],
                            "precio_venta": linea["precio_venta"],
                            "stock_minimo": linea["stock_minimo"],
                            "codigo_barras": linea["codigo_barras"],
                        }
                    )
                else:
                    datos.append(
                        {
                            "producto_id": linea["producto_id"],
                            "cantidad": linea["cantidad"],
                            "costo_unitario": linea["costo_unitario"],
                            "precio_venta": linea["precio_venta"],
                        }
                    )
            proveedor_id = proveedores_por_nombre[proveedor_var.get()]["id"]
            try:
                compra_id, total = registrar_compra(
                    self.usuario["id"], proveedor_id, datos
                )
            except (ValueError, LookupError) as error:
                messagebox.showwarning(
                    "No se pudo registrar la compra", str(error), parent=ventana
                )
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Error de base de datos",
                    f"No se pudo registrar la compra:\n{error}",
                    parent=ventana,
                )
            else:
                ventana.destroy()
                self.actualizar(compra_id)
                messagebox.showinfo(
                    "Compra registrada",
                    f"Compra #{compra_id}\nTotal: {formatear_pesos(total)}\n"
                    "Se actualizaron las existencias y el costo de los productos.",
                    parent=self.winfo_toplevel(),
                )

        ctk.CTkButton(
            ventana,
            text="Guardar compra",
            height=38,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            command=guardar,
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 12))
        dibujar_lineas()
        ventana.update_idletasks()
        alto_solicitado = contenido.winfo_reqheight() + 58
        ancho_ventana = min(600, ventana.winfo_screenwidth() - 40)
        alto_disponible = ventana.winfo_screenheight() - 100
        alto_ventana = min(alto_solicitado, alto_disponible)
        ventana.minsize(min(560, ancho_ventana), min(420, alto_ventana))
        principal = self.winfo_toplevel()
        posicion_x = principal.winfo_rootx() + (
            principal.winfo_width() - ancho_ventana
        ) // 2
        posicion_y = principal.winfo_rooty() + (
            principal.winfo_height() - alto_ventana
        ) // 2
        posicion_x = max(
            0, min(posicion_x, ventana.winfo_screenwidth() - ancho_ventana)
        )
        posicion_y = max(
            0, min(posicion_y, ventana.winfo_screenheight() - alto_ventana)
        )
        ventana.geometry(
            f"{ancho_ventana}x{alto_ventana}+{posicion_x}+{posicion_y}"
        )
