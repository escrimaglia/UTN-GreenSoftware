# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Orquestación del benchmark.

Para cada (experimento, algoritmo, n):

  1. Se valida que todas las variantes del experimento den el mismo resultado.
  2. Se hace una corrida de sondeo que sirve de warm-up y fija el tamaño del lote.
  3. Se repiten R mediciones del lote con el medidor propio y R con CodeCarbon,
     sobre exactamente el mismo trabajo.
  4. Se vuelca cada repetición a `resultados/simulacion_huella_carbono.csv`, el único
     CSV del proyecto. El agregado (media y desvío estándar) se deriva en memoria.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import time
from dataclasses import asdict
from typing import Any

import pandas as pd
import psutil

from huella_carbono import config
from huella_carbono.algoritmos import REGISTRO, validar_experimento
from huella_carbono.config import EXPERIMENTOS
from huella_carbono.medidor import MedidorCodeCarbon, MedidorPropio


def metadatos_entorno() -> dict[str, Any]:
    """Contexto de hardware y software, para que el experimento sea reproducible."""
    import codecarbon
    import numpy

    from huella_carbono import algoritmos

    # La versión de scikit-learn se lee de los metadatos del paquete instalado en lugar de
    # importarlo: importar sklearn cuesta ~1,5 s y no hace falta si el experimento de ML no
    # corrió en esta invocación.
    sklearn_version = importlib.metadata.version("scikit-learn")

    # La accuracy del modelo sólo existe si el experimento de ML se ejecutó (la carga de su
    # módulo es perezosa, así que `MODULO_ML` sigue en None si no corrió).
    calidad_knn = (
        {str(n): valor for n, valor in sorted(algoritmos.MODULO_ML.CALIDAD.items())}
        if algoritmos.MODULO_ML is not None
        else {}
    )

    # Backend de BLAS y cuántos hilos usa: es el dato que explica por qué `knn_brute` es
    # multihilo, y sin él el experimento de ML no sería reproducible en otra máquina.
    # `threadpool_info()` sólo informa bibliotecas ya cargadas, y esta función corre después
    # de medir, así que ve el backend real de la corrida.
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
    except Exception:  # noqa: BLE001 - la información es opcional, nunca debe romper la corrida
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
        "modelo_potencia": asdict(config.MODELO),
        "calidad_knn": calidad_knn,
        "hilos_blas": hilos_blas,
        # Hilos de BLAS: no se fijan a propósito, para medir el comportamiento real por
        # defecto (es lo que hace que `knn_brute` sea multihilo). Se registra si el entorno
        # los limitaba, porque cambiaría por completo el resultado del experimento de ML.
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
    """Corre el benchmark completo y devuelve el DataFrame de mediciones crudas."""
    claves = claves or list(EXPERIMENTOS)
    config.DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)

    propio = MedidorPropio()
    print("Midiendo línea de base del sistema en reposo...")
    base = propio.medir_linea_base()
    print(
        f"  carga en reposo: {base['carga_sistema'] * 100:.1f}%  "
        f"potencia basal estimada: {base['potencia_w']:.2f} W\n"
    )

    filas: list[dict[str, Any]] = []

    with MedidorCodeCarbon() as codecarbon_medidor:
        # La ventana de medición la fija el camino que quedó activo: leer la potencia del
        # hardware exige que el muestreo caiga dentro del trabajo, estimarla no. El mismo
        # lote lo usan las dos vías, para que midan exactamente el mismo trabajo.
        lectura = codecarbon_medidor.lectura
        ventana = (
            config.DURACION_MINIMA_LOTE_MUESTREO_S
            if lectura.get("requiere_ventana_muestreo")
            else config.DURACION_MINIMA_LOTE_S
        )
        fuente = lectura.get("fuente_potencia") or "desconocida"
        print(
            f"  potencia del CPU: "
            f"{'lectura directa' if lectura.get('lectura_directa') else 'estimada'}"
            f" ({fuente})  |  ventana de medición >= {ventana:.1f} s\n"
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
                    lote = propio.calcular_lote(funcion, entrada, ventana)

                    for rep in range(1, repeticiones + 1):
                        medicion, _ = propio.medir(funcion, entrada, lote=lote)
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
                                "tiempo_s": medicion.tiempo_s,
                                "cpu_s": medicion.cpu_s,
                                "utilizacion": medicion.utilizacion,
                                "nucleos_activos": medicion.nucleos_activos,
                                "memoria_pico_mb": medicion.memoria_pico_mb,
                                "potencia_marginal_w": medicion.potencia_marginal_w,
                                "energia_kwh_propio": medicion.energia_atribuible_kwh,
                                "co2_kg_propio": medicion.co2_atribuible_kg,
                                "energia_total_kwh_propio": medicion.energia_total_kwh,
                                "co2_total_kg_propio": medicion.co2_total_kg,
                                "tiempo_s_codecarbon": cc["tiempo_s"],
                                "energia_kwh_codecarbon": cc["energia_kwh"],
                                "co2_kg_codecarbon": cc["co2_kg"],
                                "co2_kg_codecarbon_nativo": cc["co2_kg_nativo"],
                                "potencia_cpu_w_codecarbon": cc["potencia_cpu_w"],
                            }
                        )

                    ult = filas[-1]
                    print(
                        f"  n={n:<6} {nombre:<16} {exp.variantes[nombre]:<16} "
                        f"lote={lote:<6} t={ult['tiempo_s']:.3e}s  "
                        f"CO2(propio)={ult['co2_kg_propio']:.3e} kg  "
                        f"CO2(codecarbon)={ult['co2_kg_codecarbon']:.3e} kg"
                    )
            print()

        metadatos = metadatos_entorno()
        metadatos["codecarbon_deteccion"] = codecarbon_medidor.metadatos
        # La ventana efectiva depende de la fuente de potencia que quedó activa, así que se
        # registra: el informe la declara en lugar de suponer el valor por defecto.
        metadatos["ventana_medicion_s"] = ventana
        metadatos["linea_base"] = base

    df = pd.DataFrame(filas)
    df.to_csv(config.CSV_SIMULACION, index=False)
    (config.DIR_RESULTADOS / "metadatos.json").write_text(
        json.dumps(metadatos, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Resultados -> {config.CSV_SIMULACION.relative_to(config.RAIZ)}")
    print(f"Metadatos  -> resultados/metadatos.json")
    return df


def agregar(df: pd.DataFrame) -> pd.DataFrame:
    """Media y desvío estándar de las R repeticiones de cada (algoritmo, n)."""
    columnas = [
        "tiempo_s",
        "cpu_s",
        "utilizacion",
        "nucleos_activos",
        "potencia_marginal_w",
        "memoria_pico_mb",
        "energia_kwh_propio",
        "co2_kg_propio",
        "energia_kwh_codecarbon",
        "co2_kg_codecarbon",
        "co2_kg_codecarbon_nativo",
    ]
    agrupado = df.groupby(["experimento", "algoritmo", "complejidad", "n"], as_index=False).agg(
        {**{c: ["mean", "std"] for c in columnas}, "ejecuciones_lote": "first"}
    )
    agrupado.columns = [
        col[0] if col[1] in ("", "first") else f"{col[0]}_{col[1]}" for col in agrupado.columns
    ]
    return agrupado.sort_values(["experimento", "n", "algoritmo"]).reset_index(drop=True)


def cargar_resultados() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Relee del disco lo producido por `ejecutar()`."""
    if not config.CSV_SIMULACION.exists():
        raise FileNotFoundError(
            f"No existe {config.CSV_SIMULACION}. Ejecutar primero el benchmark."
        )
    df = pd.read_csv(config.CSV_SIMULACION)
    resumen = agregar(df)
    metadatos = json.loads((config.DIR_RESULTADOS / "metadatos.json").read_text(encoding="utf-8"))
    return df, resumen, metadatos
