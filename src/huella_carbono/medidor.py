# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Medición del consumo energético con CodeCarbon.

`MedidorCodeCarbon` es la única vía de medición del proyecto: de acá salen todas las
cifras del informe. Lee la potencia del hardware cuando el equipo lo permite y la estima
cuando no (ver `preferir_lectura_directa`).

`calcular_lote` no mide consumo: dimensiona cuántas ejecuciones entran en la ventana de
cada medición.
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
    Determina cuántas ejecuciones meter en un lote para que la ventana medida dure al menos
    `ventana_minima_s`. Sirve además de warm-up: deja cachés e intérprete calientes antes de
    medir en serio.

    La ventana mínima depende de cómo se obtenga la potencia: estimarla sólo exige salir de
    la resolución del reloj, pero leerla del hardware exige que el muestreo ocurra mientras
    el trabajo corre (ver `DURACION_MINIMA_LOTE_MUESTREO_S`).

    El tiempo por ejecución NO se estima con una sola corrida: la primera es mucho más lenta
    que las siguientes —cachés e intérprete fríos, y en NumPy o scikit-learn la
    inicialización interna de la primera llamada—, y extrapolando de ella el lote queda muy
    por debajo de la ventana pedida. Se crece un lote de sondeo hasta que dure lo suficiente
    para ser una medición estable, y de ahí se extrapola.
    """
    funcion(entrada)  # warm-up: la primera ejecución no cuenta

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
    Envoltorio sobre `OfflineEmissionsTracker` usando su API de tareas.

    Dos decisiones deliberadas:

    - Se usa el tracker OFFLINE con `country_iso_code="ARG"`. El tracker online
      geolocaliza por IP con una llamada de red, lo que haría el experimento no
      reproducible y dependiente de la conexión.
    - Se usa `start_task()` / `stop_task()` en lugar de crear un tracker por medición.
      Verificado empíricamente: arrancar y detener un tracker cuesta unas décimas de
      segundo que caen dentro de la ventana informada, así que un tracker por medición
      infla la duración de mediciones de milisegundos en un orden de magnitud (medido:
      0,42 s informados para 0,010 s de trabajo real). Con la API de tareas la duración
      informada coincide con el tiempo real dentro del 1%. El costo de la detección se
      mide en cada corrida y queda en `metadatos.json`
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
            # No se le deja escribir sus propios CSV: duplicaría en `emissions.csv` y en
            # `emissions_base_<run_id>.csv` lo que ya queda en el CSV de la simulación. Los
            # valores nativos que se citan en el informe salen de la API, no de esos archivos.
            save_to_file=False,
        )
        self.activo = False
        self.metadatos: dict[str, Any] = {}
        # La librería inicializa el hardware recién en `start()`. Se fuerza acá para poder
        # corregir su elección de fuente de potencia antes de que empiece a medir: lectura
        # directa si el equipo la permite, estimación como fallback. Hecho esto, `start()`
        # ya no reinicializa nada (`_hardware_initialized` queda en True).
        self.tracker._ensure_hardware_ready()
        self.lectura = preferir_lectura_directa(self.tracker)
        # Costo de la detección de hardware, medido en vez de estimado: es el argumento
        # para usar la API de tareas en lugar de instanciar un tracker por medición.
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
        """Mide un lote de `lote` ejecuciones y normaliza el resultado por ejecución."""
        self.tracker.start_task(nombre_tarea)
        # El tiempo se cronometra alrededor del trabajo, no se toma de la duración que
        # informa la librería: esa incluye lo que ella misma tarda en leer la potencia al
        # cerrar la tarea. Se conservan las dos para que la diferencia quede a la vista.
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
        # El CO2 se recalcula a partir de la energía que mide CodeCarbon aplicando el factor
        # de emisión más reciente (ver config): la librería convierte internamente con su
        # dataset congelado en 2023. Se conserva igual el valor nativo para que la diferencia
        # quede declarada en el informe.
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


# Modos en los que CodeCarbon lee la potencia de un contador del hardware, en lugar de
# calcularla. Es la propia lista de la librería (`external/hardware.py`, `CPU.start`):
# Intel RAPL en Linux, Intel Power Gadget y el Energy Meter Interface en Windows, y
# powermetrics en Apple Silicon. Cualquier otro modo (`cpu_load`, `constant`) es estimación.
MODOS_LECTURA_DIRECTA = (
    "intel_rapl",
    "intel_power_gadget",
    "windows_emi",
    "apple_powermetrics",
)


def modo_activo(tracker: Any) -> str | None:
    """Modo con el que quedó configurada la medición de potencia del CPU."""
    for hardware in getattr(tracker, "_hardware", []):
        nombre = type(hardware).__name__
        if nombre == "AppleSiliconChip":
            return "apple_powermetrics"
        if nombre == "CPU":
            return getattr(hardware, "_mode", None)
    return None


def preferir_lectura_directa(tracker: Any) -> dict[str, Any]:
    """
    Garantiza la regla del trabajo: si la potencia se puede leer del hardware, se lee; si
    no, se estima.

    En la mayoría de las plataformas CodeCarbon ya hace eso —prueba Intel RAPL en Linux y el
    Energy Meter Interface en Windows antes de caer a su estimación—, así que acá no hay nada
    que corregir y la función no toca nada.

    La excepción es Apple Silicon: ahí la librería prueba primero su modo estimado
    `cpu_load` y ese intento nunca falla, porque devuelve True con sólo tener `psutil`, que
    es dependencia obligatoria suya. Su rama de `powermetrics` queda entonces inalcanzable
    aunque el equipo la permita (`core/resource_tracker.py`,
    `_try_platform_cpu_backend`). Sólo en ese caso se reemplaza el medidor estimado por el
    real.

    Se reemplaza únicamente el medidor de CPU: el de RAM se deja como está y el chip gráfico
    no se agrega, porque está ocioso en estas cargas y su potencia no es atribuible a los
    algoritmos medidos.

    Devuelve qué quedó activo, para que el informe lo declare en lugar de suponerlo.
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
    except Exception as error:  # noqa: BLE001 - diagnóstico, no debe romper la corrida
        return estimando(f"no se pudo consultar la lectura directa: {error}")

    if not powermetrics.is_powermetrics_available():
        return estimando(
            "este equipo no ofrece ninguna lectura directa de potencia que CodeCarbon "
            "sepa usar (en Linux sería Intel RAPL, en Windows el Energy Meter Interface, "
            "y en Apple Silicon powermetrics con privilegios de root)"
        )

    try:
        chip = AppleSiliconChip.from_utils(tracker._output_dir, chip_part="CPU")
        hardware = getattr(tracker, "_hardware", [])
        for estimado in [h for h in hardware if type(h).__name__ == "CPU"]:
            hardware.remove(estimado)
        hardware.append(chip)
        tracker._conf["cpu_model"] = chip.get_model()
    except Exception as error:  # noqa: BLE001 - si falla el reemplazo, sigue la estimación
        return estimando(f"powermetrics falló al inicializarse: {error}")

    return {
        "lectura_directa": True,
        "fuente_potencia": "apple_powermetrics",
        "prioridad_forzada": True,
        "requiere_ventana_muestreo": True,
        "motivo_estimacion": None,
    }


def modo_de_medicion_cpu(tracker: Any) -> dict[str, Any]:
    """
    Informa cómo está midiendo CodeCarbon la potencia del CPU en esta corrida.

    En Apple Silicon la librería usa `powermetrics` si puede correrlo con privilegios de
    root y, si no, cae al modo `cpu_load`, que estima a partir de un TDP genérico. El
    informe necesita saber cuál de los dos caminos se tomó para no afirmar algo falso, así
    que se lee del objeto de hardware del tracker en lugar de suponerlo.
    """
    # ¿Estaba powermetrics disponible para la librería? Se consulta a la propia CodeCarbon
    # para poder distinguir en el informe entre dos causas muy distintas de que use un
    # modelo aproximado: que no tenga permisos, o que teniéndolos no lo use igual.
    try:
        from codecarbon.core import powermetrics

        powermetrics_disponible = bool(powermetrics.is_powermetrics_available())
    except Exception:  # noqa: BLE001 - es información de diagnóstico, no debe romper la corrida
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
    Busca el TDP del CPU en la tabla de referencia de CodeCarbon.

    El informe afirma que este equipo no figura en esa tabla y que por eso la librería
    aplica su constante por defecto. La afirmación se verifica acá en tiempo de ejecución
    en lugar de quedar escrita a mano: se devuelve si el modelo está en el CSV, el TDP
    encontrado y el valor de `POWER_CONSTANT` que la librería usa como reemplazo.
    """
    from codecarbon.external.hardware import POWER_CONSTANT

    ruta = config.ruta_dataset_emisiones().parents[1] / "hardware" / "cpu_power.csv"
    tdp: float | None = None
    if ruta.is_file():
        with ruta.open(encoding="utf-8") as archivo:
            next(archivo, None)  # encabezado
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
