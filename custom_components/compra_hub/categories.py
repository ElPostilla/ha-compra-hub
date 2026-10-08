"""Pasillo de un producto por su nombre, igual que la app de la compra.

Copia de `lista-compra/build/src/app/categories.ts` del hub: mismas claves,
mismo orden (el recorrido típico del súper) y mismas palabras. La app la
calcula al añadir un producto y la manda al hub; desde Home Assistant hay que
hacer lo mismo o todo acabaría en «Otros».
"""

from __future__ import annotations

import unicodedata

# (clave, palabras). La primera categoría que contiene alguna palabra gana.
CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fruver", ("manzana", "platano", "plátano", "naranja", "pera", "uva", "fresa", "tomate", "lechuga",
                "cebolla", "ajo", "patata", "papa", "zanahoria", "pepino", "pimiento", "aguacate", "limon",
                "limón", "kiwi", "melon", "melón", "sandia", "sandía", "brocoli", "brócoli", "espinaca",
                "calabacin", "calabacín", "champiñon", "champiñón", "seta", "fruta", "verdura", "ensalada")),
    ("pan", ("pan", "baguette", "barra de pan", "bolleria", "bollería", "croissant", "magdalena", "tostada")),
    ("lacteos", ("leche", "yogur", "yogurt", "queso", "mantequilla", "nata", "huevo", "huevos", "margarina",
                 "requeson", "requesón", "cuajada")),
    ("carne", ("pollo", "carne", "ternera", "cerdo", "jamon", "jamón", "chorizo", "salchicha", "pescado",
               "salmon", "salmón", "atun", "atún", "merluza", "gamba", "langostino", "bacon", "panceta",
               "filete", "lomo", "marisco")),
    ("despensa", ("arroz", "pasta", "macarrones", "espagueti", "harina", "azucar", "azúcar", "sal", "aceite",
                  "vinagre", "legumbre", "lenteja", "garbanzo", "alubia", "conserva", "salsa", "especia",
                  "cafe", "café", " te ", "té", "cereales", "galleta", "miel", "chocolate")),
    ("congelados", ("congelado", "helado", "pizza")),
    ("bebidas", ("agua", "vino", "cerveza", "zumo", "refresco", "cola", "bebida", "licor")),
    ("limpieza", ("detergente", "lejia", "lejía", "suavizante", "friegasuelos", "papel higienico",
                  "papel higiénico", "servilleta", "bolsa de basura", "estropajo", "fregona", "limpiador")),
    ("higiene", ("champu", "champú", "gel de ducha", "jabon", "jabón", "pasta de dientes", "dentifrico",
                 "dentífrico", "desodorante", "compresa", "tampon", "tampón", "cuchilla", "maquinilla")),
)
OTHER = "otros"


def _normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def detect_category(name: str) -> str:
    """Clave del pasillo («fruver», «lacteos»…) o «otros»."""
    n = _normalize(name)
    for key, words in CATEGORIES:
        if any(_normalize(w) in n for w in words):
            return key
    return OTHER
