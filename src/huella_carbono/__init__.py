"""
Measuring the carbon footprint of Python algorithms.

Green Software — Universidad Tecnológica Nacional - FRC.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("huella-carbono")
except PackageNotFoundError:  # running without the package installed
    __version__ = "0.0.0"
