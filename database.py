import sqlite3
from pathlib import Path

RUTA_BASE_DATOS = Path(__file__).with_name("poskontrol.db")

# Crea las tablas del sistema.
def inicializar_base_datos():
    conexion = sqlite3.connect(RUTA_BASE_DATOS)
    try:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.execute("BEGIN")
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
                FOREIGN KEY (categoria_id) REFERENCES categorias (id)
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
            "CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas (fecha)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_egresos_fecha "
            "ON egresos_caja_menor (fecha)"
        )
        conexion.commit()
    finally:
        conexion.close()
