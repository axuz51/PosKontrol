from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

import database


# Estas pruebas usan una base aparte para no tocar los datos reales del proyecto.
class PruebasCompras(unittest.TestCase):
    def setUp(self) -> None:
        self.directorio = tempfile.TemporaryDirectory()
        self.ruta_anterior = database.RUTA_BASE_DATOS
        database.RUTA_BASE_DATOS = Path(self.directorio.name) / "prueba.db"
        database.inicializar_base_datos()
        self.administrador_id = database.crear_administrador_inicial(
            "Admin de prueba", "admin", "clave-segura-123"
        )
        self.proveedor_id = database.agregar_proveedor(
            "Proveedor de prueba", "3001234567"
        )
        categoria_id = database.agregar_categoria("Accesorios")
        database.agregar_producto(
            "Estuche", categoria_id, 5, 4000, 10000, 2
        )
        self.producto = database.listar_productos()[0]

    def tearDown(self) -> None:
        database.RUTA_BASE_DATOS = self.ruta_anterior
        self.directorio.cleanup()

    # La compra debe guardar el total y sumar las unidades recibidas al inventario.
    def test_compra_actualiza_existencias_y_costo(self) -> None:
        compra_id, total = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 3,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )

        producto_actual = database.listar_productos()[0]
        compras = database.listar_compras()
        self.assertGreater(compra_id, 0)
        self.assertEqual(total, 13500)
        self.assertEqual(producto_actual["stock"], 8)
        self.assertEqual(producto_actual["precio_costo"], 4500)
        self.assertEqual(producto_actual["precio_venta"], 11000)
        self.assertEqual(compras[0]["proveedor"], "Proveedor de prueba")

    def test_detalle_compra_muestra_productos_y_usuario(self) -> None:
        compra_id, _ = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 3,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )

        compra, productos = database.obtener_detalle_compra(compra_id)
        compra_inexistente, productos_inexistentes = (
            database.obtener_detalle_compra(compra_id + 100)
        )

        self.assertEqual(compra["usuario"], "Admin de prueba")
        self.assertEqual(compra["proveedor"], "Proveedor de prueba")
        self.assertEqual(compra["total"], 13500)
        self.assertEqual(productos[0]["nombre"], "Estuche")
        self.assertEqual(productos[0]["cantidad"], 3)
        self.assertEqual(productos[0]["costo_unitario"], 4500)
        self.assertEqual(productos[0]["subtotal"], 13500)
        self.assertIsNone(compra_inexistente)
        self.assertEqual(productos_inexistentes, [])

    def test_editar_compra_corrige_stock_precios_y_deja_historial(self) -> None:
        compra_id, _ = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 3,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )
        database.registrar_venta(
            self.administrador_id,
            [{"producto_id": self.producto["id"], "cantidad": 1, "descuento": 0}],
            {"EFECTIVO": 11000},
        )
        _, detalles = database.obtener_detalle_compra(compra_id)

        total = database.editar_compra(
            compra_id,
            self.administrador_id,
            [
                {
                    "detalle_id": detalles[0]["detalle_id"],
                    "cantidad": 4,
                    "costo_unitario": 5000,
                    "precio_venta": 12000,
                }
            ],
        )

        compra, detalles = database.obtener_detalle_compra(compra_id)
        producto = database.listar_productos()[0]
        historial = database.listar_ediciones_compra(compra_id)
        with database._conectar() as conexion:
            venta = conexion.execute(
                """
                SELECT precio_unitario, costo_unitario
                FROM detalle_ventas
                """
            ).fetchone()

        self.assertEqual(total, 20000)
        self.assertEqual(compra["total"], 20000)
        self.assertEqual(detalles[0]["cantidad"], 4)
        self.assertEqual(detalles[0]["costo_unitario"], 5000)
        self.assertEqual(detalles[0]["precio_venta"], 12000)
        self.assertEqual(producto["stock"], 8)
        self.assertEqual(producto["precio_costo"], 5000)
        self.assertEqual(producto["precio_venta"], 12000)
        self.assertEqual((venta["precio_unitario"], venta["costo_unitario"]), (11000, 4500))
        self.assertEqual(len(historial), 3)
        self.assertEqual(
            {edicion["campo"] for edicion in historial},
            {"cantidad", "costo_unitario", "precio_venta"},
        )
        self.assertTrue(all(edicion["usuario"] == "Admin de prueba" for edicion in historial))

    def test_migracion_conserva_compras_anteriores_sin_precio_venta_guardado(self) -> None:
        compra_id, _ = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 2,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )
        with closing(sqlite3.connect(database.RUTA_BASE_DATOS)) as conexion:
            conexion.execute("PRAGMA foreign_keys = OFF")
            conexion.execute("DROP TABLE historial_ediciones_compras")
            conexion.execute(
                "ALTER TABLE detalle_compras RENAME TO detalle_compras_anterior"
            )
            conexion.execute(
                """
                CREATE TABLE detalle_compras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    compra_id INTEGER NOT NULL,
                    producto_id INTEGER NOT NULL,
                    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
                    costo_unitario INTEGER NOT NULL CHECK (costo_unitario >= 0),
                    FOREIGN KEY (compra_id) REFERENCES compras (id),
                    FOREIGN KEY (producto_id) REFERENCES productos (id)
                )
                """
            )
            conexion.execute(
                """
                INSERT INTO detalle_compras (
                    id, compra_id, producto_id, cantidad, costo_unitario
                )
                SELECT id, compra_id, producto_id, cantidad, costo_unitario
                FROM detalle_compras_anterior
                """
            )
            conexion.execute("DROP TABLE detalle_compras_anterior")
            conexion.commit()

        database.inicializar_base_datos()
        compra, detalles = database.obtener_detalle_compra(compra_id)

        self.assertEqual(compra["total"], 9000)
        self.assertEqual(detalles[0]["cantidad"], 2)
        self.assertIsNone(detalles[0]["precio_venta"])

    def test_corregir_compra_no_deja_el_stock_negativo(self) -> None:
        compra_id, _ = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 3,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )
        database.registrar_venta(
            self.administrador_id,
            [{"producto_id": self.producto["id"], "cantidad": 8, "descuento": 0}],
            {"EFECTIVO": 88000},
        )
        _, detalles = database.obtener_detalle_compra(compra_id)

        with self.assertRaisesRegex(ValueError, "stock quedaría negativo"):
            database.editar_compra(
                compra_id,
                self.administrador_id,
                [
                    {
                        "detalle_id": detalles[0]["detalle_id"],
                        "cantidad": 2,
                        "costo_unitario": 4500,
                        "precio_venta": 11000,
                    }
                ],
            )

        compra, detalles = database.obtener_detalle_compra(compra_id)
        self.assertEqual(database.listar_productos()[0]["stock"], 0)
        self.assertEqual(compra["total"], 13500)
        self.assertEqual(detalles[0]["cantidad"], 3)
        self.assertEqual(database.listar_ediciones_compra(compra_id), [])

    def test_corregir_compra_anterior_no_cambia_precios_mas_recientes(self) -> None:
        compra_anterior_id, _ = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 2,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )
        database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 1,
                    "costo_unitario": 5000,
                    "precio_venta": 13000,
                }
            ],
        )
        _, detalles = database.obtener_detalle_compra(compra_anterior_id)

        database.editar_compra(
            compra_anterior_id,
            self.administrador_id,
            [
                {
                    "detalle_id": detalles[0]["detalle_id"],
                    "cantidad": 2,
                    "costo_unitario": 6000,
                    "precio_venta": 12000,
                }
            ],
        )

        producto = database.listar_productos()[0]
        self.assertEqual(producto["precio_costo"], 5000)
        self.assertEqual(producto["precio_venta"], 13000)

    def test_solo_administrador_puede_corregir_compra(self) -> None:
        compra_id, _ = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 2,
                    "costo_unitario": 4500,
                    "precio_venta": 11000,
                }
            ],
        )
        vendedor_id = database.crear_cajero(
            self.administrador_id, "Cajero de prueba", "cajero", "clave-segura-123"
        )
        _, detalles = database.obtener_detalle_compra(compra_id)

        with self.assertRaisesRegex(PermissionError, "Solo el administrador"):
            database.editar_compra(
                compra_id,
                vendedor_id,
                [
                    {
                        "detalle_id": detalles[0]["detalle_id"],
                        "cantidad": 3,
                        "costo_unitario": 4500,
                        "precio_venta": 11000,
                    }
                ],
            )

        self.assertEqual(database.listar_productos()[0]["stock"], 7)

    # Cada venta guarda el costo que tenía el producto cuando se registró esa venta.
    def test_actualizar_costo_no_cambia_ventas_anteriores(self) -> None:
        venta_anterior_id, _ = database.registrar_venta(
            self.administrador_id,
            [{"producto_id": self.producto["id"], "cantidad": 1, "descuento": 0}],
            {"EFECTIVO": 10000},
        )
        database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "producto_id": self.producto["id"],
                    "cantidad": 2,
                    "costo_unitario": 6000,
                    "precio_venta": 12000,
                }
            ],
        )
        venta_nueva_id, _ = database.registrar_venta(
            self.administrador_id,
            [{"producto_id": self.producto["id"], "cantidad": 1, "descuento": 0}],
            {"EFECTIVO": 12000},
        )

        with database._conectar() as conexion:
            detalles = conexion.execute(
                """
                SELECT venta_id, costo_unitario, precio_unitario
                FROM detalle_ventas
                WHERE venta_id IN (?, ?)
                ORDER BY venta_id
                """,
                (venta_anterior_id, venta_nueva_id),
            ).fetchall()

        self.assertEqual(
            [
                (
                    fila["venta_id"],
                    fila["costo_unitario"],
                    fila["precio_unitario"],
                )
                for fila in detalles
            ],
            [
                (venta_anterior_id, 4000, 10000),
                (venta_nueva_id, 6000, 12000),
            ],
        )

    # Un producto nuevo solo entra al inventario cuando se confirma la compra.
    def test_compra_crea_producto_nuevo_con_sus_datos(self) -> None:
        categoria_id = database.agregar_categoria("Cargadores")
        compra_id, total = database.registrar_compra(
            self.administrador_id,
            self.proveedor_id,
            [
                {
                    "nuevo": True,
                    "nombre": "Cargador USB-C",
                    "categoria_id": categoria_id,
                    "cantidad": 4,
                    "costo_unitario": 7000,
                    "precio_venta": 15000,
                    "stock_minimo": 3,
                    "codigo_barras": "123456789",
                }
            ],
        )

        productos = database.listar_productos("Cargador USB-C")
        self.assertEqual(total, 28000)
        self.assertEqual(len(productos), 1)
        self.assertEqual(productos[0]["codigo"], "SKU-000002")
        self.assertEqual(productos[0]["stock"], 4)
        self.assertEqual(productos[0]["precio_costo"], 7000)
        self.assertEqual(productos[0]["precio_venta"], 15000)
        self.assertEqual(productos[0]["stock_minimo"], 3)
        self.assertEqual(productos[0]["codigo_barras"], "123456789")
        self.assertEqual(database.listar_compras()[0]["id"], compra_id)

    # Si la cantidad o el costo no sirven, no se debe crear la compra ni mover el stock.
    def test_no_guarda_compra_con_cantidad_invalida(self) -> None:
        with self.assertRaisesRegex(ValueError, "cantidad"):
            database.registrar_compra(
                self.administrador_id,
                self.proveedor_id,
                [
                    {
                        "producto_id": self.producto["id"],
                        "cantidad": 0,
                        "costo_unitario": 4500,
                        "precio_venta": 10000,
                    }
                ],
            )

        self.assertEqual(database.listar_productos()[0]["stock"], 5)
        with database._conectar() as conexion:
            total_compras = conexion.execute(
                "SELECT COUNT(*) FROM compras"
            ).fetchone()[0]
        self.assertEqual(total_compras, 0)

    # No se permite repetir un producto porque cada producto debe tener una sola línea.
    def test_no_permite_producto_repetido_en_compra(self) -> None:
        linea = {
            "producto_id": self.producto["id"],
            "cantidad": 1,
            "costo_unitario": 4500,
            "precio_venta": 10000,
        }
        with self.assertRaisesRegex(ValueError, "repetirse"):
            database.registrar_compra(
                self.administrador_id,
                self.proveedor_id,
                [linea, linea.copy()],
            )

    # Si falla una compra con producto nuevo, tampoco debe quedar ese producto suelto.
    def test_compra_invalida_no_deja_producto_nuevo_en_inventario(self) -> None:
        with self.assertRaisesRegex(ValueError, "cantidad"):
            database.registrar_compra(
                self.administrador_id,
                self.proveedor_id,
                [
                    {
                        "nuevo": True,
                        "nombre": "Producto incompleto",
                        "categoria_id": self.producto["categoria_id"],
                        "cantidad": 0,
                        "costo_unitario": 5000,
                        "precio_venta": 9000,
                    }
                ],
            )

        self.assertEqual(database.listar_productos(), [self.producto])
        self.assertEqual(database.listar_productos(), [self.producto])
    # La búsqueda de compras muestra un número limitado aunque haya muchos productos.
    def test_busqueda_de_productos_puede_limitar_resultados(self) -> None:
        for numero in range(25):
            database.agregar_producto(
                f"Producto {numero}",
                self.producto["categoria_id"],
                1,
                1000,
                2000,
            )

        encontrados = database.listar_productos(limite=10)

        self.assertEqual(len(encontrados), 10)
