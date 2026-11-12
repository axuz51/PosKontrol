import sqlite3
from collections.abc import Callable
from tkinter import messagebox

import customtkinter as ctk

from database import (
    autenticar_usuario,
    contar_usuarios,
    crear_administrador_inicial,
    crear_cajero,
    listar_usuarios,
)

FONDO = "#111315"
PANEL = "#1b1d1f"
ACENTO = "#00c9b7"
TEXTO = "#eeeeee"
TEXTO_SUAVE = "#969a9d"


# Esta pantalla sirve para iniciar sesión y también para crear el primer admin.
class PantallaAcceso(ctk.CTkFrame):
    def __init__(
        self, master, al_ingresar: Callable[[sqlite3.Row], None]
    ) -> None:
        super().__init__(master, fg_color=FONDO)
        self._al_ingresar = al_ingresar
        # Si no hay usuarios registrados, el primer formulario crea al administrador.
        self._crear_administrador = contar_usuarios() == 0
        self._crear_formulario()

    # Aquí se arma el formulario según si ya existe un admin o no.
    def _crear_formulario(self) -> None:
        caja = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
        caja.place(relx=0.5, rely=0.5, anchor="center")

        titulo = "Crear administrador" if self._crear_administrador else "Iniciar sesión"
        ctk.CTkLabel(
            caja, text="POS-Kontrol", text_color=ACENTO, font=("Arial", 23, "bold")
        ).pack(padx=36, pady=(28, 4))
        ctk.CTkLabel(
            caja, text=titulo, text_color=TEXTO, font=("Arial", 17, "bold")
        ).pack(pady=(0, 18))

        self.entradas: dict[str, ctk.CTkEntry] = {}
        campos = []
        if self._crear_administrador:
            campos.append(("Nombre completo", False))
        campos.extend((("Usuario", False), ("Contraseña", True)))
        if self._crear_administrador:
            campos.append(("Confirmar contraseña", True))

        for etiqueta, ocultar in campos:
            entrada = ctk.CTkEntry(
                caja,
                width=310,
                height=38,
                placeholder_text=etiqueta,
                show="*" if ocultar else "",
            )
            entrada.pack(padx=28, pady=5)
            entrada.bind("<Return>", self._enviar_con_enter)
            self.entradas[etiqueta] = entrada

        boton = ctk.CTkButton(
            caja,
            text="Crear administrador" if self._crear_administrador else "Ingresar",
            width=310,
            height=38,
            fg_color=ACENTO,
            hover_color="#00ad9e",
            text_color="#101616",
            command=self._enviar,
        )
        boton.pack(padx=28, pady=(14, 28))
        self.entradas["Usuario"].focus()

    def _enviar_con_enter(self, _evento) -> str:
        self._enviar()
        return "break"

    def _enviar(self) -> None:
        usuario = self.entradas["Usuario"].get()
        clave = self.entradas["Contraseña"].get()
        try:
            if self._crear_administrador:
                confirmar = self.entradas["Confirmar contraseña"].get()
                if clave != confirmar:
                    raise ValueError("Las contraseñas no coinciden.")
                crear_administrador_inicial(
                    self.entradas["Nombre completo"].get(), usuario, clave
                )
                self._crear_administrador = False
            # El administrador recién creado inicia sesión por el mismo flujo normal.
            autenticado = autenticar_usuario(usuario, clave)
            if autenticado is None:
                messagebox.showwarning(
                    "Acceso denegado",
                    "El usuario o la contraseña no son correctos.",
                    parent=self,
                )
                return
        except ValueError as error:
            messagebox.showwarning("Revisa los datos", str(error), parent=self)
            return
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Usuario existente",
                "Ese nombre de usuario ya está registrado.",
                parent=self,
            )
            return
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo validar el acceso:\n{error}",
                parent=self,
            )
            return

        self._al_ingresar(autenticado)


# Esta ventana sirve para ver los usuarios y crear cajeros nuevos.
class VentanaCajeros(ctk.CTkToplevel):
    def __init__(self, master, administrador: sqlite3.Row) -> None:
        super().__init__(master)
        self._administrador = administrador
        self.title("Usuarios")
        self.geometry("470x540")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._crear_interfaz()

    # Aquí se arma la lista de usuarios y el formulario para crear cajeros.
    def _crear_interfaz(self) -> None:
        ctk.CTkLabel(
            self, text="Usuarios del sistema", font=("Arial", 19, "bold")
        ).pack(anchor="w", padx=22, pady=(20, 10))
        self.lista = ctk.CTkScrollableFrame(self, fg_color=PANEL, height=180)
        self.lista.pack(fill="x", padx=22, pady=(0, 16))
        self._actualizar_lista()

        ctk.CTkLabel(
            self, text="Crear cajero", font=("Arial", 16, "bold")
        ).pack(anchor="w", padx=22, pady=(4, 8))
        self.entradas: dict[str, ctk.CTkEntry] = {}
        for etiqueta, ocultar in (
            ("Nombre completo", False),
            ("Usuario", False),
            ("Contraseña (mínimo 8 caracteres)", True),
        ):
            entrada = ctk.CTkEntry(
                self,
                height=36,
                placeholder_text=etiqueta,
                show="*" if ocultar else "",
            )
            entrada.pack(fill="x", padx=22, pady=5)
            self.entradas[etiqueta] = entrada

        ctk.CTkButton(
            self,
            text="Guardar cajero",
            fg_color=ACENTO,
            text_color="#101616",
            command=self._guardar,
        ).pack(anchor="e", padx=22, pady=16)

    def _actualizar_lista(self) -> None:
        for widget in self.lista.winfo_children():
            widget.destroy()
        try:
            usuarios = listar_usuarios()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudieron cargar los usuarios:\n{error}",
                parent=self,
            )
            return
        for usuario in usuarios:
            estado = "Activo" if usuario["activo"] else "Inactivo"
            ctk.CTkLabel(
                self.lista,
                text=f"{usuario['nombre']} · {usuario['rol']} · {estado}",
                anchor="w",
            ).pack(fill="x", padx=10, pady=7)

    def _guardar(self) -> None:
        # La base de datos también comprueba que quien crea cajeros sea administrador.
        try:
            crear_cajero(
                self._administrador["id"],
                self.entradas["Nombre completo"].get(),
                self.entradas["Usuario"].get(),
                self.entradas["Contraseña (mínimo 8 caracteres)"].get(),
            )
        except ValueError as error:
            messagebox.showwarning("Revisa los datos", str(error), parent=self)
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Usuario existente",
                "Ese nombre de usuario ya está registrado.",
                parent=self,
            )
        except (sqlite3.Error, PermissionError) as error:
            messagebox.showerror(
                "No se pudo crear el cajero", str(error), parent=self
            )
        else:
            self._actualizar_lista()
            for entrada in self.entradas.values():
                entrada.delete(0, "end")
            messagebox.showinfo("Usuario creado", "El cajero quedó registrado.", parent=self)
