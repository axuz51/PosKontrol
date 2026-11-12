import tempfile
import unittest
from pathlib import Path

import database


class PruebasPuntoVenta(unittest.TestCase):
    def setUp(self) -> None:
        # Cada prueba usa una base temporal para no modificar los datos del proyecto.
        self.directorio = tempfile.TemporaryDirectory()
        self.ruta_anterior = database.RUTA_BASE_DATOS
        database.RUTA_BASE_DATOS = Path(self.directorio.name) / "prueba.db"
        database.inicializar_base_datos()
        self.administrador_id = database.crear_administrador_inicial(
            "Admin de prueba", "admin", "clave-segura-123"
        )
        self.categoria_id = database.agregar_categoria("Accesorios")
        database.agregar_producto(
            "Estuche", self.categoria_id, 5, 4000, 10000, 2
        )
        database.agregar_producto(
            "Pila", self.categoria_id, 4, 2000, 10000, 2
        )
        self.productos = database.listar_productos()

    def tearDown(self) -> None:
        database.RUTA_BASE_DATOS = self.ruta_anterior
        self.directorio.cleanup()

    def test_descuento_por_linea_y_actualizacion_de_stock(self) -> None:
        estuche, pila = self.productos
        venta_id, total = database.registrar_venta(
            self.administrador_id,
            [
                {"producto_id": estuche["id"], "cantidad": 3, "descuento": 2000},
                {"producto_id": pila["id"], "cantidad": 1, "descuento": 1000},
            ],
            {"EFECTIVO": 37000},
        )

        self.assertGreater(venta_id, 0)
        self.assertEqual(total, 37000)
        actuales = {
            producto["nombre"]: producto["stock"]
            for producto in database.listar_productos()
        }
        self.assertEqual(actuales, {"Estuche": 2, "Pila": 3})

    def test_no_guarda_venta_si_no_hay_stock_suficiente(self) -> None:
        estuche = self.productos[0]
        with self.assertRaisesRegex(ValueError, "existencias suficientes"):
            database.registrar_venta(
                self.administrador_id,
                [{"producto_id": estuche["id"], "cantidad": 6, "descuento": 0}],
                {"QR": 60000},
            )

        with database._conectar() as conexion:
            ventas = conexion.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]
        self.assertEqual(ventas, 0)
        self.assertEqual(database.listar_productos()[0]["stock"], 5)

    def test_crea_cajero_y_rechaza_clave_incorrecta(self) -> None:
        cajero_id = database.crear_cajero(
            self.administrador_id, "Cajero", "CAJERO", "clave-cajero-123"
        )

        usuario = database.autenticar_usuario("cajero", "clave-cajero-123")
        self.assertIsNotNone(usuario)
        self.assertEqual(usuario["id"], cajero_id)
        self.assertIsNone(database.autenticar_usuario("cajero", "incorrecta"))

    def test_no_permite_un_descuento_mayor_al_valor_de_la_linea(self) -> None:
        estuche = self.productos[0]
        with self.assertRaisesRegex(ValueError, "supera el valor"):
            database.registrar_venta(
                self.administrador_id,
                [{"producto_id": estuche["id"], "cantidad": 1, "descuento": 10001}],
                {"BOLD": 0},
            )

    def test_registra_una_venta_con_tres_metodos(self) -> None:
        estuche = self.productos[0]
        venta_id, total = database.registrar_venta(
            self.administrador_id,
            [{"producto_id": estuche["id"], "cantidad": 2, "descuento": 1000}],
            {"EFECTIVO": 5000, "QR": 7000, "BOLD": 7000},
        )

        self.assertEqual(total, 19000)
        with database._conectar() as conexion:
            venta = conexion.execute(
                "SELECT metodo_pago FROM ventas WHERE id = ?", (venta_id,)
            ).fetchone()
            pagos = conexion.execute(
                """
                SELECT metodo_pago, monto
                FROM pagos_venta
                WHERE venta_id = ?
                ORDER BY metodo_pago
                """,
                (venta_id,),
            ).fetchall()
        self.assertEqual(venta["metodo_pago"], "MIXTO")
        self.assertEqual(
            [(pago["metodo_pago"], pago["monto"]) for pago in pagos],
            [("BOLD", 7000), ("EFECTIVO", 5000), ("QR", 7000)],
        )

    def test_no_registra_si_los_pagos_no_suman_el_total(self) -> None:
        estuche = self.productos[0]
        with self.assertRaisesRegex(ValueError, "igual al total"):
            database.registrar_venta(
                self.administrador_id,
                [{"producto_id": estuche["id"], "cantidad": 1, "descuento": 0}],
                {"EFECTIVO": 5000, "QR": 4000},
            )

    def test_migra_ventas_existentes_y_conserva_su_pago(self) -> None:
        estuche = self.productos[0]
        with database._conectar() as conexion:
            # Se recrea el esquema anterior para probar la migración de ventas guardadas.
            conexion.execute("PRAGMA foreign_keys = OFF")
            conexion.execute("BEGIN IMMEDIATE")
            conexion.execute("DROP TABLE pagos_venta")
            conexion.execute("ALTER TABLE detalle_ventas RENAME TO detalle_ventas_nueva")
            conexion.execute("ALTER TABLE ventas RENAME TO ventas_nueva")
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
                        CHECK (metodo_pago IN ('EFECTIVO', 'QR', 'BOLD')),
                    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
                )
                """
            )
            conexion.execute(
                """
                INSERT INTO ventas
                SELECT id, usuario_id, fecha, subtotal, descuento, total, metodo_pago
                FROM ventas_nueva
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
                INSERT INTO detalle_ventas
                SELECT id, venta_id, producto_id, cantidad, precio_unitario,
                       costo_unitario, descuento
                FROM detalle_ventas_nueva
                """
            )
            conexion.execute("DROP TABLE detalle_ventas_nueva")
            conexion.execute("DROP TABLE ventas_nueva")
            conexion.execute(
                """
                INSERT INTO ventas (
                    usuario_id, subtotal, descuento, total, metodo_pago
                )
                VALUES (?, 10000, 0, 10000, 'EFECTIVO')
                """,
                (self.administrador_id,),
            )

        database.inicializar_base_datos()

        with database._conectar() as conexion:
            pagos = conexion.execute(
                """
                SELECT metodo_pago, monto
                FROM pagos_venta
                WHERE venta_id = 1
                """
            ).fetchone()
        self.assertEqual(pagos["metodo_pago"], "EFECTIVO")
        self.assertEqual(pagos["monto"], 10000)
        self.assertGreater(estuche["id"], 0)


if __name__ == "__main__":
    unittest.main()
