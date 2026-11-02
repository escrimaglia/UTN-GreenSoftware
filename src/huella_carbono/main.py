# Compute the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Command-line interface.

    uv run huella-carbono --quick        # pipeline validation (< 1 min)
    uv run huella-carbono --full         # final project run
    uv run huella-carbono --only ordenamiento
    uv run huella-carbono --report-only  # regenerate charts and report without measuring again
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
        description="Measures the carbon footprint of Python algorithms and generates the report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--quick",
        action="store_true",
        help="short run with reduced sizes, to validate the pipeline",
    )
    modo.add_argument(
        "--full",
        action="store_true",
        help="final run with all sizes (default)",
    )
    modo.add_argument(
        "--report-only",
        action="store_true",
        help="regenerate charts and report from the existing CSV",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=list(config.EXPERIMENTOS),
        metavar="EXPERIMENT",
        help=f"restrict the run to these experiments: {', '.join(config.EXPERIMENTOS)}",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=config.REPETICIONES,
        help=f"repetitions per measurement point (default {config.REPETICIONES})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parsear_argumentos(argv)

    print("=" * 78)
    print("  CARBON FOOTPRINT OF PYTHON ALGORITHMS")
    print("  Green Software — Universidad Tecnológica Nacional - FRC")
    print("=" * 78)
    print()

    if args.report_only:
        _, resumen, metadatos = cargar_resultados()
        print("Regenerating charts and report from the existing results...")
    else:
        inicio = time.perf_counter()
        ejecutar(
            claves=args.only,
            rapido=args.quick,
            repeticiones=args.repetitions,
        )
        print(f"Benchmark completed in {time.perf_counter() - inicio:.1f} s\n")
        _, resumen, metadatos = cargar_resultados()

    rutas = generar_todos(resumen)
    for nombre, ruta in rutas.items():
        print(f"  chart [{nombre}] -> {ruta}")
    print()

    generar(resumen, metadatos, rutas)
    print(f"Benchmark report -> {config.INFORME.relative_to(config.RAIZ)}")
    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
