import customtkinter as ctk


# Configura y muestra la ventana principal del sistema.
def main():
    ctk.set_appearance_mode("system")

    app = ctk.CTk()
    app.title("POS-Kontrol")
    app.geometry("900x600")

    titulo = ctk.CTkLabel(app, text="POS-Kontrol", font=("Arial", 28, "bold"))
    titulo.pack(pady=40)

    app.mainloop()


if __name__ == "__main__":
    main()
