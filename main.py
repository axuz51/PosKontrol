import customtkinter as ctk

from database import inicializar_base_datos
from pantallas.inventario import PantallaInventario


# Inicia la aplicación.
def main():
    inicializar_base_datos()
    ctk.set_appearance_mode("dark")

    app = ctk.CTk()
    app.title("POS-Kontrol")
    app.minsize(950, 620)
    app.after(100, app.state, "zoomed")

    pantalla = PantallaInventario(app)
    pantalla.pack(fill="both", expand=True)

    app.mainloop()


if __name__ == "__main__":
    main()
