{
    "name": "MRP Stock Backdate",
    "summary": "Fecha retroactiva de inventario en fabricación",
    "description": """
Usa la Fecha programada al validar fabricaciones de fechas anteriores.
Aplica la fecha a componentes, productos terminados y valoración inicial.
Conserva el registro real de creación y respeta los períodos contables cerrados.
No recalcula costos históricos de operaciones posteriores.
""",
    "version": "15.0.1.0.0",
    "category": "Manufacturing/Manufacturing",
    "author": "Jefferson Silva",
    "website": "https://github.com/jeffrepo/mrp_stock_backdate",
    "license": "LGPL-3",
    "depends": ["mrp_account"],
    "data": ["views/stock_valuation_layer_views.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
