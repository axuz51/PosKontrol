import tkinter as tk


# Aquí se deja el dinero con el formato que usamos en la app.
def formatear_pesos(valor: int) -> str:
    return f"$ {formatear_numero(valor)}"


# Esto cambia los números normales para que se vean con puntos de miles.
def formatear_numero(valor: int) -> str:
    # La interfaz usa puntos como separadores de miles.
    return f"{valor:,}".replace(",", ".")


# Al agregar puntos de miles, el cursor se ubica según los dígitos que tenía antes.
def formatear_entrada_precio(evento: tk.Event) -> None:
    entrada = evento.widget
    texto = entrada.get()
    if not texto or any(not caracter.isdecimal() and caracter != "." for caracter in texto):
        return
    posicion = entrada.index(tk.INSERT)
    digitos_antes = sum(caracter.isdecimal() for caracter in texto[:posicion])
    digitos = "".join(caracter for caracter in texto if caracter.isdecimal())
    if not digitos:
        return
    valor = int(digitos)
    formateado = formatear_numero(valor)
    nueva_posicion = 0
    digitos_contados = 0
    while nueva_posicion < len(formateado) and digitos_contados < digitos_antes:
        if formateado[nueva_posicion].isdecimal():
            digitos_contados += 1
        nueva_posicion += 1
    entrada.delete(0, "end")
    entrada.insert(0, formateado)
    entrada.icursor(nueva_posicion)


# Este método recibe el texto del input y lo convierte a número entero.
def leer_importe(valor: str) -> int:
    # Se quitan los separadores solo después de comprobar que estén bien agrupados.
    partes = valor.strip().split(".")
    if not partes or not partes[0].isdecimal():
        raise ValueError("Ingresa un valor entero válido.")
    if len(partes) > 1 and (
        not 1 <= len(partes[0]) <= 3
        or any(len(parte) != 3 or not parte.isdecimal() for parte in partes[1:])
    ):
        raise ValueError("Usa puntos solo para separar grupos de miles.")
    return int("".join(partes))
