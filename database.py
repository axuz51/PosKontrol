from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Generator
from uuid import uuid4

RUTA_BASE_DATOS = Path(__file__).with_name("poskontrol.db")


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
                    CHECK (metodo_pago IN ('EFECTIVO', 'QR', 'BOLD')),
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
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
            "CREATE INDEX IF NOT EXISTS idx_egresos_fecha "
            "ON egresos_caja_menor (fecha)"
        )


# Revisa que los datos del producto sean válidos antes de guardarlos.
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


# Registra una categoría y devuelve su identificador.
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


# Consulta las categorías ordenadas por nombre.
def listar_categorias() -> list[sqlite3.Row]:
    with _conectar() as conexion:
        return conexion.execute(
            "SELECT id, nombre FROM categorias ORDER BY nombre"
        ).fetchall()


# Registra un producto y le asigna un SKU interno consecutivo.
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


# Busca productos por coincidencia parcial en su código, referencia o nombre.
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


# Actualiza los datos de un producto existente.
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
