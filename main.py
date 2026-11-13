import sqlite3

import customtkinter as ctk

from database import inicializar_base_datos
from pantallas.acceso import PantallaAcceso, VentanaCajeros
from pantallas.compras import PantallaCompras
from pantallas.inventario import PantallaInventario
from pantallas.punto_venta import PantallaPuntoVenta


# Esta clase controla la app y deja guardada la pantalla que se está usando.
class Aplicacion(ctk.CTkFrame):
    def __init__(self, master) -> None:
        super().__init__(master, fg_color="#111315", corner_radius=0)
        self.pack(fill="both", expand=True)
        self.usuario: sqlite3.Row | None = None
        self.barra: ctk.CTkFrame | None = None
        self.contenido: ctk.CTkFrame | None = None
        self.pantalla: ctk.CTkFrame | None = None
        # Se conservan las pantallas para no perder el carrito al cambiar de sección.
        self._pantallas: dict[str, ctk.CTkFrame] = {}
        self._botones_navegacion: dict[str, ctk.CTkButton] = {}
        self._mostrar_acceso()

    # Esto vuelve a mostrar la pantalla de login cuando se cierra sesión.
    def _mostrar_acceso(self) -> None:
        if self.barra:
            self.barra.destroy()
            self.barra = None
        if self.contenido:
            self.contenido.destroy()
            self.contenido = None
        self.pantalla = PantallaAcceso(self, self._iniciar_sesion)
        self.pantalla.pack(fill="both", expand=True)

    # Cuando el usuario entra bien, se carga la barra lateral y la pantalla principal.
    def _iniciar_sesion(self, usuario: sqlite3.Row) -> None:
        self.usuario = usuario
        if self.pantalla:
            self.pantalla.destroy()
            self.pantalla = None
        self._pantallas.clear()
        self.barra = ctk.CTkFrame(self, fg_color="#17191a", corner_radius=0)
        self.barra.pack(side="left", fill="y")
        self.barra.configure(width=190)
        self.barra.pack_propagate(False)
        ctk.CTkLabel(
            self.barra,
            text="▣  POS-Kontrol",
            text_color="#00c9b7",
            anchor="w",
            font=("Arial", 16, "bold"),
        ).pack(fill="x", padx=16, pady=(22, 30))
        ctk.CTkLabel(
            self.barra,
            text="OPERACIÓN",
            text_color="#969a9d",
            anchor="w",
            font=("Arial", 10, "bold"),
        ).pack(fill="x", padx=18, pady=(0, 8))
        self._botones_navegacion = {}
        # Desde aquí también se puede entrar a compras sin perder las otras pantallas.
        opciones_operacion = [
            ("Punto de venta", "venta"),
            ("Inventario", "inventario"),
        ]
        if usuario["rol"] == "ADMINISTRADOR":
            opciones_operacion.append(("Compras", "compras"))
        for nombre, destino in opciones_operacion:
            boton = ctk.CTkButton(
                self.barra,
                text=f"  ◈  {nombre}",
                height=36,
                anchor="w",
                fg_color="transparent",
                hover_color="#202224",
                text_color="#969a9d",
                command=lambda pantalla=destino: self._mostrar_pantalla(pantalla),
            )
            boton.pack(fill="x", padx=10, pady=2)
            self._botones_navegacion[destino] = boton
        ctk.CTkLabel(
            self.barra,
            text="ADMINISTRACIÓN",
            text_color="#969a9d",
            anchor="w",
            font=("Arial", 10, "bold"),
        ).pack(fill="x", padx=18, pady=(24, 8))
        if usuario["rol"] == "ADMINISTRADOR":
            ctk.CTkButton(
                self.barra,
                text="  ◈  Cajeros",
                height=34,
                anchor="w",
                fg_color="transparent",
                hover_color="#202224",
                text_color="#969a9d",
                command=self._abrir_usuarios,
            ).pack(fill="x", padx=10, pady=1)
        for opcion in ("Reportes", "Configuración"):
            ctk.CTkLabel(
                self.barra,
                text=f"  ◈  {opcion}",
                text_color="#969a9d",
                anchor="w",
                font=("Arial", 12),
            ).pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(
            self.barra,
            text=f"{usuario['nombre']}\n{usuario['rol']}",
            text_color="#eeeeee",
            anchor="w",
            justify="left",
            font=("Arial", 11),
        ).pack(side="bottom", fill="x", padx=16, pady=(12, 4))
        ctk.CTkButton(
            self.barra,
            text="Cerrar sesión",
            anchor="w",
            fg_color="transparent",
            hover_color="#202224",
            text_color="#969a9d",
            command=self._cerrar_sesion,
        ).pack(side="bottom", fill="x", padx=10, pady=(4, 16))
        self.contenido = ctk.CTkFrame(self, fg_color="transparent")
        self.contenido.pack(side="left", fill="both", expand=True)
        self._mostrar_pantalla("venta")

    def _mostrar_pantalla(self, nombre: str) -> None:
        if not self.contenido or not self.usuario:
            return
        if nombre == "compras" and self.usuario["rol"] != "ADMINISTRADOR":
            return
        if self.pantalla:
            self.pantalla.pack_forget()
        if nombre not in self._pantallas:
            # Cada pantalla se crea una sola vez y luego se vuelve a mostrar.
            if nombre == "venta":
                pantalla = PantallaPuntoVenta(self.contenido, self.usuario)
            elif nombre == "compras":
                # Esta pantalla usa el usuario actual para guardar quién hizo la compra.
                pantalla = PantallaCompras(self.contenido, self.usuario)
            else:
                pantalla = PantallaInventario(
                    self.contenido, mostrar_barra_lateral=False
                )
            self._pantallas[nombre] = pantalla
        self.pantalla = self._pantallas[nombre]
        self.pantalla.pack(fill="both", expand=True)
        if nombre == "inventario":
            self.pantalla.actualizar()
        elif nombre == "compras":
            # Se actualiza el historial al volver a compras después de guardar algo.
            self.pantalla.actualizar()
        else:
            self.pantalla._buscar_productos()
        for destino, boton in self._botones_navegacion.items():
            activo = destino == nombre
            boton.configure(
                fg_color="#123b37" if activo else "transparent",
                text_color="#00c9b7" if activo else "#969a9d",
                font=("Arial", 12, "bold" if activo else "normal"),
            )

    def _abrir_usuarios(self) -> None:
        if self.usuario and self.usuario["rol"] == "ADMINISTRADOR":
            VentanaCajeros(self.winfo_toplevel(), self.usuario)

    def _cerrar_sesion(self) -> None:
        self.usuario = None
        if self.pantalla:
            self.pantalla.destroy()
            self.pantalla = None
        self._pantallas.clear()
        self._mostrar_acceso()


def main() -> None:
    inicializar_base_datos()
    ctk.set_appearance_mode("dark")

    app = ctk.CTk()
    app.title("POS-Kontrol")
    app.minsize(950, 620)
    app.after(100, app.state, "zoomed")
    Aplicacion(app)
    app.mainloop()


if __name__ == "__main__":
    main()
