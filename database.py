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
        # Aquí quedan guardados los datos de contacto de cada proveedor.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS proveedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                telefono TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Esta tabla guarda los datos generales de cada compra.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                proveedor_id INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                total INTEGER NOT NULL CHECK (total >= 0),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
                FOREIGN KEY (proveedor_id) REFERENCES proveedores (id)
            )
            """
        )
        # En cada detalle se guarda el producto, cuántas unidades llegaron y su costo.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS detalle_compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL,
                producto_id INTEGER NOT NULL,
                cantidad INTEGER NOT NULL CHECK (cantidad > 0),
                costo_unitario INTEGER NOT NULL CHECK (costo_unitario >= 0),
                precio_venta INTEGER CHECK (precio_venta >= 0),
                FOREIGN KEY (compra_id) REFERENCES compras (id),
                FOREIGN KEY (producto_id) REFERENCES productos (id)
            )
            """
        )
        columnas_detalle_compra = {
            columna["name"]
            for columna in conexion.execute("PRAGMA table_info(detalle_compras)")
        }
        # En las compras antiguas el precio de venta no quedó guardado.
        if "precio_venta" not in columnas_detalle_compra:
            conexion.execute(
                "ALTER TABLE detalle_compras ADD COLUMN precio_venta INTEGER "
                "CHECK (precio_venta >= 0)"
            )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_ediciones_compras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compra_id INTEGER NOT NULL,
                detalle_compra_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                producto_nombre TEXT NOT NULL,
                campo TEXT NOT NULL CHECK (
                    campo IN ('cantidad', 'costo_unitario', 'precio_venta')
                ),
                valor_anterior INTEGER,
                valor_nuevo INTEGER NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (compra_id) REFERENCES compras (id),
                FOREIGN KEY (detalle_compra_id) REFERENCES detalle_compras (id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
            """
        )
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
        # Este índice ayuda a ordenar las compras por fecha cuando se consultan.
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_compras_fecha ON compras (fecha)"
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


# Este método crea el producto dentro de una conexión que ya está abierta.
def _insertar_producto(
    conexion: sqlite3.Connection,
    nombre: str,
    categoria_id: int,
    stock: int,
    precio_costo: int,
    precio_venta: int,
    stock_minimo: int,
    codigo_barras: str | None,
) -> tuple[int, str]:
    nombre = _validar_producto(
        nombre, categoria_id, stock, precio_costo, precio_venta, stock_minimo
    )
    if codigo_barras is not None:
        codigo_barras = codigo_barras.strip() or None
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
    return producto_id, codigo


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
    with _conectar() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        _producto_id, codigo = _insertar_producto(
            conexion,
            nombre,
            categoria_id,
            stock,
            precio_costo,
            precio_venta,
            stock_minimo,
            codigo_barras,
        )
        return codigo


# Esta búsqueda sirve para encontrar productos por nombre, SKU o código de barras.
def listar_productos(
    busqueda: str = "", limite: int | None = None
) -> list[sqlite3.Row]:
    busqueda = busqueda.strip()
    patron = f"%{busqueda}%"
    # En compras se limita la lista para que la búsqueda no cargue todo el inventario.
    if limite is not None and limite <= 0:
        raise ValueError("El límite de productos debe ser mayor que cero.")
    with _conectar() as conexion:
        consulta = """
            SELECT
                p.id, p.codigo, p.nombre, p.categoria_id, c.nombre AS categoria,
                p.stock, p.precio_costo, p.precio_venta, p.stock_minimo,
                p.codigo_barras
            FROM productos AS p
            JOIN categorias AS c ON c.id = p.categoria_id
            WHERE p.codigo LIKE ? OR p.codigo_barras LIKE ? OR p.nombre LIKE ?
            ORDER BY p.nombre
        """
        parametros: tuple = (patron, patron, patron)
        if limite is not None:
            consulta += " LIMIT ?"
            parametros += (limite,)
        return conexion.execute(consulta, parametros).fetchall()


# Aquí se guarda el proveedor con su teléfono si se quiere registrar.
def agregar_proveedor(nombre: str, telefono: str = "") -> int:
    nombre = nombre.strip()
    telefono = telefono.strip()
    if not nombre:
        raise ValueError("El nombre del proveedor es obligatorio.")
    with _conectar() as conexion:
        cursor = conexion.execute(
            "INSERT INTO proveedores (nombre, telefono) VALUES (?, ?)",
            (nombre, telefono),
        )
        return cursor.lastrowid


# Esta lista se usa para escoger el proveedor al registrar una compra.
def listar_proveedores() -> list[sqlite3.Row]:
    with _conectar() as conexion:
        return conexion.execute(
            "SELECT id, nombre, telefono FROM proveedores ORDER BY nombre"
        ).fetchall()


# Aquí se consultan las compras más recientes para mostrarlas en la pantalla.
def listar_compras() -> list[sqlite3.Row]:
    with _conectar() as conexion:
        return conexion.execute(
            """
            SELECT c.id, c.fecha, c.total, p.nombre AS proveedor
            FROM compras AS c
            JOIN proveedores AS p ON p.id = c.proveedor_id
            ORDER BY c.fecha DESC, c.id DESC
            LIMIT 100
            """
        ).fetchall()


# Esta consulta trae quién registró la compra y los productos que llegaron.
def obtener_detalle_compra(
    compra_id: int,
) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with _conectar() as conexion:
        compra = conexion.execute(
            """
            SELECT c.id, c.fecha, c.total, p.nombre AS proveedor,
                   u.nombre AS usuario
            FROM compras AS c
            JOIN proveedores AS p ON p.id = c.proveedor_id
            JOIN usuarios AS u ON u.id = c.usuario_id
            WHERE c.id = ?
            """,
            (compra_id,),
        ).fetchone()
        if not compra:
            return None, []
        productos = conexion.execute(
            """
            SELECT dc.id AS detalle_id, dc.precio_venta,
                   pr.codigo, pr.nombre, dc.cantidad, dc.costo_unitario,
                   dc.cantidad * dc.costo_unitario AS subtotal
            FROM detalle_compras AS dc
            JOIN productos AS pr ON pr.id = dc.producto_id
            WHERE dc.compra_id = ?
            ORDER BY dc.id
            """,
            (compra_id,),
        ).fetchall()
        return compra, productos


# Aquí se consultan los cambios hechos para que no se pierda el historial.
def listar_ediciones_compra(compra_id: int) -> list[sqlite3.Row]:
    with _conectar() as conexion:
        return conexion.execute(
            """
            SELECT fecha, producto_nombre, campo, valor_anterior,
                   valor_nuevo, usuarios.nombre AS usuario
            FROM historial_ediciones_compras AS historial
            JOIN usuarios ON usuarios.id = historial.usuario_id
            WHERE historial.compra_id = ?
            ORDER BY historial.id DESC
            LIMIT 50
            """,
            (compra_id,),
        ).fetchall()


# Esta función corrige la compra y el inventario dentro de una sola transacción.
def editar_compra(
    compra_id: int,
    usuario_id: int,
    lineas: list[dict[str, int | None]],
) -> int:
    if type(compra_id) is not int or compra_id <= 0:
        raise ValueError("La compra seleccionada no es válida.")
    if type(usuario_id) is not int or usuario_id <= 0:
        raise ValueError("El usuario no es válido.")
    if not lineas:
        raise ValueError("La compra debe conservar al menos un producto.")

    cambios_por_detalle: dict[int, dict[str, int | None]] = {}
    for linea in lineas:
        detalle_id = linea.get("detalle_id")
        cantidad = linea.get("cantidad")
        costo_unitario = linea.get("costo_unitario")
        precio_venta = linea.get("precio_venta")
        if (
            type(detalle_id) is not int
            or detalle_id <= 0
            or type(cantidad) is not int
            or cantidad <= 0
            or type(costo_unitario) is not int
            or costo_unitario < 0
            or precio_venta is not None
            and (type(precio_venta) is not int or precio_venta < 0)
        ):
            raise ValueError("Revisa las cantidades y los precios de la compra.")
        if detalle_id in cambios_por_detalle:
            raise ValueError("Un producto no puede repetirse en la corrección.")
        cambios_por_detalle[detalle_id] = {
            "cantidad": cantidad,
            "costo_unitario": costo_unitario,
            "precio_venta": precio_venta,
        }

    with _conectar() as conexion:
        conexion.execute("BEGIN IMMEDIATE")
        usuario = conexion.execute(
            "SELECT activo, rol FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if not usuario or not usuario["activo"]:
            raise LookupError("El usuario no existe o está inactivo.")
        if usuario["rol"] != "ADMINISTRADOR":
            raise PermissionError("Solo el administrador puede corregir compras.")
        compra = conexion.execute(
            "SELECT id, fecha FROM compras WHERE id = ?", (compra_id,)
        ).fetchone()
        if not compra:
            raise LookupError("No se encontró la compra seleccionada.")
        detalles = conexion.execute(
            """
            SELECT dc.id, dc.producto_id, dc.cantidad, dc.costo_unitario,
                   dc.precio_venta, p.nombre, p.stock
            FROM detalle_compras AS dc
            JOIN productos AS p ON p.id = dc.producto_id
            WHERE dc.compra_id = ?
            """,
            (compra_id,),
        ).fetchall()
        ids_guardados = {detalle["id"] for detalle in detalles}
        if ids_guardados != set(cambios_por_detalle):
            raise ValueError("La lista de productos cambió. Vuelve a abrir la compra.")

        total = 0
        for detalle in detalles:
            valores = cambios_por_detalle[detalle["id"]]
            cantidad = valores["cantidad"]
            costo_unitario = valores["costo_unitario"]
            precio_venta = valores["precio_venta"]
            if precio_venta is None and detalle["precio_venta"] is not None:
                precio_venta = detalle["precio_venta"]

            diferencia_stock = cantidad - detalle["cantidad"]
            if diferencia_stock:
                cursor = conexion.execute(
                    """
                    UPDATE productos
                    SET stock = stock + ?
                    WHERE id = ? AND stock + ? >= 0
                    """,
                    (
                        diferencia_stock,
                        detalle["producto_id"],
                        diferencia_stock,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ValueError(
                        f"No se puede reducir la cantidad de {detalle['nombre']}: "
                        "ya se vendieron unidades y el stock quedaría negativo."
                    )

            es_compra_mas_reciente = not conexion.execute(
                """
                SELECT 1
                FROM detalle_compras AS otra_linea
                JOIN compras AS otra_compra ON otra_compra.id = otra_linea.compra_id
                WHERE otra_linea.producto_id = ?
                    AND (
                        otra_compra.fecha > ?
                        OR (otra_compra.fecha = ? AND otra_compra.id > ?)
                    )
                LIMIT 1
                """,
                (
                    detalle["producto_id"],
                    compra["fecha"],
                    compra["fecha"],
                    compra_id,
                ),
            ).fetchone()
            if es_compra_mas_reciente:
                actualizaciones_producto = []
                parametros_producto: list[int] = []
                if costo_unitario != detalle["costo_unitario"]:
                    actualizaciones_producto.append("precio_costo = ?")
                    parametros_producto.append(costo_unitario)
                if (
                    valores["precio_venta"] is not None
                    and valores["precio_venta"] != detalle["precio_venta"]
                ):
                    actualizaciones_producto.append("precio_venta = ?")
                    parametros_producto.append(valores["precio_venta"])
                if actualizaciones_producto:
                    parametros_producto.append(detalle["producto_id"])
                    conexion.execute(
                        f"UPDATE productos SET {', '.join(actualizaciones_producto)} "
                        "WHERE id = ?",
                        parametros_producto,
                    )

            for campo, valor_anterior, valor_nuevo in (
                ("cantidad", detalle["cantidad"], cantidad),
                ("costo_unitario", detalle["costo_unitario"], costo_unitario),
                ("precio_venta", detalle["precio_venta"], precio_venta),
            ):
                if valor_anterior == valor_nuevo:
                    continue
                conexion.execute(
                    """
                    INSERT INTO historial_ediciones_compras (
                        compra_id, detalle_compra_id, usuario_id, producto_nombre,
                        campo, valor_anterior, valor_nuevo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        compra_id,
                        detalle["id"],
                        usuario_id,
                        detalle["nombre"],
                        campo,
                        valor_anterior,
                        valor_nuevo,
                    ),
                )

            conexion.execute(
                """
                UPDATE detalle_compras
                SET cantidad = ?, costo_unitario = ?, precio_venta = ?
                WHERE id = ?
                """,
                (cantidad, costo_unitario, precio_venta, detalle["id"]),
            )
            total += cantidad * costo_unitario

        conexion.execute(
            "UPDATE compras SET total = ? WHERE id = ?", (total, compra_id)
        )
        return total


# Este proceso registra la compra y suma las unidades recibidas al inventario.
def registrar_compra(
    usuario_id: int,
    proveedor_id: int,
    productos: list[dict[str, int | str | bool | None]],
) -> tuple[int, int]:
    if not productos:
        raise ValueError("Agrega al menos un producto a la compra.")

    # Se revisan los datos antes de guardar para evitar compras con líneas repetidas o inválidas.
    ids_vistos = set()
    for item in productos:
        producto_id = item.get("producto_id")
        cantidad = item.get("cantidad")
        costo_unitario = item.get("costo_unitario")
        precio_venta = item.get("precio_venta")
        es_nuevo = item.get("nuevo", False)
        if (
            type(es_nuevo) is not bool
            or type(cantidad) is not int
            or type(costo_unitario) is not int
            or cantidad <= 0
            or costo_unitario < 0
            or type(precio_venta) is not int
            or precio_venta < 0
        ):
            raise ValueError("Revisa el producto, la cantidad y los precios.")
        if es_nuevo:
            if (
                producto_id is not None
                or not isinstance(item.get("nombre"), str)
                or not item["nombre"].strip()
                or type(item.get("categoria_id")) is not int
                or item["categoria_id"] <= 0
                or type(item.get("stock_minimo", 2)) is not int
                or item.get("stock_minimo", 2) < 0
                or item.get("codigo_barras") is not None
                and not isinstance(item.get("codigo_barras"), str)
            ):
                raise ValueError("Revisa el nombre, la categoría y el stock mínimo.")
        else:
            if type(producto_id) is not int or producto_id <= 0:
                raise ValueError("Selecciona un producto válido.")
            if producto_id in ids_vistos:
                raise ValueError("Un producto no puede repetirse en la compra.")
            ids_vistos.add(producto_id)

    with _conectar() as conexion:
        # La compra y el aumento de inventario se guardan juntos.
        conexion.execute("BEGIN IMMEDIATE")
        usuario = conexion.execute(
            "SELECT activo FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if not usuario or not usuario["activo"]:
            raise LookupError("El usuario no existe o está inactivo.")
        if not conexion.execute(
            "SELECT 1 FROM proveedores WHERE id = ?", (proveedor_id,)
        ).fetchone():
            raise LookupError("No se encontró el proveedor seleccionado.")

        # Se confirma que los productos existan y se calcula el total antes de guardar.
        lineas = []
        total = 0
        for item in productos:
            cantidad = item["cantidad"]
            costo_unitario = item["costo_unitario"]
            precio_venta = item["precio_venta"]
            if item.get("nuevo", False):
                producto_id, _codigo = _insertar_producto(
                    conexion,
                    item["nombre"],
                    item["categoria_id"],
                    0,
                    costo_unitario,
                    precio_venta,
                    item.get("stock_minimo", 2),
                    item.get("codigo_barras"),
                )
                producto = conexion.execute(
                    "SELECT id, nombre FROM productos WHERE id = ?",
                    (producto_id,),
                ).fetchone()
            else:
                producto = conexion.execute(
                    "SELECT id, nombre FROM productos WHERE id = ?",
                    (item["producto_id"],),
                ).fetchone()
                if not producto:
                    raise LookupError("Uno de los productos ya no está disponible.")
            total += cantidad * costo_unitario
            lineas.append((producto, cantidad, costo_unitario, precio_venta))

        cursor = conexion.execute(
            """
            INSERT INTO compras (usuario_id, proveedor_id, total)
            VALUES (?, ?, ?)
            """,
            (usuario_id, proveedor_id, total),
        )
        compra_id = cursor.lastrowid
        for producto, cantidad, costo_unitario, precio_venta in lineas:
            conexion.execute(
                """
                INSERT INTO detalle_compras (
                    compra_id, producto_id, cantidad, costo_unitario, precio_venta
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    compra_id,
                    producto["id"],
                    cantidad,
                    costo_unitario,
                    precio_venta,
                ),
            )
            # Los nuevos precios se usan en las siguientes ventas, las anteriores quedan igual.
            conexion.execute(
                """
                UPDATE productos
                SET stock = stock + ?, precio_costo = ?, precio_venta = ?
                WHERE id = ?
                """,
                (cantidad, costo_unitario, precio_venta, producto["id"]),
            )
        return compra_id, total


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
