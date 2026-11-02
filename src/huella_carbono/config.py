# Calculating the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Energy and emissions model parameters.

Every number the project uses lives here, together with its source and its rationale.
The goal is an auditable model: no magic constants hidden inside the measurement
logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------
# Project paths
# --------------------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parents[2]
DIR_RESULTADOS = RAIZ / "resultados"
DIR_GRAFICOS = DIR_RESULTADOS / "graficos"
# A single results CSV: it is the deliverable of the simulation. It holds one row per
# measured repetition, which is the finest grain; the means and deviations used by the
# report are derived from it in memory, so the same information is not versioned twice.
CSV_SIMULACION = DIR_RESULTADOS / "simulacion_huella_carbono.csv"
INFORME = RAIZ / "INFORME.md"


# --------------------------------------------------------------------------------------
# Power grid emission factor
# --------------------------------------------------------------------------------------

# Carbon intensity of the Argentine power grid, in kgCO2eq per kWh.
#
# The MOST RECENT figure available for Argentina is used. No value is hard-coded: it is
# read at run time from `datos/intensidad_carbono_argentina.json`, which versions the
# full series published by Our World in Data from Ember's yearly data, and the latest
# year of the series is picked automatically.
#
# Why CodeCarbon's built-in value is not used: its dataset
# (`codecarbon/data/private_infra/global_energy_mix.json`) is frozen at 2023 for
# Argentina (354.103 gCO2eq/kWh) even in the latest published version of the library.
# That value is still read here, but only as a reference for the report and to state
# the difference explicitly.

PAIS_ISO = "ARG"
DIR_DATOS = RAIZ / "datos"
ARCHIVO_INTENSIDAD_CARBONO = DIR_DATOS / "intensidad_carbono_argentina.json"


def cargar_serie_intensidad_carbono() -> dict[str, Any]:
    """Read the Argentine grid carbon intensity series versioned in the repo."""
    if not ARCHIVO_INTENSIDAD_CARBONO.is_file():
        raise RuntimeError(
            f"The carbon intensity dataset is missing at {ARCHIVO_INTENSIDAD_CARBONO}. "
            "It is a file versioned with the project; it should not be missing."
        )
    with ARCHIVO_INTENSIDAD_CARBONO.open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    if not datos.get("serie_g_kwh"):
        raise RuntimeError(
            f"{ARCHIVO_INTENSIDAD_CARBONO.name} has no 'serie_g_kwh' key with data."
        )
    return datos


def factor_emision_mas_reciente(serie: dict[str, float]) -> tuple[int, float]:
    """Return (year, gCO2eq/kWh) for the most recent year in the series."""
    anio = max(int(a) for a in serie)
    return anio, float(serie[str(anio)])


def ruta_dataset_emisiones() -> Path:
    """
    Locate the electricity mix JSON inside the installed `codecarbon` package.

    It is resolved with `find_spec` instead of `import codecarbon` because importing the
    whole package is expensive (it pulls in its dependencies) and only the path of a
    data file is needed here.
    """
    spec = find_spec("codecarbon")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError(
            "The `codecarbon` package cannot be found in the environment. "
            "Install the project dependencies (`uv sync`)."
        )
    raiz_paquete = Path(next(iter(spec.submodule_search_locations)))
    return raiz_paquete / "data" / "private_infra" / "global_energy_mix.json"


def cargar_matriz_electrica(iso: str = PAIS_ISO) -> dict[str, Any]:
    """Return a country's electricity mix record as shipped by CodeCarbon."""
    ruta = ruta_dataset_emisiones()
    if not ruta.is_file():
        raise RuntimeError(
            f"CodeCarbon's electricity mix dataset is not at {ruta}. "
            "Its location may have changed in this version of CodeCarbon."
        )
    with ruta.open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    if iso not in datos:
        raise KeyError(f"CodeCarbon's dataset has no country key '{iso}'.")
    return datos[iso]


# --- emission factor actually used in every calculation of the project ---
INTENSIDAD_CARBONO = cargar_serie_intensidad_carbono()
ANIO_FACTOR_EMISION, FACTOR_EMISION_AR_G_KWH = factor_emision_mas_reciente(
    INTENSIDAD_CARBONO["serie_g_kwh"]
)
FACTOR_EMISION_AR = FACTOR_EMISION_AR_G_KWH / 1000.0  # kgCO2eq/kWh
FUENTE_FACTOR_EMISION = INTENSIDAD_CARBONO["fuente"]

# Official factor from Argentina's Energy Secretariat, cited in the report only as a
# methodological contrast (it is a UNFCCC-style marginal factor, not an average grid
# intensity). It lives in the same data file so that no figure in the report is hard-coded.
REFERENCIA_FACTOR_OFICIAL = INTENSIDAD_CARBONO.get("referencia_factor_oficial", {})

# --- CodeCarbon's built-in value, only as a reference and contrast in the report ---
REGISTRO_PAIS = cargar_matriz_electrica()
FACTOR_EMISION_CODECARBON_G_KWH = float(REGISTRO_PAIS["carbon_intensity"])
ANIO_FACTOR_EMISION_CODECARBON = int(REGISTRO_PAIS["year"])

# Context on the Argentine electricity mix (CodeCarbon record), used in the theoretical
# background of the report. The year is the one the dataset itself declares, not an
# assumption: it is the latest year with a by-source breakdown available, and it may be
# earlier than the year of the emission factor used in the calculations.
MATRIZ_AR = {
    "anio": ANIO_FACTOR_EMISION_CODECARBON,
    "total_TWh": float(REGISTRO_PAIS["total_TWh"]),
    "fossil_TWh": float(REGISTRO_PAIS["fossil_TWh"]),
    "gas_TWh": float(REGISTRO_PAIS["gas_TWh"]),
    "oil_TWh": float(REGISTRO_PAIS["oil_TWh"]),
    "coal_TWh": float(REGISTRO_PAIS["coal_TWh"]),
    "hydroelectricity_TWh": float(REGISTRO_PAIS["hydroelectricity_TWh"]),
    "nuclear_TWh": float(REGISTRO_PAIS["nuclear_TWh"]),
    "wind_TWh": float(REGISTRO_PAIS["wind_TWh"]),
    "solar_TWh": float(REGISTRO_PAIS["solar_TWh"]),
    "pais": str(REGISTRO_PAIS["country_name"]),
}


# PUE (Power Usage Effectiveness): the factor that, in a datacenter, accounts for the
# energy spent on cooling and infrastructure in addition to that of the computation.
# Here the experiment runs on a laptop on a desk, with no external cooling
# infrastructure, so PUE = 1.0. It is kept explicit because if the same code ran in a
# datacenter it would have to be multiplied by 1.1 - 1.6.
PUE = 1.0


# --------------------------------------------------------------------------------------
# Hardware power model
# --------------------------------------------------------------------------------------


# A custom power model is described in the report (section 3.3) as a calculation option,
# but the project does not implement it: measurement is done by CodeCarbon.


# --------------------------------------------------------------------------------------
# Benchmark parameters
# --------------------------------------------------------------------------------------

SEMILLA = 42  # fixed seed: every algorithm receives exactly the same input
REPETICIONES = 3  # each (algorithm, n) is run R times -> mean and standard deviation

# Batch measurement.
#
# Efficient algorithms are so fast that a single run falls below the resolution of the
# measurement tools: `psutil.cpu_times()` has a granularity on the order of 10 ms on
# macOS, and `timsort_nativo` on n=1000 takes ~1 ms. Measuring that directly would yield
# utilizations of 0 or 1 depending on rounding, not a data point.
#
# Standard solution (the same one used by the standard library's `timeit` module): run
# the algorithm K times inside the measured region, with K auto-tuned so that the batch
# lasts at least DURACION_MINIMA_LOTE_S, and then divide by K. That way every measurement
# is taken over a sufficiently large time window.
DURACION_MINIMA_LOTE_S = 0.5
# When power is READ from the hardware, a much longer window is needed, because sampling
# has to fall WITHIN the work. Measured on this machine: reading adds a fixed overhead of
# about 1.95 s per measurement (taken when the task closes), so the reported duration is
# inflated 5.7x with 0.4 s windows, 2.4x with 1.4 s and 1.65x with 3 s. 3 s is adopted
# as a compromise between accuracy and run time.
DURACION_MINIMA_LOTE_MUESTREO_S = 3.0

# Cap on runs per batch. It is a safety net against an unrepresentative probe (if the
# trial run measured almost zero, K would go to infinity), not a design limit: batch size
# is governed by the time window. It has to leave enough headroom to reach the window with
# the project's fastest algorithms: `fib_iterativo` runs in about 450 ns, so it needs on
# the order of 7 million runs to cover 3 s. With a low cap, precisely the most efficient
# algorithms in each experiment would be measured over short windows and their energy
# would come out inflated relative to their alternatives, which is the bias that would
# ruin the comparison.
MAX_EJECUCIONES_LOTE = 10_000_000

# Duration of the probe batch used to estimate the time per run before fixing K.
# 10 ms is enough to average out clock noise and is negligible compared to the window.
DURACION_SONDEO_S = 0.01


@dataclass
class Experimento:
    clave: str
    titulo: str
    pregunta: str
    tamanios_completo: list[int]
    tamanios_rapido: list[int]
    unidad_n: str = "n"
    notas: str = ""
    variantes: dict[str, str] = field(default_factory=dict)  # algorithm -> complexity
    # What each variant does, in plain language and in three lines at most: the report
    # inserts it before each experiment's chart, so it is clear what was compared.
    descripciones: dict[str, str] = field(default_factory=dict)
    # Scales that section 5.3 uses to extrapolate this experiment's emissions. The default
    # (one million and one billion runs) makes sense for a function called by a service;
    # not for a model training, so each experiment can declare its own: a list of
    # (multiplier, description).
    escalas: list[tuple[int, str]] | None = None


EXPERIMENTOS: dict[str, Experimento] = {
    "ordenamiento": Experimento(
        clave="ordenamiento",
        titulo="Sorting algorithms",
        pregunta=(
            "Does computational complexity translate into a measurable difference in "
            "emissions when the output produced is identical?"
        ),
        tamanios_completo=[1000, 2000, 4000, 8000],
        tamanios_rapido=[500, 1000],
        unidad_n="number of elements",
        notas=(
            "All three variants sort exactly the same list of integers, generated "
            "with a fixed seed, and return the same result."
        ),
        variantes={
            "bubble_sort": "O(n²)",
            "merge_sort": "O(n log n)",
            "timsort_nativo": "O(n log n) in C",
        },
        descripciones={
            "bubble_sort": (
                "Compares neighboring elements and swaps them if they are out of order, "
                "repeating the pass until there is nothing left to swap. It is the "
                "simplest method to write and the one that does the most work."
            ),
            "merge_sort": (
                "Splits the list in halves until only single elements remain, then merges "
                "them back in pairs, already sorted. Written in Python."
            ),
            "timsort_nativo": (
                "Python's built-in sort, written in C. It uses the same idea of merging "
                "sorted halves, but also detects and takes advantage of stretches that "
                "were already in order."
            ),
        },
    ),
    "fibonacci": Experimento(
        clave="fibonacci",
        titulo="Computing Fibonacci",
        pregunta=(
            "What is the environmental cost of recomputing work already done? "
            "A comparison between exponential and linear growth."
        ),
        tamanios_completo=[20, 25, 30, 32],
        tamanios_rapido=[18, 22],
        unidad_n="term n of the sequence",
        notas=(
            "Capped at n=32 because the naive recursive variant grows "
            "exponentially and would dominate the total benchmark time."
        ),
        variantes={
            "fib_recursivo": "O(φⁿ)",
            "fib_memoizado": "O(n)",
            "fib_iterativo": "O(n)",
        },
        descripciones={
            "fib_recursivo": (
                "To get a term it adds the two previous ones, and for each of them it "
                "starts over from scratch, remembering nothing. It ends up recomputing "
                "the same values an enormous number of times."
            ),
            "fib_memoizado": (
                "Does the same, but records each result the first time it computes it "
                "and then reuses it instead of computing it again."
            ),
            "fib_iterativo": (
                "Walks through the sequence just once, from the bottom up, keeping "
                "only the last two values."
            ),
        },
    ),
    "matrices": Experimento(
        clave="matrices",
        titulo="Matrix multiplication",
        pregunta=(
            "With the same O(n³) algorithmic complexity, how much does the choice of "
            "implementation (pure Python versus an optimized numerical library) weigh "
            "environmentally?"
        ),
        tamanios_completo=[100, 200, 300],
        tamanios_rapido=[60, 100],
        unidad_n="dimension n of the n×n matrix",
        notas=(
            "Both variants compute the same product with the same asymptotic "
            "complexity. The difference in footprint is purely the cost of implementation."
        ),
        variantes={
            "matmul_python": "O(n³) in Python",
            "matmul_numpy": "O(n³) vectorized",
        },
        descripciones={
            "matmul_python": (
                "Multiplies the matrices element by element, with three nested loops "
                "written in Python. Every operation goes through the interpreter."
            ),
            "matmul_numpy": (
                "Hands the same multiplication to a compiled numerical library, which "
                "operates on blocks of data at once instead of number by number."
            ),
        },
    ),
    "aprendizaje_knn": Experimento(
        clave="aprendizaje_knn",
        titulo="Training and inference of an ML model (KNN)",
        pregunta=(
            "With exactly the same predictive result, how much does the footprint change "
            "depending on how the neighbor search is implemented, and what happens when one "
            "of them uses all cores instead of one?"
        ),
        tamanios_completo=[2500, 5000, 10000, 20000],
        tamanios_rapido=[2000, 4000],
        unidad_n="dataset samples",
        notas=(
            "The model is a nearest-neighbors classifier, which does not infer any rule: "
            "to decide which category a new data point belongs to, it finds the 31 most "
            "similar points among those it already knows and assigns it the category that "
            "prevails among those 31. Here, similar means close, measuring the distance across "
            "the 20 features that describe each data point.\n\n"
            "The expensive part is precisely finding those 31 neighbors among thousands of "
            "points, and that is where the three variants differ. Training and "
            "classification are measured as a single unit of work, and all three return "
            "exactly the same predictions."
        ),
        variantes={
            "knn_brute": "O(n·m·d) vectorized",
            "knn_kd_tree": "O(n·d) + O(n log n)",
            "knn_ball_tree": "O(n·d) + O(n log n)",
        },
        descripciones={
            "knn_brute": (
                "Measures the distance from the new point to every known point, one by "
                "one, and keeps the 31 closest. It discards nothing, but it does those "
                "computations in blocks and spreads the work across all cores."
            ),
            "knn_kd_tree": (
                "Before classifying, it arranges the known points by splitting the space "
                "with straight cuts, like an irregular grid. When searching for neighbors "
                "it discards the far-away zones in one go, instead of going point by point."
            ),
            "knn_ball_tree": (
                "Does the same as `knn_kd_tree` (discarding whole zones instead of going "
                "through everything), but groups the known points into bubbles instead of "
                "cutting them with straight lines. Uses a single core."
            ),
        },
        # The report's fit is done on CO2, not on time, and for this experiment the two do
        # not match. The work is O(n·m·d) with m = 0.2·n, i.e. quadratic in n for all three
        # variants: the O(n log n) construction of the trees does not dominate because in
        # 20 dimensions the query stops pruning (curse of dimensionality).
        # `brute` spreads that quadratic work across all cores, so its TIME grows more
        # slowly, but energy counts core-seconds and its CO2 exponent gets back close to 2.
        escalas=[
            (365, "one retraining per day for a year"),
            (8_760, "one retraining per hour for a year"),
        ],
    ),
}


# --------------------------------------------------------------------------------------
# Equivalences to translate kgCO2eq into tangible quantities
# --------------------------------------------------------------------------------------

# They are read from `datos/equivalencias_co2.json` at run time. Electrical equivalences
# are stored as CONSUMPTION in kWh and converted with FACTOR_EMISION_AR, so they can never
# drift out of sync with the current emission factor. Direct ones store their value along
# with the source and the URL it comes from.

ARCHIVO_EQUIVALENCIAS = DIR_DATOS / "equivalencias_co2.json"


def cargar_equivalencias() -> tuple[list[tuple[str, float, str]], dict[str, Any]]:
    """
    Return the equivalences as (name, kgCO2eq per unit, source) plus the raw data.

    The raw data is also returned so the report can cite URLs and access dates.
    """
    if not ARCHIVO_EQUIVALENCIAS.is_file():
        raise RuntimeError(
            f"The equivalences file is missing at {ARCHIVO_EQUIVALENCIAS}. "
            "It is a file versioned with the project; it should not be missing."
        )
    with ARCHIVO_EQUIVALENCIAS.open(encoding="utf-8") as archivo:
        crudo = json.load(archivo)

    lista: list[tuple[str, float, str]] = []
    for item in crudo.get("directas", []):
        lista.append((item["nombre"], float(item["kg_co2_por_unidad"]), item["fuente"]))
    for item in crudo.get("vehiculares", []):
        # kgCO2/km = (L/100 km ÷ 100) × kgCO2/L. Both terms are Argentine data.
        consumo = float(item["consumo_l_por_100km"])
        factor_combustible = float(item["factor_kg_co2_por_litro"])
        consumo_txt = f"{consumo:.1f}"
        combustible_txt = f"{factor_combustible:.4f}"
        fuente = (
            f"{consumo_txt} L/100 km (average light-vehicle consumption in Argentina) × "
            f"{combustible_txt} kgCO₂/L ({item['combustible']})"
        )
        lista.append((item["nombre"], consumo / 100 * factor_combustible, fuente))
    for item in crudo.get("electricas", []):
        consumo = float(item["consumo_kwh"])
        detalle = item["detalle"]
        consumo_txt = f"{consumo:.3f}"
        factor_txt = f"{FACTOR_EMISION_AR:.3f}"
        fuente = (
            f"{detalle[:1].upper()}{detalle[1:]}: {consumo_txt} kWh × "
            f"{factor_txt} kgCO₂eq/kWh (EF {ANIO_FACTOR_EMISION})"
        )
        lista.append((item["nombre"], consumo * FACTOR_EMISION_AR, fuente))
    return lista, crudo


EQUIVALENCIAS, EQUIVALENCIAS_CRUDO = cargar_equivalencias()

# Annual CO2 absorption of a tree, for the report's offsetting calculation. These are the
# reference values adopted by this work, declared as such: they were not measured here.
ARBOLES: list[tuple[str, float, str]] = [
    (item["nombre"], float(item["kg_co2_por_anio"]), item.get("detalle", ""))
    for item in EQUIVALENCIAS_CRUDO.get("arboles", [])
]
