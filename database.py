from contextlib import contextmanager
import hashlib
import hmac
import sqlite3
import secrets
from pathlib import Path
from typing import Generator
from uuid import uuid4

RUTA_BASE_DATOS = Path(__file__).with_name("poskontrol.db")
ITERACIONES_CLAVE = 260_000


# Abre la base de datos y administra el cierre de la conexión.
@contextmanager
def _conectar() -> Generator[sqlite3.Connection, None, None]:
    conexion = sqlite3.connect(RUTA_BASE_DATOS)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    try:
        with conexion:
            yield conexion
    finally:
        conexion.close()


# Crea las tablas del sistema.
def inicializar_base_datos() -> None:
    with _conectar() as conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                nombre_usuario TEXT NOT NULL UNIQUE,
                clave_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('ADMINISTRADOR', 'VENDEDOR')),
                activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE
            )
            """
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                categoria_id INTEGER NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                precio_costo INTEGER NOT NULL CHECK (precio_costo >= 0),
                precio_venta INTEGER NOT NULL CHECK (precio_venta >= 0),
                stock_minimo INTEGER NOT NULL DEFAULT 2 CHECK (stock_minimo >= 0),
                codigo_barras TEXT,
                FOREIGN KEY (categoria_id) REFERENCES categorias (id)
            )
            """
        )
        columnas_producto = {
            columna["name"]
            for columna in conexion.execute("PRAGMA table_info(productos)")
        }
        if "codigo_barras" not in columnas_producto:
            conexion.execute("ALTER TABLE productos ADD COLUMN codigo_barras TEXT")
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
                descuento INTEGER NOT NULL DEFAULT 0 CHECK (descuento >= 0),
                total INTEGER NOT NULL CHECK (total >= 0),
                metodo_pago TEXT NOT NULL
                    CHECK (metodo_pago IN ('EFECTIVO', 'QR', 'BOLD', 'MIXTO')),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
            """
        )
        _migrar_ventas_pago_mixto(conexion)
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos_venta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL,
                metodo_pago TEXT NOT NULL
                    CHECK (metodo_pago IN ('EFECTIVO', 'QR', 'BOLD')),
                monto INTEGER NOT NULL CHECK (monto > 0),
                UNIQUE (venta_id, metodo_pago),
                FOREIGN KEY (venta_id) REFERENCES ventas (id)
            )
            """
        )
        conexion.execute(
            """
            INSERT INTO pagos_venta (venta_id, metodo_pago, monto)
            SELECT v.id, v.metodo_pago, v.total
            FROM ventas AS v
            WHERE v.metodo_pago IN ('EFECTIVO', 'QR', 'BOLD')
                AND v.total > 0
                AND NOT EXISTS (
                    SELECT 1 FROM pagos_venta AS p WHERE p.venta_id = v.id
                )
            """
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS detalle_ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad INTEGER NOT NULL CHECK (cantidad > 0),
                precio_unitario INTEGER NOT NULL CHECK (precio_unitario >= 0),
                costo_unitario INTEGER NOT NULL CHECK (costo_unitario >= 0),
                descuento INTEGER NOT NULL DEFAULT 0 CHECK (descuento >= 0),
                FOREIGN KEY (venta_id) REFERENCES ventas (id),
                FOREIGN KEY (producto_id) REFERENCES productos (id)
            )
            """
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS egresos_caja_menor (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                monto INTEGER NOT NULL CHECK (monto > 0),
                categoria TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
            """
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS cierres_caja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                fecha TEXT NOT NULL UNIQUE,
                total_ventas INTEGER NOT NULL CHECK (total_ventas >= 0),
                total_efectivo INTEGER NOT NULL CHECK (total_efectivo >= 0),
                total_qr INTEGER NOT NULL CHECK (total_qr >= 0),
                total_bold INTEGER NOT NULL CHECK (total_bold >= 0),
                total_egresos INTEGER NOT NULL CHECK (total_egresos >= 0),
                efectivo_esperado INTEGER NOT NULL CHECK (efectivo_esperado >= 0),
                efectivo_contado INTEGER NOT NULL CHECK (efectivo_contado >= 0),
                ganancia_bruta INTEGER NOT NULL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_productos_nombre ON productos (nombre)"
        )
        conexion.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_productos_codigo_barras
            ON productos (codigo_barras)
            WHERE codigo_barras IS NOT NULL AND codigo_barras != ''
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas (fecha)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagos_venta_metodo "
            "ON pagos_venta (metodo_pago, venta_id)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_egresos_fecha "
            "ON egresos_caja_menor (fecha)"
        )


def _migrar_ventas_pago_mixto(conexion: sqlite3.Connection) -> None:
    # Reconstruye el esquema anterior para aceptar MIXTO sin perder ventas ni detalles.
    esquema = conexion.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ventas'"
    ).fetchone()
    if not esquema or "'MIXTO'" in esquema["sql"]:
        return

    conexion.execute("PRAGMA foreign_keys = OFF")
    conexion.execute("BEGIN IMMEDIATE")
    try:
        conexion.execute("ALTER TABLE detalle_ventas RENAME TO detalle_ventas_anterior")
        conexion.execute("ALTER TABLE ventas RENAME TO ventas_anterior")
        conexion.execute(
            """
            CREATE TABLE ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
                descuento INTEGER NOT NULL DEFAULT 0 CHECK (descuento >= 0),
                total INTEGER NOT NULL CHECK (total >= 0),
                metodo_pago TEXT NOT NULL
                    CHECK (metodo_pago IN ('EFECTIVO', 'QR', 'BOLD', 'MIXTO')),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
            """
        )
        conexion.execute(
            """
            INSERT INTO ventas (
                id, usuario_id, fecha, subtotal, descuento, total, metodo_pago
            )
            SELECT
                id, usuario_id, fecha, subtotal, descuento, total, metodo_pago
            FROM ventas_anterior
            """
        )
        conexion.execute(
            """
            CREATE TABLE detalle_ventas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad INTEGER NOT NULL CHECK (cantidad > 0),
                precio_unitario INTEGER NOT NULL CHECK (precio_unitario >= 0),
                costo_unitario INTEGER NOT NULL CHECK (costo_unitario >= 0),
                descuento INTEGER NOT NULL DEFAULT 0 CHECK (descuento >= 0),
                FOREIGN KEY (venta_id) REFERENCES ventas (id),
                FOREIGN KEY (producto_id) REFERENCES productos (id)
            )
            """
        )
        conexion.execute(
            """
            INSERT INTO detalle_ventas (
                id, venta_id, producto_id, cantidad, precio_unitario,
                costo_unitario, descuento
            )
            SELECT
                id, venta_id, producto_id, cantidad, precio_unitario,
                costo_unitario, descuento
            FROM detalle_ventas_anterior
            """
        )
        conexion.execute("DROP TABLE detalle_ventas_anterior")
        conexion.execute("DROP TABLE ventas_anterior")
        conexion.commit()
    except sqlite3.Error:
        conexion.rollback()
        raise
    finally:
        conexion.execute("PRAGMA foreign_keys = ON")


# Esto valida que el producto tenga nombre, categoría y números bien.
def _validar_producto(
    nombre: str,
    categoria_id: int,
    stock: int,
    precio_costo: int,
    precio_venta: int,
    stock_minimo: int,
) -> str:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del producto es obligatorio.")
    if categoria_id <= 0:
        raise ValueError("Selecciona una categoría válida.")
    if min(stock, precio_costo, precio_venta, stock_minimo) < 0:
        raise ValueError("El stock y los precios no pueden ser negativos.")
    return nombre


# Aquí se revisa que el usuario y la contraseña tengan datos válidos.
def _validar_usuario(nombre: str, nombre_usuario: str, clave: str) -> tuple[str, str]:
    nombre = nombre.strip()
    nombre_usuario = nombre_usuario.strip().casefold()
    if not nombre or not nombre_usuario:
        raise ValueError("El nombre y el usuario son obligatorios.")
    if len(clave) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    return nombre, nombre_usuario


# Aquí se guarda la clave con hash para que no quede en texto plano.
def _hash_clave(clave: str, sal: bytes | None = None) -> str:
    # Cada contraseña usa una sal aleatoria y un cálculo repetido antes de guardarse.
    sal = sal or secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac(
        "sha256", clave.encode("utf-8"), sal, ITERACIONES_CLAVE
    )
    return f"pbkdf2_sha256${ITERACIONES_CLAVE}${sal.hex()}${resumen.hex()}"


# Esto compara la clave ingresada con la que está guardada.
def _verificar_clave(clave: str, almacenada: str) -> bool:
    try:
        algoritmo, iteraciones, sal_hex, resumen_hex = almacenada.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        sal = bytes.fromhex(sal_hex)
        esperado = bytes.fromhex(resumen_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", clave.encode("utf-8"), sal, int(iteraciones)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, esperado)


# Esto cuenta cuántos usuarios hay para saber si falta crear el admin.
def contar_usuarios() -> int:
    with _conectar() as conexion:
        return conexion.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]


# Esto crea el primer admin cuando la app se abre por primera vez.
def crear_administrador_inicial(
    nombre: str, nombre_usuario: str, clave: str
) -> int:
    nombre, nombre_usuario = _validar_usuario(nombre, nombre_usuario, clave)
    with _conectar() as conexion:
        # La transacción evita crear dos administradores iniciales al mismo tiempo.
        conexion.execute("BEGIN IMMEDIATE")
        if conexion.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
            raise LookupError("El administrador inicial ya fue creado.")
        cursor = conexion.execute(
            """
            INSERT INTO usuarios (nombre, nombre_usuario, clave_hash, rol)
            VALUES (?, ?, ?, 'ADMINISTRADOR')
            """,
            (nombre, nombre_usuario, _hash_clave(clave)),
        )
        return cursor.lastrowid


# Esto hace que solo el admin pueda crear cajeros nuevos.
def crear_cajero(
    administrador_id: int, nombre: str, nombre_usuario: str, clave: str
) -> int:
    nombre, nombre_usuario = _validar_usuario(nombre, nombre_usuario, clave)
    with _conectar() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        administrador = conexion.execute(
            "SELECT rol, activo FROM usuarios WHERE id = ?", (administrador_id,)
        ).fetchone()
        if not administrador or administrador["rol"] != "ADMINISTRADOR":
            raise PermissionError("Solo un administrador puede crear cajeros.")
        if not administrador["activo"]:
            raise PermissionError("La cuenta de administrador está inactiva.")
        cursor = conexion.execute(
            """
            INSERT INTO usuarios (nombre, nombre_usuario, clave_hash, rol)
            VALUES (?, ?, ?, 'VENDEDOR')
            """,
            (nombre, nombre_usuario, _hash_clave(clave)),
        )
        return cursor.lastrowid


# Aquí se valida que el usuario exista, la clave sea correcta y esté activo.
def autenticar_usuario(nombre_usuario: str, clave: str) -> sqlite3.Row | None:
    nombre_usuario = nombre_usuario.strip().casefold()
    with _conectar() as conexion:
        usuario = conexion.execute(
            """
            SELECT id, nombre, nombre_usuario, clave_hash, rol, activo
            FROM usuarios
            WHERE nombre_usuario = ?
            """,
            (nombre_usuario,),
        ).fetchone()
    if (
        not usuario
        or not usuario["activo"]
        or not _verificar_clave(clave, usuario["clave_hash"])
    ):
        return None
    return usuario


def listar_usuarios() -> list[sqlite3.Row]:
    with _conectar() as conexion:
        return conexion.execute(
            """
            SELECT id, nombre, nombre_usuario, rol, activo
            FROM usuarios
            ORDER BY nombre
            """
        ).fetchall()


# Esto guarda la categoría en la base de datos y devuelve su id.
def agregar_categoria(nombre: str) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de la categoría es obligatorio.")
    with _conectar() as conexion:
        cursor = conexion.execute(
            "INSERT INTO categorias (nombre) VALUES (?)",
            (nombre,),
        )
        return cursor.lastrowid


# Aquí se traen las categorías ordenadas para mostrarlas en la app.
def listar_categorias() -> list[sqlite3.Row]:
    with _conectar() as conexion:
        return conexion.execute(
            "SELECT id, nombre FROM categorias ORDER BY nombre"
        ).fetchall()


# Esto crea el producto y le asigna un SKU para identificarlo.
def agregar_producto(
    nombre: str,
    categoria_id: int,
    stock: int,
    precio_costo: int,
    precio_venta: int,
    stock_minimo: int = 2,
    codigo_barras: str | None = None,
) -> str:
    nombre = _validar_producto(
        nombre, categoria_id, stock, precio_costo, precio_venta, stock_minimo
    )
    if codigo_barras is not None:
        codigo_barras = codigo_barras.strip() or None
    with _conectar() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        cursor = conexion.execute(
            """
            INSERT INTO productos (
                codigo, nombre, categoria_id, stock, precio_costo,
                precio_venta, stock_minimo, codigo_barras
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"__SKU_PENDIENTE_{uuid4().hex}__",
                nombre,
                categoria_id,
                stock,
                precio_costo,
                precio_venta,
                stock_minimo,
                codigo_barras,
            ),
        )
        producto_id = cursor.lastrowid
        numero_sku = producto_id
        while True:
            codigo = f"SKU-{numero_sku:06d}"
            repetido = conexion.execute(
                "SELECT 1 FROM productos WHERE codigo = ?",
                (codigo,),
            ).fetchone()
            if repetido is None:
                break
            numero_sku += 1
        conexion.execute(
            "UPDATE productos SET codigo = ? WHERE id = ?",
            (codigo, producto_id),
        )
        return codigo


# Esta búsqueda sirve para encontrar productos por nombre, SKU o código de barras.
def listar_productos(busqueda: str = "") -> list[sqlite3.Row]:
    busqueda = busqueda.strip()
    patron = f"%{busqueda}%"
    with _conectar() as conexion:
        return conexion.execute(
            """
            SELECT
                p.id, p.codigo, p.nombre, p.categoria_id, c.nombre AS categoria,
                p.stock, p.precio_costo, p.precio_venta, p.stock_minimo,
                p.codigo_barras
            FROM productos AS p
            JOIN categorias AS c ON c.id = p.categoria_id
            WHERE p.codigo LIKE ? OR p.codigo_barras LIKE ? OR p.nombre LIKE ?
            ORDER BY p.nombre
            """,
            (patron, patron, patron),
        ).fetchall()


# Aquí se actualizan los datos del producto sin perder su referencia.
def editar_producto(
    producto_id: int,
    nombre: str,
    categoria_id: int,
    stock: int,
    precio_costo: int,
    precio_venta: int,
    stock_minimo: int = 2,
    codigo_barras: str | None = None,
) -> None:
    if producto_id <= 0:
        raise ValueError("El identificador del producto no es válido.")
    nombre = _validar_producto(
        nombre, categoria_id, stock, precio_costo, precio_venta, stock_minimo
    )
    if codigo_barras is not None:
        codigo_barras = codigo_barras.strip() or None
    with _conectar() as conexion:
        cursor = conexion.execute(
            """
            UPDATE productos
            SET nombre = ?, categoria_id = ?, stock = ?, precio_costo = ?,
                precio_venta = ?, stock_minimo = ?, codigo_barras = ?
            WHERE id = ?
            """,
            (
                nombre,
                categoria_id,
                stock,
                precio_costo,
                precio_venta,
                stock_minimo,
                codigo_barras,
                producto_id,
            ),
        )
        if cursor.rowcount == 0:
            raise LookupError("No se encontró el producto que quieres editar.")


def registrar_venta(
    usuario_id: int,
    productos: list[dict[str, int]],
    pagos: dict[str, int],
) -> tuple[int, int]:
    # Se valida la información antes de modificar las existencias o crear la venta.
    metodos_validos = {"EFECTIVO", "QR", "BOLD"}
    if not isinstance(pagos, dict) or not pagos:
        raise ValueError("Selecciona al menos un método de pago.")
    if any(
        metodo not in metodos_validos or type(monto) is not int or monto < 0
        for metodo, monto in pagos.items()
    ):
        raise ValueError("Los valores de pago deben ser enteros no negativos.")
    if not productos:
        raise ValueError("Agrega al menos un producto a la venta.")

    ids_vistos = set()
    for item in productos:
        producto_id = item.get("producto_id")
        cantidad = item.get("cantidad")
        descuento = item.get("descuento", 0)
        if (
            not isinstance(producto_id, int)
            or not isinstance(cantidad, int)
            or not isinstance(descuento, int)
            or producto_id <= 0
            or cantidad <= 0
            or descuento < 0
        ):
            raise ValueError("La cantidad y el descuento deben ser válidos.")
        if producto_id in ids_vistos:
            raise ValueError("Un producto no puede repetirse en la venta.")
        ids_vistos.add(producto_id)

    with _conectar() as conexion:
        # Venta, pagos, detalles y descuento de stock quedan en una sola transacción.
        conexion.execute("BEGIN IMMEDIATE")
        usuario = conexion.execute(
            "SELECT activo FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if not usuario or not usuario["activo"]:
            raise LookupError("El usuario no existe o está inactivo.")

        lineas = []
        subtotal = 0
        descuento_total = 0
        for item in productos:
            producto = conexion.execute(
                """
                SELECT id, nombre, stock, precio_venta, precio_costo
                FROM productos
                WHERE id = ?
                """,
                (item["producto_id"],),
            ).fetchone()
            if not producto:
                raise LookupError("Uno de los productos ya no está disponible.")
            if item["cantidad"] > producto["stock"]:
                raise ValueError(
                    f"No hay existencias suficientes de {producto['nombre']}."
                )
            total_linea = item["cantidad"] * producto["precio_venta"]
            if item.get("descuento", 0) > total_linea:
                raise ValueError(
                    f"El descuento de {producto['nombre']} supera el valor de la línea."
                )
            subtotal += total_linea
            descuento_total += item.get("descuento", 0)
            lineas.append((producto, item["cantidad"], item.get("descuento", 0)))

        total = subtotal - descuento_total
        if sum(pagos.values()) != total:
            raise ValueError("La suma de los pagos debe ser igual al total.")
        # Los métodos en cero no se guardan; MIXTO indica que hubo más de uno.
        pagos_activos = {
            metodo: monto for metodo, monto in pagos.items() if monto > 0
        }
        metodo_venta = (
            next(iter(pagos_activos)) if len(pagos_activos) == 1 else "MIXTO"
        )
        cursor = conexion.execute(
            """
            INSERT INTO ventas (
                usuario_id, subtotal, descuento, total, metodo_pago
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (usuario_id, subtotal, descuento_total, total, metodo_venta),
        )
        venta_id = cursor.lastrowid
        for metodo, monto in pagos_activos.items():
            conexion.execute(
                """
                INSERT INTO pagos_venta (venta_id, metodo_pago, monto)
                VALUES (?, ?, ?)
                """,
                (venta_id, metodo, monto),
            )
        for producto, cantidad, descuento in lineas:
            conexion.execute(
                """
                INSERT INTO detalle_ventas (
                    venta_id, producto_id, cantidad, precio_unitario,
                    costo_unitario, descuento
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    venta_id,
                    producto["id"],
                    cantidad,
                    producto["precio_venta"],
                    producto["precio_costo"],
                    descuento,
                ),
            )
            conexion.execute(
                """
                UPDATE productos
                SET stock = stock - ?
                WHERE id = ? AND stock >= ?
                """,
                (cantidad, producto["id"], cantidad),
            )
        return venta_id, total
