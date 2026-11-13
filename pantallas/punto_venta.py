import sqlite3
import tkinter as tk
from tkinter import messagebox
from typing import TypedDict

import customtkinter as ctk

from database import listar_productos, registrar_venta
from pantallas.formato import formatear_numero, formatear_pesos, leer_importe

FONDO = "#111315"
PANEL = "#1b1d1f"
PANEL_SECUNDARIO = "#202224"
BORDES = "#2c2f31"
TEXTO = "#eeeeee"
TEXTO_SUAVE = "#969a9d"
ACENTO = "#00c9b7"
ROJO = "#e36b72"


class LineaCarrito(TypedDict):
    producto: sqlite3.Row
    cantidad: int
    descuento: int


class PantallaPuntoVenta(ctk.CTkFrame):
    def __init__(self, master, usuario: sqlite3.Row) -> None:
        super().__init__(master, fg_color=FONDO)
        self.usuario = usuario
        self.carrito: dict[int, LineaCarrito] = {}
        self._descuentos: dict[int, ctk.CTkEntry] = {}
        self._temporizador_busqueda: str | None = None
        self.metodos_seleccionados = {"EFECTIVO"}
        self._montos_pago = {"EFECTIVO": 0, "QR": 0, "BOLD": 0}
        self._entradas_pago: dict[str, ctk.CTkEntry] = {}
        self.etiqueta_pago_efectivo: ctk.CTkLabel | None = None
        self._crear_interfaz()

    def _crear_interfaz(self) -> None:
        self.grid_columnconfigure(0, weight=64, uniform="panel")
        self.grid_columnconfigure(1, weight=36, uniform="panel")
        self.grid_rowconfigure(1, weight=1)

        encabezado = ctk.CTkFrame(self, fg_color="transparent")
        encabezado.grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 12)
        )
        ctk.CTkLabel(
            encabezado,
            text="Nueva venta",
            text_color=TEXTO,
            font=("Arial", 23, "bold"),
        ).pack(side="left")
        self.etiqueta_estado = ctk.CTkLabel(
            encabezado,
            text="En curso",
            text_color=TEXTO_SUAVE,
            fg_color=PANEL_SECUNDARIO,
            corner_radius=5,
            font=("Arial", 10),
        )
        self.etiqueta_estado.pack(side="left", padx=10)

        self.panel_carrito = ctk.CTkFrame(
            self, fg_color=PANEL, border_width=1, border_color=BORDES
        )
        self.panel_carrito.grid(
            row=1, column=0, sticky="nsew", padx=(20, 7), pady=(0, 16)
        )
        self.panel_carrito.grid_columnconfigure(0, weight=1)
        self.panel_carrito.grid_rowconfigure(4, weight=1)
        self._crear_busqueda()
        self._crear_tabla_carrito()

        self.panel_pago = ctk.CTkFrame(
            self, fg_color=PANEL, border_width=1, border_color=BORDES
        )
        self.panel_pago.grid(
            row=1, column=1, sticky="nsew", padx=(7, 20), pady=(0, 16)
        )
        self.panel_pago.grid_columnconfigure(0, weight=1)
        self._crear_pago()
        self._dibujar_carrito()

    def _crear_busqueda(self) -> None:
        busqueda = ctk.CTkFrame(self.panel_carrito, fg_color="transparent")
        busqueda.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        busqueda.grid_columnconfigure(0, weight=1)
        self.campo_busqueda = ctk.CTkEntry(
            busqueda,
            height=38,
            placeholder_text="Escanea el código de barras o busca un producto...",
        )
        self.campo_busqueda.grid(row=0, column=0, sticky="ew")
        self.campo_busqueda.bind("<KeyRelease>", self._programar_busqueda)
        self.campo_busqueda.bind("<Button-1>", self._reiniciar_busqueda)
        self.campo_busqueda.bind(
            "<Return>", lambda _evento: self._agregar_coincidencia()
        )
        ctk.CTkLabel(
            self.panel_carrito,
            text="Busca por nombre o código. Presiona Enter para agregar.",
            anchor="w",
            text_color=TEXTO_SUAVE,
            font=("Arial", 10),
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 2))
        self.resultados = ctk.CTkScrollableFrame(
            self.panel_carrito, fg_color=PANEL_SECUNDARIO, height=110
        )

    def _crear_tabla_carrito(self) -> None:
        encabezado = ctk.CTkFrame(self.panel_carrito, fg_color="transparent")
        encabezado.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 4))
        encabezado.grid_columnconfigure(
            (0, 1, 2, 3, 4), weight=1, uniform="encabezado"
        )
        for columna, titulo in enumerate(
            ("CÓDIGO", "NOMBRE DEL PRODUCTO", "CANTIDAD", "PRECIO UNITARIO", "SUBTOTAL")
        ):
            ctk.CTkLabel(
                encabezado,
                text=titulo,
                text_color=TEXTO_SUAVE,
                anchor="w" if columna < 2 else "center",
                font=("Arial", 9, "bold"),
            ).grid(row=0, column=columna, sticky="ew", padx=3)

        self.lineas_carrito = ctk.CTkScrollableFrame(
            self.panel_carrito, fg_color="transparent"
        )
        self.lineas_carrito.grid(
            row=4, column=0, sticky="nsew", padx=8, pady=(0, 4)
        )
        self.lineas_carrito.grid_columnconfigure(
            (0, 1, 2, 3, 4), weight=1, uniform="linea"
        )
        pie = ctk.CTkFrame(self.panel_carrito, fg_color="transparent")
        pie.grid(row=5, column=0, sticky="ew", padx=14, pady=(3, 12))
        self.etiqueta_articulos = ctk.CTkLabel(
            pie, text="0 artículos en esta venta", anchor="w", text_color=TEXTO_SUAVE
        )
        self.etiqueta_articulos.pack(side="left")
        ctk.CTkButton(
            pie,
            text="Vaciar carrito",
            width=100,
            height=28,
            fg_color="transparent",
            hover_color=PANEL_SECUNDARIO,
            text_color=ROJO,
            command=self._vaciar_carrito,
        ).pack(side="right")

    def _crear_pago(self) -> None:
        ctk.CTkLabel(
            self.panel_pago,
            text="TOTAL A PAGAR",
            text_color=TEXTO_SUAVE,
            anchor="w",
            font=("Arial", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 2))
        self.etiqueta_total = ctk.CTkLabel(
            self.panel_pago,
            text="$ 0",
            text_color=TEXTO,
            anchor="w",
            font=("Arial", 34, "bold"),
        )
        self.etiqueta_total.grid(row=1, column=0, sticky="ew", padx=14)
        self.etiqueta_resumen = ctk.CTkLabel(
            self.panel_pago,
            text="Subtotal $ 0  ·  Descuentos $ 0",
            text_color=TEXTO_SUAVE,
            anchor="w",
            font=("Arial", 10),
        )
        self.etiqueta_resumen.grid(
            row=2, column=0, sticky="ew", padx=16, pady=(0, 14)
        )

        ctk.CTkLabel(
            self.panel_pago,
            text="Método de pago",
            text_color=TEXTO,
            anchor="w",
            font=("Arial", 11, "bold"),
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 8))
        metodos = ctk.CTkFrame(self.panel_pago, fg_color="transparent")
        metodos.grid(row=4, column=0, sticky="ew", padx=12)
        metodos.grid_columnconfigure((0, 1, 2), weight=1, uniform="metodo")
        self.botones_pago: dict[str, ctk.CTkButton] = {}
        for columna, (metodo, etiqueta) in enumerate(
            (
                ("EFECTIVO", "Efectivo"),
                ("QR", "QR"),
                ("BOLD", "Datáfono\nBold"),
            )
        ):
            boton = ctk.CTkButton(
                metodos,
                text=etiqueta,
                height=48,
                fg_color=PANEL_SECUNDARIO,
                border_width=1,
                border_color=BORDES,
                hover_color="#303638",
                command=lambda valor=metodo: self._alternar_metodo(valor),
            )
            boton.grid(row=0, column=columna, sticky="ew", padx=3)
            self.botones_pago[metodo] = boton
        self._actualizar_botones_pago()

        self.panel_montos_pago = ctk.CTkFrame(
            self.panel_pago, fg_color="transparent"
        )
        self.panel_montos_pago.grid(
            row=6, column=0, sticky="ew", padx=16, pady=(8, 0)
        )
        self._dibujar_montos_pago()

        self.panel_efectivo = ctk.CTkFrame(self.panel_pago, fg_color="transparent")
        self.panel_efectivo.grid(
            row=5, column=0, sticky="ew", padx=16, pady=(14, 0)
        )
        self.panel_efectivo.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.panel_efectivo, text="Efectivo recibido", anchor="w",
            text_color=TEXTO_SUAVE,
        ).grid(row=0, column=0, sticky="ew")
        self.campo_efectivo = ctk.CTkEntry(
            self.panel_efectivo, height=38, placeholder_text="$ 0"
        )
        self.campo_efectivo.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.campo_efectivo.bind("<KeyRelease>", self._cambio_efectivo_recibido)
        self.campo_efectivo.bind("<FocusOut>", self._formatear_efectivo_recibido)
        self.etiqueta_cambio = ctk.CTkLabel(
            self.panel_pago,
            text="Cambio / Devuelta: $ 0",
            text_color=ACENTO,
            anchor="w",
            font=("Arial", 14, "bold"),
        )
        self.etiqueta_cambio.grid(
            row=7, column=0, sticky="ew", padx=16, pady=(4, 0)
        )

        espacio = ctk.CTkFrame(self.panel_pago, fg_color="transparent")
        espacio.grid(row=8, column=0, sticky="nsew")
        self.panel_pago.grid_rowconfigure(8, weight=1)
        self.etiqueta_estado_pago = ctk.CTkLabel(
            self.panel_pago,
            text="Elige los métodos y reparte el pago.",
            text_color=TEXTO_SUAVE,
            anchor="w",
            font=("Arial", 10),
            wraplength=280,
        )
        self.etiqueta_estado_pago.grid(
            row=9, column=0, sticky="ew", padx=16, pady=(8, 6)
        )
        ctk.CTkButton(
            self.panel_pago,
            text="PROCESAR VENTA",
            height=42,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            font=("Arial", 12, "bold"),
            command=self._confirmar_venta,
        ).grid(row=10, column=0, sticky="ew", padx=16, pady=(0, 16))

    # Esto hace una búsqueda con espera para no buscar en cada letra.
    def _programar_busqueda(self, _evento: tk.Event) -> None:
        # Se espera a que el usuario termine de escribir antes de buscar.
        if self._temporizador_busqueda:
            self.after_cancel(self._temporizador_busqueda)
        self._temporizador_busqueda = self.after(180, self._buscar_productos)

    def _reiniciar_busqueda(self, _evento: tk.Event) -> None:
        if not self.campo_busqueda.get():
            return
        if self._temporizador_busqueda:
            self.after_cancel(self._temporizador_busqueda)
            self._temporizador_busqueda = None
        self.campo_busqueda.delete(0, "end")
        self._buscar_productos()

    # Aquí se busca en la base de datos lo que escribe el usuario.
    def _buscar_productos(self) -> None:
        self._temporizador_busqueda = None
        busqueda = self.campo_busqueda.get().strip()
        for widget in self.resultados.winfo_children():
            widget.destroy()
        if not busqueda:
            self.resultados.grid_remove()
            return
        try:
            productos = listar_productos(busqueda)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron buscar productos:\n{error}",
                parent=self,
            )
            return

        self.resultados.grid(
            row=3, column=0, sticky="ew", padx=14, pady=(0, 4)
        )
        if not productos:
            ctk.CTkLabel(
                self.resultados,
                text="No se encontraron productos.",
                text_color=TEXTO_SUAVE,
            ).pack(pady=8)
            return

        for producto in productos:
            fila = ctk.CTkFrame(
                self.resultados,
                fg_color=PANEL,
                corner_radius=6,
                cursor="hand2" if producto["stock"] > 0 else "arrow",
            )
            fila.pack(fill="x", padx=4, pady=3)
            nombre = ctk.CTkLabel(
                fila,
                text=f"{producto['nombre']}  ·  {producto['codigo']}  ·  "
                f"{producto['stock']} uds.  ·  "
                f"{formatear_pesos(producto['precio_venta'])}",
                anchor="w",
                cursor="hand2" if producto["stock"] > 0 else "arrow",
            )
            nombre.pack(fill="x", padx=8, pady=9)
            if producto["stock"] > 0:
                # La fila completa se puede pulsar para agregar el producto al carrito.
                fila.bind(
                    "<Button-1>",
                    lambda _evento, item=producto: self._agregar_producto(item),
                )
                nombre.bind(
                    "<Button-1>",
                    lambda _evento, item=producto: self._agregar_producto(item),
                )

    def _agregar_coincidencia(self) -> None:
        codigo = self.campo_busqueda.get().strip().casefold()
        try:
            productos = listar_productos(codigo)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo consultar el producto:\n{error}",
                parent=self,
            )
            return
        producto = next(
            (
                item
                for item in productos
                if codigo
                in {
                    item["codigo"].casefold(),
                    (item["codigo_barras"] or "").casefold(),
                }
            ),
            None,
        )
        if producto:
            self._agregar_producto(producto)
            self.campo_busqueda.delete(0, "end")
            self._buscar_productos()
        else:
            self._buscar_productos()

    # Esto agrega el producto al carrito y evita pasar del stock disponible.
    def _agregar_producto(self, producto: sqlite3.Row) -> None:
        producto_id = producto["id"]
        linea = self.carrito.get(producto_id)
        cantidad_actual = linea["cantidad"] if linea else 0
        if cantidad_actual >= producto["stock"]:
            messagebox.showwarning(
                "Stock insuficiente",
                "No hay más unidades disponibles para agregar.",
                parent=self,
            )
            return
        if linea:
            linea["cantidad"] += 1
            linea["producto"] = producto
        else:
            self.carrito[producto_id] = {
                "producto": producto,
                "cantidad": 1,
                "descuento": 0,
            }
        self._dibujar_carrito()

    # Este método vuelve a dibujar el carrito con los productos, cantidades y totales.
    def _dibujar_carrito(self) -> None:
        if not self._guardar_descuentos():
            return
        for widget in self.lineas_carrito.winfo_children():
            widget.destroy()
        self._descuentos.clear()
        total_articulos = 0

        for numero, (producto_id, linea) in enumerate(self.carrito.items()):
            producto = linea["producto"]
            cantidad = linea["cantidad"]
            total_articulos += cantidad
            ctk.CTkLabel(
                self.lineas_carrito,
                text=producto["codigo"],
                text_color=TEXTO_SUAVE,
                anchor="w",
                font=("Arial", 9),
            ).grid(row=numero, column=0, sticky="ew", padx=4, pady=8)

            nombre = ctk.CTkFrame(self.lineas_carrito, fg_color="transparent")
            nombre.grid(row=numero, column=1, sticky="ew", padx=4, pady=4)
            nombre.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                nombre,
                text=producto["nombre"],
                text_color=TEXTO,
                anchor="w",
                font=("Arial", 10, "bold"),
                wraplength=190,
            ).grid(row=0, column=0, sticky="ew")
            descuento = ctk.CTkEntry(
                nombre,
                width=120,
                height=25,
                placeholder_text="Descuento",
            )
            if linea["descuento"]:
                descuento.insert(0, formatear_numero(linea["descuento"]))
            descuento.grid(row=1, column=0, sticky="w", pady=(3, 0))
            descuento.bind(
                "<FocusIn>",
                lambda _evento, entrada=descuento: self._seleccionar_valor(entrada),
            )
            descuento.bind(
                "<KeyRelease>",
                lambda _evento, pid=producto_id: self._previsualizar_descuento(pid),
            )
            descuento.bind(
                "<FocusOut>", lambda _evento, pid=producto_id: self._aplicar_descuento(pid)
            )
            descuento.bind(
                "<Return>", lambda _evento, pid=producto_id: self._aplicar_descuento(pid)
            )
            self._descuentos[producto_id] = descuento

            controles = ctk.CTkFrame(self.lineas_carrito, fg_color="transparent")
            controles.grid(row=numero, column=2, sticky="ew", padx=2, pady=6)
            controles.grid_columnconfigure(1, weight=1)
            ctk.CTkButton(
                controles,
                text="−",
                width=25,
                height=25,
                fg_color=ACENTO,
                hover_color="#00ad9e",
                text_color="#101616",
                command=lambda pid=producto_id: self._cambiar_cantidad(pid, -1),
            ).grid(row=0, column=0)
            ctk.CTkLabel(
                controles, text=str(cantidad), anchor="center"
            ).grid(row=0, column=1, sticky="ew", padx=2)
            ctk.CTkButton(
                controles,
                text="+",
                width=25,
                height=25,
                fg_color=ACENTO,
                hover_color="#00ad9e",
                text_color="#101616",
                command=lambda pid=producto_id: self._cambiar_cantidad(pid, 1),
            ).grid(row=0, column=2)
            ctk.CTkLabel(
                self.lineas_carrito,
                text=formatear_pesos(producto["precio_venta"]),
                text_color=TEXTO_SUAVE,
                anchor="center",
                font=("Arial", 9),
            ).grid(row=numero, column=3, sticky="ew", padx=3)
            subtotal = cantidad * producto["precio_venta"] - linea["descuento"]
            ctk.CTkLabel(
                self.lineas_carrito,
                text=formatear_pesos(subtotal),
                text_color=TEXTO,
                anchor="center",
                font=("Arial", 9, "bold"),
            ).grid(row=numero, column=4, sticky="ew", padx=3)

        if not self.carrito:
            ctk.CTkLabel(
                self.lineas_carrito,
                text="Busca un producto para empezar la venta.",
                text_color=TEXTO_SUAVE,
                font=("Arial", 12),
            ).grid(row=0, column=0, columnspan=5, pady=32)

        self.etiqueta_articulos.configure(
            text=f"{total_articulos} artículos en esta venta"
        )
        self._actualizar_totales()

    # En esta parte se revisan los descuentos antes de seguir con la venta.
    def _guardar_descuentos(self) -> bool:
        for producto_id, entrada in self._descuentos.items():
            if producto_id not in self.carrito:
                continue
            try:
                descuento = leer_importe(entrada.get() or "0")
            except ValueError as error:
                messagebox.showwarning(
                    "Descuento no válido", str(error), parent=self
                )
                return False
            linea = self.carrito[producto_id]
            if descuento > linea["cantidad"] * linea["producto"]["precio_venta"]:
                messagebox.showwarning(
                    "Descuento no válido",
                    f"El descuento no puede superar el subtotal de "
                    f"{linea['producto']['nombre']}.",
                    parent=self,
                )
                return False
            linea["descuento"] = descuento
        return True

    def _aplicar_descuento(self, producto_id: int) -> None:
        try:
            descuento = leer_importe(self._descuentos[producto_id].get() or "0")
            linea = self.carrito[producto_id]
            if descuento > linea["cantidad"] * linea["producto"]["precio_venta"]:
                raise ValueError("El descuento no puede superar el subtotal del producto.")
        except ValueError as error:
            messagebox.showwarning("Descuento no válido", str(error), parent=self)
            return
        # El descuento se guarda como valor total de la línea, no por unidad.
        self.carrito[producto_id]["descuento"] = descuento
        entrada = self._descuentos[producto_id]
        entrada.delete(0, "end")
        if descuento:
            entrada.insert(0, formatear_numero(descuento))
        self._actualizar_totales()

    def _previsualizar_descuento(self, producto_id: int) -> None:
        try:
            descuento = leer_importe(self._descuentos[producto_id].get() or "0")
        except ValueError:
            return
        linea = self.carrito[producto_id]
        subtotal = linea["cantidad"] * linea["producto"]["precio_venta"]
        if descuento <= subtotal:
            linea["descuento"] = descuento
            self._actualizar_totales()

    @staticmethod
    def _seleccionar_valor(entrada: ctk.CTkEntry) -> None:
        entrada.after_idle(lambda: entrada.select_range(0, "end"))

    def _cambiar_cantidad(self, producto_id: int, cambio: int) -> None:
        linea = self.carrito[producto_id]
        nueva_cantidad = linea["cantidad"] + cambio
        if not self._guardar_descuentos():
            return
        if nueva_cantidad <= 0:
            del self.carrito[producto_id]
        elif nueva_cantidad > linea["producto"]["stock"]:
            messagebox.showwarning(
                "Stock insuficiente",
                "No hay más unidades disponibles.",
                parent=self,
            )
            return
        else:
            linea["cantidad"] = nueva_cantidad
            if linea["descuento"] > nueva_cantidad * linea["producto"]["precio_venta"]:
                linea["descuento"] = nueva_cantidad * linea["producto"]["precio_venta"]
        self._dibujar_carrito()

    def _quitar_producto(self, producto_id: int) -> None:
        if not self._guardar_descuentos():
            return
        del self.carrito[producto_id]
        self._dibujar_carrito()

    def _vaciar_carrito(self) -> None:
        if self.carrito and messagebox.askyesno(
            "Vaciar carrito",
            "¿Quieres quitar todos los productos de esta venta?",
            parent=self,
        ):
            self.carrito.clear()
            self._dibujar_carrito()

    def _actualizar_totales(self) -> tuple[int, int, int]:
        subtotal = sum(
            linea["cantidad"] * linea["producto"]["precio_venta"]
            for linea in self.carrito.values()
        )
        descuento = sum(linea["descuento"] for linea in self.carrito.values())
        total = subtotal - descuento
        self.etiqueta_total.configure(text=formatear_pesos(total))
        self.etiqueta_resumen.configure(
            text=f"Subtotal {formatear_pesos(subtotal)}  ·  "
            f"Descuentos {formatear_pesos(descuento)}"
        )
        self._actualizar_estado_pago()
        self._actualizar_cambio()
        return subtotal, descuento, total

    # Aquí se activa o desactiva el método de pago que va a usar la venta.
    def _alternar_metodo(self, metodo: str) -> None:
        if not self._leer_montos_pago():
            return
        if metodo in self.metodos_seleccionados:
            self.metodos_seleccionados.remove(metodo)
            self._montos_pago[metodo] = 0
        else:
            self.metodos_seleccionados.add(metodo)
        self._dibujar_montos_pago()
        if "EFECTIVO" in self.metodos_seleccionados:
            self.panel_efectivo.grid()
            self.etiqueta_cambio.grid()
        else:
            self.panel_efectivo.grid_remove()
            self.etiqueta_cambio.grid_remove()
        self._actualizar_botones_pago()
        self._actualizar_estado_pago()
        self._actualizar_cambio()

    def _actualizar_botones_pago(self) -> None:
        for metodo, boton in self.botones_pago.items():
            seleccionado = metodo in self.metodos_seleccionados
            boton.configure(
                fg_color="#123b37" if seleccionado else PANEL_SECUNDARIO,
                border_color=ACENTO if seleccionado else BORDES,
                text_color=ACENTO if seleccionado else TEXTO,
            )

    def _dibujar_montos_pago(self) -> None:
        for widget in self.panel_montos_pago.winfo_children():
            widget.destroy()
        self._entradas_pago.clear()
        self.etiqueta_pago_efectivo = None
        if not self.metodos_seleccionados:
            ctk.CTkLabel(
                self.panel_montos_pago,
                text="Selecciona uno o más métodos de pago.",
                text_color=TEXTO_SUAVE,
                anchor="w",
            ).pack(fill="x")
            return

        etiquetas = {
            "EFECTIVO": "Efectivo",
            "QR": "Transferencia QR",
            "BOLD": "Datáfono Bold",
        }
        for metodo in ("EFECTIVO", "QR", "BOLD"):
            if metodo not in self.metodos_seleccionados:
                continue
            if metodo == "EFECTIVO":
                fila_efectivo = ctk.CTkFrame(
                    self.panel_montos_pago, fg_color="transparent"
                )
                fila_efectivo.pack(fill="x", pady=(5, 2))
                ctk.CTkLabel(
                    fila_efectivo,
                    text="Pago cubierto en efectivo",
                    text_color=TEXTO_SUAVE,
                    anchor="w",
                ).pack(side="left")
                self.etiqueta_pago_efectivo = ctk.CTkLabel(
                    fila_efectivo,
                    text=formatear_pesos(self._montos_pago["EFECTIVO"]),
                    text_color=TEXTO,
                    anchor="e",
                )
                self.etiqueta_pago_efectivo.pack(side="right")
                continue
            ctk.CTkLabel(
                self.panel_montos_pago,
                text=f"Valor pagado con {etiquetas[metodo]}",
                text_color=TEXTO_SUAVE,
                anchor="w",
            ).pack(fill="x", pady=(5, 2))
            entrada = ctk.CTkEntry(
                self.panel_montos_pago, height=34, placeholder_text="$ 0"
            )
            monto = self._montos_pago[metodo]
            if monto:
                entrada.insert(0, formatear_numero(monto))
            entrada.pack(fill="x")
            entrada.bind(
                "<KeyRelease>",
                lambda _evento, clave=metodo: self._cambio_montos_pago(clave),
            )
            entrada.bind(
                "<FocusOut>",
                lambda _evento, clave=metodo: self._formatear_monto_pago(clave),
            )
            if len(self.metodos_seleccionados) == 1:
                entrada.configure(state="disabled")
            self._entradas_pago[metodo] = entrada

    def _leer_montos_pago(self) -> bool:
        montos = {}
        for metodo, entrada in self._entradas_pago.items():
            try:
                montos[metodo] = leer_importe(entrada.get() or "0")
            except ValueError:
                return False
        self._montos_pago.update(montos)
        return True

    def _cambio_montos_pago(self, metodo_editado: str | None = None) -> None:
        if self._leer_montos_pago():
            if len(self.metodos_seleccionados) == 2 and metodo_editado:
                # Con dos métodos, el que no se edita cubre automáticamente el saldo.
                otro_metodo = next(
                    metodo
                    for metodo in self.metodos_seleccionados
                    if metodo != metodo_editado
                )
                self._montos_pago[otro_metodo] = max(
                    0, self._total_venta() - self._montos_pago[metodo_editado]
                )
                otra_entrada = self._entradas_pago.get(otro_metodo)
                if otra_entrada:
                    otra_entrada.delete(0, "end")
                    otra_entrada.insert(
                        0, formatear_numero(self._montos_pago[otro_metodo])
                    )
            self._actualizar_estado_pago()
            self._actualizar_cambio()
        else:
            self.etiqueta_estado_pago.configure(
                text="Ingresa valores enteros válidos para cada método."
            )

    def _formatear_monto_pago(self, metodo: str) -> None:
        entrada = self._entradas_pago.get(metodo)
        if not entrada:
            return
        try:
            monto = leer_importe(entrada.get() or "0")
        except ValueError:
            return
        self._montos_pago[metodo] = monto
        entrada.delete(0, "end")
        if monto:
            entrada.insert(0, formatear_numero(monto))
        self._cambio_montos_pago(metodo)

    def _total_venta(self) -> int:
        return sum(
            linea["cantidad"] * linea["producto"]["precio_venta"]
            - linea["descuento"]
            for linea in self.carrito.values()
        )

    def _actualizar_estado_pago(self) -> None:
        if not self.metodos_seleccionados:
            self.etiqueta_estado_pago.configure(
                text="Selecciona uno o más métodos de pago.", text_color=ROJO
            )
            return
        total = self._total_venta()
        if "EFECTIVO" in self.metodos_seleccionados:
            # La parte en efectivo es lo que queda después de contar QR o Bold.
            otros_pagos = sum(
                self._montos_pago[metodo]
                for metodo in self.metodos_seleccionados
                if metodo != "EFECTIVO"
            )
            self._montos_pago["EFECTIVO"] = max(0, total - otros_pagos)
            if self.etiqueta_pago_efectivo:
                self.etiqueta_pago_efectivo.configure(
                    text=formatear_pesos(self._montos_pago["EFECTIVO"])
                )
        elif len(self.metodos_seleccionados) == 1:
            metodo = next(iter(self.metodos_seleccionados))
            self._montos_pago[metodo] = total
            entrada = self._entradas_pago.get(metodo)
            if entrada:
                entrada.configure(state="normal")
                entrada.delete(0, "end")
                entrada.insert(0, formatear_numero(total))
                entrada.configure(state="disabled")

        total_pagado = sum(
            self._montos_pago[metodo] for metodo in self.metodos_seleccionados
        )
        diferencia = total - total_pagado
        if diferencia > 0:
            texto = f"Falta asignar {formatear_pesos(diferencia)} al pago."
            color = ROJO
        elif diferencia < 0:
            texto = f"El pago supera el total por {formatear_pesos(-diferencia)}."
            color = ROJO
        else:
            texto = "La distribución del pago está completa."
            color = ACENTO
        self.etiqueta_estado_pago.configure(text=texto, text_color=color)

    def _actualizar_cambio(self, _evento: tk.Event | None = None) -> None:
        if (
            "EFECTIVO" not in self.metodos_seleccionados
            or not hasattr(self, "etiqueta_cambio")
        ):
            return
        try:
            recibido = leer_importe(self.campo_efectivo.get() or "0")
        except ValueError:
            self.etiqueta_cambio.configure(text="Efectivo recibido no válido")
            return
        efectivo_asignado = self._montos_pago["EFECTIVO"]
        if recibido < efectivo_asignado:
            self.etiqueta_cambio.configure(
                text=f"Falta efectivo por {formatear_pesos(efectivo_asignado - recibido)}",
                text_color=ROJO,
            )
        else:
            self.etiqueta_cambio.configure(
                text=f"Cambio / Devuelta: "
                f"{formatear_pesos(recibido - efectivo_asignado)}",
                text_color=ACENTO,
            )

    def _cambio_efectivo_recibido(self, _evento: tk.Event | None = None) -> None:
        if (
            len(self.metodos_seleccionados) == 2
            and "EFECTIVO" in self.metodos_seleccionados
        ):
            try:
                recibido = leer_importe(self.campo_efectivo.get() or "0")
            except ValueError:
                self._actualizar_cambio()
                return
            total = self._total_venta()
            # Al recibir efectivo, el otro método seleccionado se ajusta al restante.
            otro_metodo = next(
                metodo
                for metodo in self.metodos_seleccionados
                if metodo != "EFECTIVO"
            )
            self._montos_pago[otro_metodo] = max(0, total - min(recibido, total))
            otra_entrada = self._entradas_pago.get(otro_metodo)
            if otra_entrada:
                otra_entrada.delete(0, "end")
                if self._montos_pago[otro_metodo]:
                    otra_entrada.insert(
                        0, formatear_numero(self._montos_pago[otro_metodo])
                    )
            self._actualizar_estado_pago()
        self._actualizar_cambio()

    def _formatear_efectivo_recibido(self, _evento: tk.Event | None = None) -> None:
        try:
            recibido = leer_importe(self.campo_efectivo.get() or "0")
        except ValueError:
            return
        self.campo_efectivo.delete(0, "end")
        if recibido:
            self.campo_efectivo.insert(0, formatear_numero(recibido))
        self._cambio_efectivo_recibido()

    # Aquí termina la venta: valida todo, guarda en la BD y limpia el carrito.
    def _confirmar_venta(self) -> None:
        if not self.carrito:
            messagebox.showwarning(
                "Carrito vacío",
                "Agrega productos antes de registrar la venta.",
                parent=self,
            )
            return
        if not self._guardar_descuentos():
            return
        if not self.metodos_seleccionados:
            messagebox.showwarning(
                "Falta el método de pago",
                "Selecciona uno o más métodos para registrar el pago.",
                parent=self,
            )
            return
        if not self._leer_montos_pago():
            messagebox.showwarning(
                "Revisa los pagos",
                "Ingresa valores enteros válidos para cada método.",
                parent=self,
            )
            return

        _subtotal, _descuento, total = self._actualizar_totales()
        pagos = {
            metodo: self._montos_pago[metodo]
            for metodo in self.metodos_seleccionados
        }
        if sum(pagos.values()) != total:
            self._actualizar_estado_pago()
            messagebox.showwarning(
                "El pago no coincide",
                "La suma de los métodos de pago debe ser igual al total.",
                parent=self,
            )
            return
        if "EFECTIVO" in self.metodos_seleccionados:
            try:
                recibido = leer_importe(self.campo_efectivo.get() or "0")
            except ValueError as error:
                messagebox.showwarning("Revisa el efectivo", str(error), parent=self)
                return
            if recibido < pagos["EFECTIVO"]:
                messagebox.showwarning(
                    "Efectivo insuficiente",
                    "El efectivo recibido no alcanza para cubrir la parte en efectivo.",
                    parent=self,
                )
                return

        medios = ", ".join(sorted(self.metodos_seleccionados))
        if not messagebox.askyesno(
            "Confirmar venta",
            f"Total: {formatear_pesos(total)}\n"
            f"Métodos: {medios}\n¿Registrar la venta?",
            parent=self,
        ):
            return

        productos = [
            {
                "producto_id": producto_id,
                "cantidad": linea["cantidad"],
                "descuento": linea["descuento"],
            }
            for producto_id, linea in self.carrito.items()
        ]
        # La base vuelve a validar los montos y el stock antes de guardar la venta.
        try:
            venta_id, total = registrar_venta(
                self.usuario["id"], productos, pagos
            )
        except (ValueError, LookupError) as error:
            messagebox.showwarning("No se pudo registrar", str(error), parent=self)
            self._buscar_productos()
            return
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo registrar la venta:\n{error}",
                parent=self,
            )
            return

        self.carrito.clear()
        self.campo_efectivo.delete(0, "end")
        self.metodos_seleccionados = {"EFECTIVO"}
        self._montos_pago = {"EFECTIVO": 0, "QR": 0, "BOLD": 0}
        self._dibujar_montos_pago()
        self.panel_efectivo.grid()
        self._actualizar_botones_pago()
        self._dibujar_carrito()
        self.campo_busqueda.delete(0, "end")
        self._buscar_productos()
        self.campo_busqueda.focus()
        messagebox.showinfo(
            "Venta registrada",
            f"Venta #{venta_id}\nTotal: {formatear_pesos(total)}",
            parent=self,
        )
