# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Interfaz de línea de comandos.

    uv run huella-carbono --rapido      # validación del pipeline (< 1 min)
    uv run huella-carbono --completo    # corrida final del proyecto
    uv run huella-carbono --solo ordenamiento
    uv run huella-carbono --solo-informe  # regenera gráficos e informe sin volver a medir
"""

from __future__ import annotations

import argparse
import sys
import time

from huella_carbono import config
from huella_carbono.benchmark import cargar_resultados, ejecutar
from huella_carbono.graficos import generar_todos
from huella_carbono.informe import generar


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="huella-carbono",
        description="Mide la huella de carbono de algoritmos en Python y genera el reporte.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--rapido",
        action="store_true",
        help="corrida corta con tamaños reducidos, para validar el pipeline",
    )
    modo.add_argument(
        "--completo",
        action="store_true",
        help="corrida final con todos los tamaños (por defecto)",
    )
    modo.add_argument(
        "--solo-informe",
        action="store_true",
        help="regenera gráficos e informe a partir de los CSV ya existentes",
    )
    parser.add_argument(
        "--solo",
        nargs="+",
        choices=list(config.EXPERIMENTOS),
        metavar="EXPERIMENTO",
        help=f"limita la corrida a estos experimentos: {', '.join(config.EXPERIMENTOS)}",
    )
    parser.add_argument(
        "--repeticiones",
        type=int,
        default=config.REPETICIONES,
        help=f"repeticiones por punto de medición (por defecto {config.REPETICIONES})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parsear_argumentos(argv)

    print("=" * 78)
    print("  HUELLA DE CARBONO DE ALGORITMOS EN PYTHON")
    print("  Green Software — Universidad Tecnológica Nacional - FRC")
    print("=" * 78)
    print()

    if args.solo_informe:
        _, resumen, metadatos = cargar_resultados()
        print("Regenerando gráficos e informe desde los resultados existentes...")
    else:
        inicio = time.perf_counter()
        ejecutar(
            claves=args.solo,
            rapido=args.rapido,
            repeticiones=args.repeticiones,
        )
        print(f"Benchmark completado en {time.perf_counter() - inicio:.1f} s\n")
        _, resumen, metadatos = cargar_resultados()

    rutas = generar_todos(resumen)
    for nombre, ruta in rutas.items():
        print(f"  gráfico [{nombre}] -> {ruta}")
    print()

    generar(resumen, metadatos, rutas)
    print(f"Reporte del benchmark -> {config.INFORME.relative_to(config.RAIZ)}")
    print()
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
