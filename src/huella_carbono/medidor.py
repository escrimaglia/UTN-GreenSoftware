# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Las dos vías de medición del consumo energético.

Vía A - `MedidorPropio`: modelo explicable de punta a punta, construido sobre `psutil`.
        Queda implementado y sus resultados se registran en el CSV de la simulación, pero
        el informe no lo desarrolla: sólo lo documenta como la alternativa disponible.

Vía B - `MedidorCodeCarbon`: envoltorio sobre CodeCarbon, la herramienta estándar de la
        industria. **Es la vía que desarrolla el informe**: de acá salen todas sus cifras.
        Lee la potencia del hardware cuando el equipo lo permite y la estima cuando no
        (ver `preferir_lectura_directa`).

Ambos medidores envuelven exactamente la misma ejecución, de modo que sus resultados sean
comparables punto por punto para quien quiera retomar la vía A.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

import psutil

from huella_carbono import config
from huella_carbono.config import MODELO, ModeloPotencia

BYTES_POR_GB = 1024**3
SEGUNDOS_POR_HORA = 3600.0


# ======================================================================================
# Vía A — Medidor propio
# ======================================================================================


@dataclass
class Medicion:
    """Resultado de una ejecución instrumentada."""

    ejecuciones_lote: int  # cuántas ejecuciones se promediaron para obtener este dato
    tiempo_s: float
    cpu_s: float  # segundos de CPU realmente consumidos (user + sys)
    utilizacion: float  # cpu_s / (tiempo_s * n_nucleos), en [0, 1]
    nucleos_activos: float  # cpu_s / tiempo_s: núcleos equivalentes a pleno uso
    memoria_pico_mb: float  # incremento máximo de RSS durante la ejecución
    potencia_media_w: float  # potencia total estimada (incluye consumo basal)
    potencia_marginal_w: float  # potencia atribuible al algoritmo
    energia_total_kwh: float
    energia_atribuible_kwh: float
    co2_total_kg: float
    co2_atribuible_kg: float


class MuestreadorMemoria(threading.Thread):
    """Hilo liviano que registra el pico de RSS durante la ejecución medida."""

    def __init__(self, proceso: psutil.Process, intervalo: float) -> None:
        super().__init__(daemon=True)
        self.proceso = proceso
        self.intervalo = intervalo
        self.evento_detener = threading.Event()
        self.rss_pico = proceso.memory_info().rss

    def run(self) -> None:
        while not self.evento_detener.is_set():
            try:
                self.rss_pico = max(self.rss_pico, self.proceso.memory_info().rss)
            except psutil.Error:  # el proceso desapareció; nada que muestrear
                return
            self.evento_detener.wait(self.intervalo)

    def detener(self) -> None:
        self.evento_detener.set()
        self.join(timeout=1.0)


class MedidorPropio:
    """
    Modelo energético propio.

    Cadena de cálculo, paso a paso:

      1. cpu_s      = Δ(user + sys) de psutil.Process().cpu_times()
      2. u          = cpu_s / (tiempo_s × n_nucleos)              [utilización agregada]
      3. P_total    = P_idle + (P_max − P_idle) × u + RAM_GB × P_ram   [W]
         P_marginal = (P_max − P_idle) × u + ΔRAM_GB × P_ram           [W]
      4. E_kWh      = P × tiempo_s / 3 600 000
      5. CO2_kg     = E_kWh × factor_de_emisión × PUE

    Se reportan dos energías porque responden a preguntas distintas:

      - `energia_total`: cuánta energía consumió la máquina mientras corría el
        algoritmo, incluido el consumo basal del sistema operativo.
      - `energia_atribuible`: cuánta energía adicional causó el algoritmo por existir.
        Es la métrica correcta para comparar algoritmos entre sí, porque el consumo
        basal es el mismo para todos y solo diluiría las diferencias.
    """

    def __init__(self, modelo: ModeloPotencia = MODELO) -> None:
        self.modelo = modelo
        self.proceso = psutil.Process()
        self.nucleos = psutil.cpu_count(logical=True) or 1
        self.linea_base: dict[str, float] | None = None

    # -- línea de base -------------------------------------------------------------

    def medir_linea_base(self, segundos: float = config.SEGUNDOS_LINEA_BASE) -> dict[str, float]:
        """
        Mide el sistema en reposo para poder documentar el consumo basal.

        No se resta de `energia_atribuible` (el modelo ya la excluye por construcción),
        pero sirve para dimensionar cuánto del consumo total es ruido de fondo y para
        detectar si la máquina estaba ocupada con otra cosa al momento de medir.
        """
        psutil.cpu_percent(interval=None)  # descarta la primera lectura, que es basura
        inicio = time.perf_counter()
        time.sleep(segundos)
        transcurrido = time.perf_counter() - inicio
        carga_sistema = psutil.cpu_percent(interval=None) / 100.0
        ram_gb = psutil.virtual_memory().used / BYTES_POR_GB
        potencia = self.modelo.potencia_cpu(carga_sistema) + self.modelo.potencia_ram(ram_gb)
        self.linea_base = {
            "segundos": transcurrido,
            "carga_sistema": carga_sistema,
            "ram_usada_gb": ram_gb,
            "potencia_w": potencia,
            "energia_kwh": potencia * transcurrido / SEGUNDOS_POR_HORA / 1000.0,
        }
        return self.linea_base

    # -- medición ------------------------------------------------------------------

    def calcular_lote(
        self,
        funcion: Callable[[Any], Any],
        entrada: Any,
        ventana_minima_s: float = config.DURACION_MINIMA_LOTE_S,
    ) -> int:
        """
        Determina cuántas ejecuciones meter en un lote para que la ventana medida dure al
        menos `ventana_minima_s`. Sirve además de warm-up: deja cachés e intérprete
        calientes antes de medir en serio.

        La ventana mínima no es la misma en los dos caminos: estimar la potencia sólo exige
        salir de la resolución del reloj, pero leerla del hardware exige que el muestreo
        ocurra mientras el trabajo corre (ver `DURACION_MINIMA_LOTE_MUESTREO_S`).

        El tiempo por ejecución NO se estima con una sola corrida: la primera es mucho más
        lenta que las siguientes —cachés e intérprete fríos, y en NumPy o scikit-learn la
        inicialización interna de la primera llamada—, y extrapolando de ella el lote queda
        muy por debajo de la ventana pedida. Se crece un lote de sondeo hasta que dure lo
        suficiente para ser una medición estable, y de ahí se extrapola.
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

    def medir(
        self, funcion: Callable[[Any], Any], entrada: Any, lote: int = 1
    ) -> tuple[Medicion, Any]:
        """
        Ejecuta `funcion(entrada)` `lote` veces dentro de la región instrumentada y
        devuelve la medición NORMALIZADA POR EJECUCIÓN junto con el último resultado.

        Tiempo, CPU, energía y CO2 se dividen por el tamaño del lote. La utilización y
        las potencias no se dividen: son promedios sobre la ventana, no acumulados.
        """
        muestreador = MuestreadorMemoria(self.proceso, config.INTERVALO_MUESTREO_S)
        rss_inicial = self.proceso.memory_info().rss

        cpu_antes = self.proceso.cpu_times()
        muestreador.start()
        t0 = time.perf_counter()

        resultado = None
        for _ in range(lote):
            resultado = funcion(entrada)

        tiempo_s = time.perf_counter() - t0
        cpu_despues = self.proceso.cpu_times()
        muestreador.detener()

        cpu_s = (cpu_despues.user - cpu_antes.user) + (cpu_despues.system - cpu_antes.system)
        cpu_s = max(0.0, cpu_s)
        tiempo_s = max(tiempo_s, 1e-9)

        nucleos_activos = cpu_s / tiempo_s
        utilizacion = min(1.0, nucleos_activos / self.nucleos)

        delta_rss_gb = max(0.0, muestreador.rss_pico - rss_inicial) / BYTES_POR_GB
        ram_total_gb = psutil.virtual_memory().used / BYTES_POR_GB

        potencia_total = self.modelo.potencia_cpu(utilizacion) + self.modelo.potencia_ram(
            ram_total_gb
        )
        potencia_marginal = self.modelo.potencia_cpu_marginal(
            utilizacion
        ) + self.modelo.potencia_ram(delta_rss_gb)

        energia_total = potencia_total * tiempo_s / SEGUNDOS_POR_HORA / 1000.0
        energia_atribuible = potencia_marginal * tiempo_s / SEGUNDOS_POR_HORA / 1000.0
        factor = config.FACTOR_EMISION_AR * config.PUE

        medicion = Medicion(
            ejecuciones_lote=lote,
            tiempo_s=tiempo_s / lote,
            cpu_s=cpu_s / lote,
            utilizacion=utilizacion,
            nucleos_activos=nucleos_activos,
            memoria_pico_mb=delta_rss_gb * 1024.0,
            potencia_media_w=potencia_total,
            potencia_marginal_w=potencia_marginal,
            energia_total_kwh=energia_total / lote,
            energia_atribuible_kwh=energia_atribuible / lote,
            co2_total_kg=energia_total * factor / lote,
            co2_atribuible_kg=energia_atribuible * factor / lote,
        )
        return medicion, resultado


# ======================================================================================
# Vía B — CodeCarbon
# ======================================================================================


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
        for _ in range(lote):
            funcion(entrada)
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
            "tiempo_s": datos.duration / lote,
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


# ======================================================================================
# Calibración opcional del modelo propio con powermetrics
# ======================================================================================


def leer_potencia_powermetrics(muestras: int = 5, intervalo_ms: int = 200) -> float | None:
    """
    Lee la potencia real del paquete del SoC con `powermetrics` (requiere sudo).

    Devuelve la potencia media en W, o None si no se puede leer.
    """
    if platform.system() != "Darwin" or shutil.which("powermetrics") is None:
        return None
    try:
        salida = subprocess.run(
            [
                "sudo", "-n", "powermetrics",
                "--samplers", "cpu_power",
                "-n", str(muestras),
                "-i", str(intervalo_ms),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if salida.returncode != 0:
        return None

    # powermetrics informa, según la versión, "CPU Power: 1234 mW" o "Package Power".
    valores = [float(v) for v in re.findall(r"CPU Power:\s+([\d.]+)\s*mW", salida.stdout)]
    if not valores:
        valores = [
            float(v) * 1000 for v in re.findall(r"Package Power:\s+([\d.]+)\s*W", salida.stdout)
        ]
    if not valores:
        return None
    return sum(valores) / len(valores) / 1000.0  # mW -> W


# Código que ejecuta cada proceso de carga durante la calibración. Se lanza con
# `sys.executable -c`, en lugar de con `multiprocessing`, para no depender de que el módulo
# `__main__` del proceso padre sea reimportable: con el método `spawn` de macOS, un
# `multiprocessing.Process` falla si el padre se ejecutó desde stdin o desde un entrypoint
# que no se puede volver a importar.
CODIGO_CARGA = (
    "import time\n"
    "limite = time.perf_counter() + {segundos}\n"
    "x = 0\n"
    "while time.perf_counter() < limite:\n"
    "    for _ in range(100000):\n"
    "        x += 1\n"
)


def lanzar_carga_total(segundos: float) -> list[subprocess.Popen[bytes]]:
    """
    Lanza un proceso por núcleo lógico, cada uno ocupando su núcleo con cómputo entero.

    Tienen que ser PROCESOS y no hilos: un bucle de Python puro en varios hilos queda
    serializado por el GIL, así que sólo se satura un núcleo. Medido en este equipo: con
    hilos la carga del sistema llega al 10,7% (≈ 1 de 12 núcleos) y con procesos al 99%.
    Con hilos, el `P_max` calibrado terminaba siendo la potencia de un núcleo.
    """
    codigo = CODIGO_CARGA.format(segundos=segundos)
    return [
        subprocess.Popen(
            [sys.executable, "-c", codigo],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(psutil.cpu_count() or 1)
    ]


def detener_carga(procesos: list[subprocess.Popen[bytes]]) -> None:
    """Termina los procesos de carga, con `kill` como respaldo si no responden."""
    for proceso in procesos:
        proceso.terminate()
    for proceso in procesos:
        try:
            proceso.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proceso.kill()


def calibrar_modelo(segundos_carga: float = 4.0) -> dict[str, Any]:
    """
    Calibra `P_idle` y `P_max` midiendo la potencia real del chip con powermetrics.

    Requiere que `sudo` esté disponible sin pedir contraseña interactiva. Si no lo está,
    devuelve un diccionario indicando que se conservan los valores de referencia; el
    informe deja constancia de cuál de los dos caminos se usó.
    """
    p_idle = leer_potencia_powermetrics()
    if p_idle is None:
        return {
            "disponible": False,
            "motivo": (
                "powermetrics requiere privilegios de root. Ejecutar previamente "
                "`sudo -v` en la terminal y volver a correr con --calibrar."
            ),
            "modelo": asdict(MODELO),
        }

    # Satura todos los núcleos con PROCESOS y mide la potencia bajo carga.
    #
    # Tienen que ser procesos y no hilos: un bucle de Python puro en varios hilos queda
    # serializado por el GIL, así que sólo se satura un núcleo y la potencia medida es la de
    # un núcleo, no la del chip entero. Con `multiprocessing` cada trabajador tiene su propio
    # intérprete y su propio GIL, y la carga sí ocupa todos los núcleos.
    nucleos = psutil.cpu_count() or 1
    procesos = lanzar_carga_total(segundos_carga + 4.0)
    time.sleep(1.5)  # deja que arranquen los intérpretes y que la carga se estabilice

    carga = psutil.cpu_percent(interval=0.5)  # para poder declarar si la saturación ocurrió
    p_max = leer_potencia_powermetrics(muestras=int(segundos_carga * 5))
    detener_carga(procesos)

    if p_max is None:
        return {"disponible": False, "motivo": "no se pudo leer bajo carga", "modelo": asdict(MODELO)}

    if p_max <= p_idle * 2:
        # Si la potencia bajo carga no se despega de la de reposo, la calibración no midió
        # lo que cree: mejor conservar los valores de referencia que publicar un modelo con
        # un P_max de un solo núcleo.
        return {
            "disponible": False,
            "motivo": (
                f"la potencia bajo carga ({p_max:.3f} W) no se despega de la de reposo "
                f"({p_idle:.3f} W); la carga no llegó a saturar el chip"
            ),
            "modelo": asdict(MODELO),
        }

    MODELO.p_idle_w = round(p_idle, 3)
    MODELO.p_max_w = round(p_max, 3)
    MODELO.origen = "powermetrics"
    MODELO.carga_calibracion_pct = round(carga, 1)
    return {
        "disponible": True,
        "modelo": asdict(MODELO),
        "carga_durante_calibracion": round(carga, 1),
        "nucleos_saturados": nucleos,
    }
