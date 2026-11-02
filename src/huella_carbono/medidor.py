# Compute the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Energy consumption measurement with CodeCarbon.

`MedidorCodeCarbon` is the project's only measurement path: every figure in the report
comes from here. It reads power from the hardware when the machine allows it and estimates it
when it does not (see `preferir_lectura_directa`).

`calcular_lote` does not measure consumption: it sizes how many runs fit in the window of
each measurement.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from huella_carbono import config



def calcular_lote(
    funcion: Callable[[Any], Any],
    entrada: Any,
    ventana_minima_s: float = config.DURACION_MINIMA_LOTE_S,
) -> int:
    """
    Determine how many runs to put in a batch so that the measured window lasts at least
    `ventana_minima_s`. It also serves as warm-up: it leaves caches and interpreter warm before
    measuring for real.

    The minimum window depends on how power is obtained: estimating it only requires getting
    beyond the clock resolution, but reading it from the hardware requires sampling to happen while
    the work is running (see `DURACION_MINIMA_LOTE_MUESTREO_S`).

    The time per run is NOT estimated from a single run: the first one is much slower
    than the following ones —cold caches and interpreter, and in NumPy or scikit-learn the
    internal initialization of the first call—, and extrapolating from it leaves the batch far
    below the requested window. A probe batch is grown until it lasts long enough
    to be a stable measurement, and the extrapolation is done from there.
    """
    funcion(entrada)  # warm-up: the first run does not count

    sondeo, duracion = 1, 0.0
    while sondeo <= config.MAX_EJECUCIONES_LOTE:
        t0 = time.perf_counter()
        for _ in range(sondeo):
            funcion(entrada)
        duracion = time.perf_counter() - t0
        if duracion >= config.DURACION_SONDEO_S:
            break
        sondeo *= 10

    por_ejecucion = max(duracion / sondeo, 1e-12)
    k = int(ventana_minima_s / por_ejecucion) + 1
    return max(1, min(k, config.MAX_EJECUCIONES_LOTE))


class MedidorCodeCarbon:
    """
    Wrapper around `OfflineEmissionsTracker` using its task API.

    Two deliberate decisions:

    - The OFFLINE tracker is used with `country_iso_code="ARG"`. The online tracker
      geolocates by IP with a network call, which would make the experiment
      non-reproducible and dependent on the connection.
    - `start_task()` / `stop_task()` are used instead of creating one tracker per measurement.
      Verified empirically: starting and stopping a tracker costs a few tenths of a
      second that fall inside the reported window, so one tracker per measurement
      inflates the duration of millisecond measurements by an order of magnitude (measured:
      0.42 s reported for 0.010 s of actual work). With the task API the reported
      duration matches the actual time within 1%. The detection cost is
      measured on every run and stored in `metadatos.json`
      (`codecarbon_deteccion.segundos_deteccion_hardware`).
    """

    def __init__(self, medir_cada_s: float = 1.0) -> None:
        from codecarbon import OfflineEmissionsTracker

        config.DIR_RESULTADOS.mkdir(parents=True, exist_ok=True)
        inicio_construccion = time.perf_counter()
        self.tracker = OfflineEmissionsTracker(
            country_iso_code="ARG",
            measure_power_secs=medir_cada_s,
            log_level="error",
            # It is not allowed to write its own CSVs: it would duplicate in `emissions.csv` and in
            # `emissions_base_<run_id>.csv` what is already in the simulation CSV. The
            # native values cited in the report come from the API, not from those files.
            save_to_file=False,
        )
        self.activo = False
        self.metadatos: dict[str, Any] = {}
        # The library only initializes the hardware in `start()`. It is forced here so that
        # its choice of power source can be corrected before it starts measuring: direct
        # reading if the machine allows it, estimation as fallback. Once this is done, `start()`
        # no longer reinitializes anything (`_hardware_initialized` stays True).
        self.tracker._ensure_hardware_ready()
        self.lectura = preferir_lectura_directa(self.tracker)
        # Hardware detection cost, measured rather than estimated: it is the argument
        # for using the task API instead of instantiating one tracker per measurement.
        self.segundos_deteccion = time.perf_counter() - inicio_construccion

    def __enter__(self) -> "MedidorCodeCarbon":
        inicio_arranque = time.perf_counter()
        self.tracker.start()
        self.segundos_deteccion += time.perf_counter() - inicio_arranque
        self.activo = True
        return self

    def __exit__(self, *excepciones: object) -> None:
        if self.activo:
            self.tracker.stop()
            self.activo = False

    def medir(
        self,
        nombre_tarea: str,
        funcion: Callable[[Any], Any],
        entrada: Any,
        lote: int = 1,
    ) -> dict[str, float]:
        """Measure a batch of `lote` runs and normalize the result per run."""
        self.tracker.start_task(nombre_tarea)
        # Time is measured around the work, not taken from the duration the library
        # reports: that one includes the time the library itself takes to read power when
        # closing the task. Both are kept so the difference is visible.
        inicio = time.perf_counter()
        for _ in range(lote):
            funcion(entrada)
        tiempo_s = time.perf_counter() - inicio
        datos = self.tracker.stop_task(nombre_tarea)
        if not self.metadatos:
            self.metadatos = {
                "cpu_model": datos.cpu_model,
                "cpu_power_w": datos.cpu_power,
                "segundos_deteccion_hardware": round(self.segundos_deteccion, 2),
                **tdp_de_referencia(datos.cpu_model),
                **modo_de_medicion_cpu(self.tracker),
                **self.lectura,
                "ram_power_w": datos.ram_power,
                "os": datos.os,
                "country": datos.country_name,
                "run_id": str(datos.run_id),
            }
        # CO2 is recomputed from the energy CodeCarbon measures by applying the most recent
        # emission factor (see config): the library converts internally with its
        # dataset frozen in 2023. The native value is kept anyway so the difference
        # is stated in the report.
        factor = config.FACTOR_EMISION_AR * config.PUE
        return {
            "tiempo_s": max(tiempo_s, 1e-9) / lote,
            "tiempo_s_informado": datos.duration / lote,
            "energia_kwh": datos.energy_consumed / lote,
            "co2_kg": datos.energy_consumed * factor / lote,
            "co2_kg_nativo": datos.emissions / lote,
            "potencia_cpu_w": datos.cpu_power,
            "potencia_ram_w": datos.ram_power,
        }


# Modes in which CodeCarbon reads power from a hardware counter instead of
# computing it. It is the library's own list (`external/hardware.py`, `CPU.start`):
# Intel RAPL on Linux, Intel Power Gadget and the Energy Meter Interface on Windows, and
# powermetrics on Apple Silicon. Any other mode (`cpu_load`, `constant`) is an estimate.
MODOS_LECTURA_DIRECTA = (
    "intel_rapl",
    "intel_power_gadget",
    "windows_emi",
    "apple_powermetrics",
)


def modo_activo(tracker: Any) -> str | None:
    """Mode the CPU power measurement ended up configured with."""
    for hardware in getattr(tracker, "_hardware", []):
        nombre = type(hardware).__name__
        if nombre == "AppleSiliconChip":
            return "apple_powermetrics"
        if nombre == "CPU":
            return getattr(hardware, "_mode", None)
    return None


def preferir_lectura_directa(tracker: Any) -> dict[str, Any]:
    """
    Enforce the project rule: if power can be read from the hardware, it is read; if
    not, it is estimated.

    On most platforms CodeCarbon already does this —it tries Intel RAPL on Linux and the
    Energy Meter Interface on Windows before falling back to its estimate—, so there is nothing
    to correct here and the function changes nothing.

    The exception is Apple Silicon: there the library first tries its estimated mode
    `cpu_load`, and that attempt never fails, because it returns True just by having `psutil`, which
    is one of its mandatory dependencies. Its `powermetrics` branch is therefore unreachable
    even when the machine allows it (`core/resource_tracker.py`,
    `_try_platform_cpu_backend`). Only in that case is the estimated meter replaced by the
    real one.

    Only the CPU meter is replaced: the RAM meter is left as is and the GPU
    is not added, because it is idle in these workloads and its power is not attributable to the
    measured algorithms.

    Returns what ended up active, so the report states it instead of assuming it.
    """
    modo = modo_activo(tracker)
    if modo in MODOS_LECTURA_DIRECTA:
        return {
            "lectura_directa": True,
            "fuente_potencia": modo,
            "prioridad_forzada": False,
            "requiere_ventana_muestreo": modo == "apple_powermetrics",
            "motivo_estimacion": None,
        }

    def estimando(motivo: str) -> dict[str, Any]:
        return {
            "lectura_directa": False,
            "fuente_potencia": modo,
            "prioridad_forzada": False,
            "requiere_ventana_muestreo": False,
            "motivo_estimacion": motivo,
        }

    try:
        from codecarbon.core import powermetrics
        from codecarbon.external.hardware import AppleSiliconChip
    except Exception as error:  # noqa: BLE001 - diagnostics, must not break the run
        return estimando(f"could not query direct reading: {error}")

    if not powermetrics.is_powermetrics_available():
        return estimando(
            "this machine offers no direct power reading that CodeCarbon "
            "knows how to use (on Linux it would be Intel RAPL, on Windows the Energy Meter Interface, "
            "and on Apple Silicon powermetrics with root privileges)"
        )

    try:
        chip = AppleSiliconChip.from_utils(tracker._output_dir, chip_part="CPU")
        hardware = getattr(tracker, "_hardware", [])
        for estimado in [h for h in hardware if type(h).__name__ == "CPU"]:
            hardware.remove(estimado)
        hardware.append(chip)
        tracker._conf["cpu_model"] = chip.get_model()
    except Exception as error:  # noqa: BLE001 - if the replacement fails, estimation continues
        return estimando(f"powermetrics failed to initialize: {error}")

    return {
        "lectura_directa": True,
        "fuente_potencia": "apple_powermetrics",
        "prioridad_forzada": True,
        "requiere_ventana_muestreo": True,
        "motivo_estimacion": None,
    }


def modo_de_medicion_cpu(tracker: Any) -> dict[str, Any]:
    """
    Report how CodeCarbon is measuring CPU power in this run.

    On Apple Silicon the library uses `powermetrics` if it can run it with root
    privileges and, if not, falls back to `cpu_load` mode, which estimates from a generic TDP. The
    report needs to know which of the two paths was taken so as not to claim something false, so
    it is read from the tracker's hardware object instead of being assumed.
    """
    # Was powermetrics available to the library? CodeCarbon itself is queried
    # so the report can distinguish between two very different reasons for using an
    # approximate model: lacking permissions, or having them and still not using it.
    try:
        from codecarbon.core import powermetrics

        powermetrics_disponible = bool(powermetrics.is_powermetrics_available())
    except Exception:  # noqa: BLE001 - it is diagnostic information, must not break the run
        powermetrics_disponible = None

    for hardware in getattr(tracker, "_hardware", []):
        if type(hardware).__name__ == "AppleSiliconChip":
            return {
                "modo_cpu": "apple_powermetrics",
                "tdp_generico": False,
                "tdp_w": None,
                "powermetrics_disponible": powermetrics_disponible,
            }
        if type(hardware).__name__ == "CPU":
            return {
                "modo_cpu": getattr(hardware, "_mode", None),
                "tdp_generico": getattr(hardware, "_is_generic_tdp", None),
                "tdp_w": getattr(hardware, "_tdp", None),
                "powermetrics_disponible": powermetrics_disponible,
            }
    return {
        "modo_cpu": None,
        "tdp_generico": None,
        "tdp_w": None,
        "powermetrics_disponible": powermetrics_disponible,
    }


def tdp_de_referencia(modelo_cpu: str) -> dict[str, Any]:
    """
    Look up the CPU TDP in CodeCarbon's reference table.

    The report states that this machine is not in that table and that the library therefore
    applies its default constant. The claim is verified here at runtime
    instead of being written by hand: it returns whether the model is in the CSV, the TDP
    found and the value of `POWER_CONSTANT` the library uses as a replacement.
    """
    from codecarbon.external.hardware import POWER_CONSTANT

    ruta = config.ruta_dataset_emisiones().parents[1] / "hardware" / "cpu_power.csv"
    tdp: float | None = None
    if ruta.is_file():
        with ruta.open(encoding="utf-8") as archivo:
            next(archivo, None)  # header
            for linea in archivo:
                nombre, _, potencia = linea.rpartition(",")
                if nombre.strip().lower() == modelo_cpu.strip().lower():
                    tdp = float(potencia)
                    break
    return {
        "tdp_en_tabla_codecarbon": tdp,
        "tdp_por_defecto_codecarbon_w": float(POWER_CONSTANT),
        "archivo_tdp_codecarbon": str(ruta.name),
    }
