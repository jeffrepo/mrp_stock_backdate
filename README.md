# MRP Stock Backdate — Odoo 15

Al **Marcar como hecha** una orden de fabricación cuya **Fecha programada** sea
anterior al momento de validación, registra el inventario con esa fecha y hora.
Funciona aunque la orden se valide un mes o un año después.

Ejemplo: una orden con Fecha programada **15/08/2025 10:00**, validada hoy,
registra la salida de sus componentes y la entrada del producto terminado el
**15/08/2025 10:00**. No hace falta un botón adicional.

## Instalación

1. Colocar este repositorio en una carpeta llamada `mrp_stock_backdate`, dentro
   de una ruta de módulos de Odoo 15 (`addons_path`). El módulo está en la raíz
   del repositorio.
2. Reiniciar Odoo y actualizar la lista de aplicaciones.
3. Quitar el filtro «Aplicaciones» y buscar **MRP Stock Backdate**.
4. Instalar el módulo. Depende de `mrp_account`, que integra fabricación,
   inventario y contabilidad.

## Uso

1. Crear o abrir una fabricación pendiente.
2. Establecer su **Fecha programada** (`date_planned_start`). Esta es la fecha
   efectiva; no se utiliza la fecha de creación ni la fecha límite.
3. Confirmar, registrar las cantidades y **Marcar como hecha**.
4. Consultar los movimientos de inventario y sus operaciones detalladas.

Confirmar la orden solamente prepara/reserva los movimientos, como en Odoo
estándar. La salida efectiva ocurre cuando se registra la producción.
Si se replanifican operaciones antes de terminar, comprobar la Fecha programada:
el módulo utiliza el valor que tenga la orden al registrar su inventario.

## Fechas que se aplican

- Salida de componentes, entrada de productos terminados y subproductos.
- Operaciones detalladas, incluidos sus lotes y números de serie.
- Capas iniciales de valoración y el informe estándar de valoración a una fecha.
- Asientos de valoración automática y líneas analíticas del consumo.
- Cada fabricación mantiene su propia fecha en las validaciones por lotes.
- Las órdenes pendientes generadas por una fabricación parcial conservan la
  Fecha programada original; puede cambiarse antes de validar el pendiente.

La fecha de finalización de la fabricación y sus datos de creación/modificación
siguen reflejando el procesamiento real. Las capas retroactivas muestran además
**Registrado realmente el** (`mrp_recorded_at`); esta columna se puede activar en
la lista de valoración y aparece en el formulario.

Odoo 15 filtra la valoración histórica por `stock.valuation.layer.create_date`.
Por ello el módulo ajusta esa columna únicamente en las capas iniciales que acaba
de crear y conserva su valor original en `mrp_recorded_at`. No modifica capas
anteriores ni revaloraciones posteriores de cantidad cero.

## Alcance

- Actúa sobre nuevas validaciones, incluidas órdenes pendientes que ya existían
  al instalarlo. No cambia fabricaciones finalizadas anteriormente.
- Las fechas futuras siguen el comportamiento estándar: inventario al validar.
- No cambia entregas, recepciones, transferencias, desechos ni desmontajes.
- Conserva la hora de los movimientos en UTC y utiliza el día de la zona horaria
  del usuario que valida para los asientos y las líneas analíticas.
- Con valoración automática, impide registrar en fechas anteriores o iguales
  al cierre de período o ejercicio de la compañía, también para administradores.
  No abre períodos ni desplaza silenciosamente el asiento a otra fecha.
- **No reconstruye el inventario disponible ni recalcula los costos FIFO/AVCO
  de operaciones posteriores.** Odoo calcula cantidades disponibles y costos al
  procesar la operación. Para registrar un historial completo, introducir las
  operaciones en orden cronológico y revisar las existencias y costos de origen.
- No cambia fechas de transferencias auxiliares de rutas de fabricación de
  varios pasos, tiempos de trabajo ni costos analíticos propios del centro de
  trabajo. No incluye una migración del historial existente.

## Pruebas

El repositorio incluye pruebas de integración con Odoo 15 y PostgreSQL en
GitHub Actions. También se pueden ejecutar sobre una base de pruebas:

```sh
odoo -d mrp_backdate_test -i mrp_stock_backdate \
  --test-enable --test-tags /mrp_stock_backdate \
  --stop-after-init --without-demo=all
```

Licencia: LGPL-3.0.
