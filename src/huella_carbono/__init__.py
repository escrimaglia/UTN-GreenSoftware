"""
Medición de la huella de carbono de algoritmos en Python.

Green Software — Universidad Tecnológica Nacional - FRC.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("huella-carbono")
except PackageNotFoundError:  # ejecutado sin instalar el paquete
    __version__ = "0.0.0"
