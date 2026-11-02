# Compute the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Benchmark orchestration.

For each (experiment, algorithm, n):

  1. Validate that all variants of the experiment give the same result.
  2. Do a probe run that serves as warm-up and sets the batch size.
  3. Repeat R measurements of the batch with CodeCarbon, timing the same work
     the tool is measuring.
  4. Write each repetition to `resultados/simulacion_huella_carbono.csv`, the only
     CSV of the project. The aggregate (mean and standard deviation) is derived in memory.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import time
from typing import Any

import pandas as pd
import psutil

from huella_carbono import config
from huella_carbono.algoritmos import REGISTRO, validar_experimento
from huella_carbono.config import EXPERIMENTOS
from huella_carbono.medidor import MedidorCodeCarbon, calcular_lote


def metadatos_entorno() -> dict[str, Any]:
    """Hardware and software context, so that the experiment is reproducible."""
    import codecarbon
    import numpy

    from huella_carbono import algoritmos

    # The scikit-learn version is read from the installed package metadata instead of
    # importing it: importing sklearn takes ~1.5 s and is unnecessary if the ML experiment did
    # not run in this invocation.
    sklearn_version = importlib.metadata.version("scikit-learn")

    # The model accuracy only exists if the ML experiment ran (its module is loaded
    # lazily, so `MODULO_ML` stays None if it did not run).
    calidad_knn = (
        {str(n): valor for n, valor in sorted(algoritmos.MODULO_ML.CALIDAD.items())}
        if algoritmos.MODULO_ML is not None
        else {}
    )

    # BLAS backend and how many threads it uses: this is what explains why `knn_brute` is
    # multithreaded, and without it the ML experiment would not be reproducible on another machine.
    # `threadpool_info()` only reports libraries already loaded, and this function runs after
    # measuring, so it sees the actual backend of the run.
    try:
        from threadpoolctl import threadpool_info

        hilos_blas = [
            {
                "biblioteca": info.get("internal_api") or info.get("user_api"),
                "version": info.get("version"),
                "hilos": info.get("num_threads"),
            }
            for info in threadpool_info()
        ]
    except Exception:  # noqa: BLE001 - the information is optional, it must never break the run
        hilos_blas = []

    return {
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "plataforma": platform.platform(),
        "procesador": platform.processor(),
        "cpu_nucleos_logicos": psutil.cpu_count(logical=True),
        "cpu_nucleos_fisicos": psutil.cpu_count(logical=False),
        "ram_total_gb": round(psutil.virtual_memory().total / 1024**3, 2),
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "codecarbon": codecarbon.__version__,
        "scikit_learn": sklearn_version,
        "factor_emision_kg_kwh": config.FACTOR_EMISION_AR,
        "factor_emision_anio": config.ANIO_FACTOR_EMISION,
        "factor_emision_fuente": config.FUENTE_FACTOR_EMISION,
        "factor_emision_codecarbon_kg_kwh": config.FACTOR_EMISION_CODECARBON_G_KWH / 1000.0,
        "factor_emision_codecarbon_anio": config.ANIO_FACTOR_EMISION_CODECARBON,
        "pue": config.PUE,
        "repeticiones": config.REPETICIONES,
        "semilla": config.SEMILLA,
        "calidad_knn": calidad_knn,
        "hilos_blas": hilos_blas,
        # BLAS threads: deliberately not pinned, to measure the actual default
        # behavior (it is what makes `knn_brute` multithreaded). Whether the environment
        # limited them is recorded, because it would completely change the ML experiment result.
        "limite_hilos_entorno": {
            var: os.environ[var]
            for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
            if var in os.environ
        },
    }


def ejecutar(
    claves: list[str] | None = None,
    rapido: bool = False,
    repeticiones: int = config.REPETICIONES,
) -> pd.DataFrame:
    """Run the full benchmark and return the DataFrame of raw measurements."""
    claves = claves or list(EXPERIMENTOS)
    config.DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)

    filas: list[dict[str, Any]] = []

    with MedidorCodeCarbon() as codecarbon_medidor:
        # The measurement window is set by the active path: reading power from the
        # hardware requires sampling to fall within the work, estimating it does not.
        lectura = codecarbon_medidor.lectura
        ventana = (
            config.DURACION_MINIMA_LOTE_MUESTREO_S
            if lectura.get("requiere_ventana_muestreo")
            else config.DURACION_MINIMA_LOTE_S
        )
        fuente = lectura.get("fuente_potencia") or "unknown"
        print(
            f"  CPU power: "
            f"{'direct reading' if lectura.get('lectura_directa') else 'estimated'}"
            f" ({fuente})  |  measurement window >= {ventana:.1f} s\n"
        )
        for clave in claves:
            exp = EXPERIMENTOS[clave]
            generar, variantes = REGISTRO[clave]
            tamanios = exp.tamanios_rapido if rapido else exp.tamanios_completo

            print(f"=== {exp.titulo} ===")
            for n in tamanios:
                validar_experimento(clave, n)
                entrada = generar(n)

                for nombre, funcion in variantes.items():
                    lote = calcular_lote(funcion, entrada, ventana)

                    for rep in range(1, repeticiones + 1):
                        cc = codecarbon_medidor.medir(
                            f"{clave}_{nombre}_n{n}_r{rep}", funcion, entrada, lote=lote
                        )
                        filas.append(
                            {
                                "experimento": clave,
                                "algoritmo": nombre,
                                "complejidad": exp.variantes[nombre],
                                "n": n,
                                "repeticion": rep,
                                "ejecuciones_lote": lote,
                                "tiempo_s": cc["tiempo_s"],
                                "tiempo_s_informado": cc["tiempo_s_informado"],
                                "energia_kwh": cc["energia_kwh"],
                                "co2_kg": cc["co2_kg"],
                                "co2_kg_nativo": cc["co2_kg_nativo"],
                                "potencia_cpu_w": cc["potencia_cpu_w"],
                            }
                        )

                    ult = filas[-1]
                    print(
                        f"  n={n:<6} {nombre:<16} {exp.variantes[nombre]:<16} "
                        f"batch={lote:<6} t={ult['tiempo_s']:.3e}s  "
                        f"CO2={ult['co2_kg']:.3e} kg"
                    )
            print()

        metadatos = metadatos_entorno()
        metadatos["codecarbon_deteccion"] = codecarbon_medidor.metadatos
        # The effective window depends on the power source that ended up active, so it is
        # recorded: the report states it instead of assuming the default value.
        metadatos["ventana_medicion_s"] = ventana

    df = pd.DataFrame(filas)
    df.to_csv(config.CSV_SIMULACION, index=False)
    (config.DIR_RESULTADOS / "metadatos.json").write_text(
        json.dumps(metadatos, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Results  -> {config.CSV_SIMULACION.relative_to(config.RAIZ)}")
    print(f"Metadata -> resultados/metadatos.json")
    return df


def agregar(df: pd.DataFrame) -> pd.DataFrame:
    """Mean and standard deviation of the R repetitions of each (algorithm, n)."""
    columnas = [
        "tiempo_s",
        "tiempo_s_informado",
        "energia_kwh",
        "co2_kg",
        "co2_kg_nativo",
        "potencia_cpu_w",
    ]
    agrupado = df.groupby(["experimento", "algoritmo", "complejidad", "n"], as_index=False).agg(
        {**{c: ["mean", "std"] for c in columnas}, "ejecuciones_lote": "first"}
    )
    agrupado.columns = [
        col[0] if col[1] in ("", "first") else f"{col[0]}_{col[1]}" for col in agrupado.columns
    ]
    return agrupado.sort_values(["experimento", "n", "algoritmo"]).reset_index(drop=True)


def cargar_resultados() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Reload from disk what `ejecutar()` produced."""
    if not config.CSV_SIMULACION.exists():
        raise FileNotFoundError(
            f"{config.CSV_SIMULACION} does not exist. Run the benchmark first."
        )
    df = pd.read_csv(config.CSV_SIMULACION)
    resumen = agregar(df)
    metadatos = json.loads((config.DIR_RESULTADOS / "metadatos.json").read_text(encoding="utf-8"))
    return df, resumen, metadatos
