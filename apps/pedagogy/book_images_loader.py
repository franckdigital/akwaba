"""Chargeur des images extraites du livre source (docs/code_route.pdf) : une vraie photo/schéma du
livre par leçon, quand il en existe une à cet endroit précis. Les fichiers sont dans
apps/pedagogy/book_images/ (voir manifest.json), extraits avec leur résolution d'origine telle
qu'imprimée dans le livre.
"""
import json
import os

_DIR = os.path.join(os.path.dirname(__file__), "book_images")
_MANIFEST_PATH = os.path.join(_DIR, "manifest.json")

try:
    with open(_MANIFEST_PATH, encoding="utf-8") as f:
        _MANIFEST = json.load(f)
except FileNotFoundError:
    _MANIFEST = {}


def book_image_for(title):
    """Retourne les octets de la vraie image du livre pour cette leçon, ou None si absente."""
    fname = _MANIFEST.get(title)
    if not fname:
        return None
    path = os.path.join(_DIR, fname)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()
