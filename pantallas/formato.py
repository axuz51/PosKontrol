# Aquí se deja el dinero con el formato que usamos en la app.
def formatear_pesos(valor: int) -> str:
    return f"$ {formatear_numero(valor)}"


# Esto cambia los números normales para que se vean con puntos de miles.
def formatear_numero(valor: int) -> str:
    # La interfaz usa puntos como separadores de miles.
    return f"{valor:,}".replace(",", ".")


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
