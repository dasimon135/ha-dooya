"""Configuration pytest — permet d'importer dooya_protocol directement sans HA."""

import sys
import os

# Ajouter le dossier du composant directement dans le path
# pour les tests unitaires qui n'ont pas besoin de HA
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "custom_components", "dooya"))
