# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Parámetros del modelo energético y de emisiones.

Todo número usado por el proyecto vive acá, con su fuente y su justificación.
El objetivo es que el modelo sea auditable: no hay constantes mágicas escondidas
dentro de la lógica de medición.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------
# Rutas del proyecto
# --------------------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parents[2]
DIR_RESULTADOS = RAIZ / "resultados"
DIR_GRAFICOS = DIR_RESULTADOS / "graficos"
# Un único CSV de resultados: es el entregable de la simulación. Contiene una fila por
# repetición medida, que es el grano más fino; las medias y desvíos que usa el informe se
# derivan de acá en memoria, para no versionar dos veces la misma información.
CSV_SIMULACION = DIR_RESULTADOS / "simulacion_huella_carbono.csv"
INFORME = RAIZ / "INFORME.md"


# --------------------------------------------------------------------------------------
# Factor de emisión de la red eléctrica
# --------------------------------------------------------------------------------------

# Intensidad de carbono de la red eléctrica argentina, en kgCO2eq por kWh.
#
# Se usa el dato MÁS RECIENTE disponible para Argentina. Ningún valor está escrito a
# mano: se lee en tiempo de ejecución de `datos/intensidad_carbono_argentina.json`, que
# versiona la serie completa publicada por Our World in Data a partir de los datos
# anuales de Ember, y se toma automáticamente el último año de la serie.
#
# Por qué no se usa el valor interno de CodeCarbon: su dataset
# (`codecarbon/data/private_infra/global_energy_mix.json`) está congelado en 2023 para
# Argentina (354,103 gCO2eq/kWh) incluso en la última versión publicada de la librería.
# Ese valor se sigue leyendo acá, pero sólo como referencia para el informe y para poder
# declarar explícitamente la diferencia.

PAIS_ISO = "ARG"
DIR_DATOS = RAIZ / "datos"
ARCHIVO_INTENSIDAD_CARBONO = DIR_DATOS / "intensidad_carbono_argentina.json"


def cargar_serie_intensidad_carbono() -> dict[str, Any]:
    """Lee la serie de intensidad de carbono de la red argentina versionada en el repo."""
    if not ARCHIVO_INTENSIDAD_CARBONO.is_file():
        raise RuntimeError(
            f"Falta el dataset de intensidad de carbono en {ARCHIVO_INTENSIDAD_CARBONO}. "
            "Es un archivo versionado con el proyecto; no debería faltar."
        )
    with ARCHIVO_INTENSIDAD_CARBONO.open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    if not datos.get("serie_g_kwh"):
        raise RuntimeError(
            f"{ARCHIVO_INTENSIDAD_CARBONO.name} no tiene la clave 'serie_g_kwh' con datos."
        )
    return datos


def factor_emision_mas_reciente(serie: dict[str, float]) -> tuple[int, float]:
    """Devuelve (año, gCO2eq/kWh) del año más reciente de la serie."""
    anio = max(int(a) for a in serie)
    return anio, float(serie[str(anio)])


def ruta_dataset_emisiones() -> Path:
    """
    Ubica el JSON de matrices eléctricas dentro del paquete `codecarbon` instalado.

    Se resuelve con `find_spec` en lugar de `import codecarbon` porque importar el
    paquete completo es costoso (arrastra sus dependencias) y acá sólo se necesita
    la ruta de un archivo de datos.
    """
    spec = find_spec("codecarbon")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError(
            "No se encuentra el paquete `codecarbon` en el entorno. "
            "Instalar las dependencias del proyecto (`uv sync`)."
        )
    raiz_paquete = Path(next(iter(spec.submodule_search_locations)))
    return raiz_paquete / "data" / "private_infra" / "global_energy_mix.json"


def cargar_matriz_electrica(iso: str = PAIS_ISO) -> dict[str, Any]:
    """Devuelve el registro de matriz eléctrica de un país tal como lo trae CodeCarbon."""
    ruta = ruta_dataset_emisiones()
    if not ruta.is_file():
        raise RuntimeError(
            f"El dataset de matrices eléctricas de CodeCarbon no está en {ruta}. "
            "Puede haber cambiado de ubicación en esta versión de CodeCarbon."
        )
    with ruta.open(encoding="utf-8") as archivo:
        datos = json.load(archivo)
    if iso not in datos:
        raise KeyError(f"El dataset de CodeCarbon no tiene la clave de país '{iso}'.")
    return datos[iso]


# --- factor de emisión efectivamente usado en todos los cálculos del proyecto ---
INTENSIDAD_CARBONO = cargar_serie_intensidad_carbono()
ANIO_FACTOR_EMISION, FACTOR_EMISION_AR_G_KWH = factor_emision_mas_reciente(
    INTENSIDAD_CARBONO["serie_g_kwh"]
)
FACTOR_EMISION_AR = FACTOR_EMISION_AR_G_KWH / 1000.0  # kgCO2eq/kWh
FUENTE_FACTOR_EMISION = INTENSIDAD_CARBONO["fuente"]

# Factor oficial de la Secretaría de Energía, citado en el informe sólo como contraste
# metodológico (es un factor marginal estilo UNFCCC, no una intensidad media de la red).
# Vive en el mismo archivo de datos para que ninguna cifra del informe esté escrita a mano.
REFERENCIA_FACTOR_OFICIAL = INTENSIDAD_CARBONO.get("referencia_factor_oficial", {})

# --- valor interno de CodeCarbon, sólo como referencia y contraste en el informe ---
REGISTRO_PAIS = cargar_matriz_electrica()
FACTOR_EMISION_CODECARBON_G_KWH = float(REGISTRO_PAIS["carbon_intensity"])
ANIO_FACTOR_EMISION_CODECARBON = int(REGISTRO_PAIS["year"])

# Contexto de la matriz eléctrica argentina (registro de CodeCarbon), usado en el marco
# teórico del informe. El año es el que declara el propio dataset, no una suposición: es
# el último año con desglose por fuente disponible, y puede ser anterior al año del
# factor de emisión usado en los cálculos.
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


# PUE (Power Usage Effectiveness): factor que en un datacenter contabiliza la energía
# de refrigeración e infraestructura además de la del cómputo.
# Acá el experimento corre en una notebook sobre un escritorio, sin infraestructura de
# refrigeración externa, por lo que PUE = 1.0. Se deja explícito porque si el mismo
# código corriera en un datacenter habría que multiplicar por 1.1 - 1.6.
PUE = 1.0


# --------------------------------------------------------------------------------------
# Modelo de potencia del hardware
# --------------------------------------------------------------------------------------


# El modelo de potencia propio se describe en el informe (§3.3) como una opción de
# cálculo, pero el proyecto no lo implementa: la medición es de CodeCarbon.


# --------------------------------------------------------------------------------------
# Parámetros del benchmark
# --------------------------------------------------------------------------------------

SEMILLA = 42  # semilla fija: todos los algoritmos reciben exactamente la misma entrada
REPETICIONES = 3  # cada (algoritmo, n) se corre R veces -> media y desvío estándar

# Medición por lotes.
#
# Los algoritmos eficientes son tan rápidos que una sola ejecución cae por debajo de la
# resolución de las herramientas de medición: `psutil.cpu_times()` tiene granularidad del
# orden de los 10 ms en macOS y `timsort_nativo` sobre n=1000 tarda ~1 ms. Medir eso
# directamente daría utilizaciones de 0 o de 1 según el redondeo, no un dato.
#
# Solución estándar (la misma que usa el módulo `timeit` de la biblioteca estándar):
# ejecutar el algoritmo K veces dentro de la región medida, con K autoajustado para que
# el lote dure al menos DURACION_MINIMA_LOTE_S, y luego dividir por K. Así toda medición
# se toma sobre una ventana temporal suficientemente grande.
DURACION_MINIMA_LOTE_S = 0.5
# Cuando la potencia se LEE del hardware hace falta una ventana mucho más larga, porque el
# muestreo tiene que caer DENTRO del trabajo. Medido en este equipo: la lectura agrega un
# sobrecosto fijo de unos 1,95 s por medición (se toma al cerrar la tarea), así que el
# inflado de la duración informada es 5,7x con ventanas de 0,4 s, 2,4x con 1,4 s y 1,65x
# con 3 s. Se adoptan 3 s como compromiso entre exactitud y duración de la corrida.
DURACION_MINIMA_LOTE_MUESTREO_S = 3.0

# Tope de ejecuciones por lote. Es una red de seguridad contra un sondeo no representativo
# (si la corrida de prueba midiera casi cero, K se iría al infinito), no un límite de
# diseño: el tamaño del lote lo gobierna la ventana temporal. Tiene que dar holgura para
# llegar a la ventana con los algoritmos más rápidos del proyecto: `fib_iterativo` corre en unos
# 450 ns, así que necesita del orden de 7 millones de ejecuciones para cubrir 3 s. Con un
# tope bajo, justamente los algoritmos más eficientes de cada experimento medirían sobre
# ventanas cortas y su energía saldría inflada respecto de la de sus alternativas, que es
# el sesgo que arruinaría la comparación.
MAX_EJECUCIONES_LOTE = 10_000_000

# Duración del lote de sondeo con el que se estima el tiempo por ejecución antes de fijar K.
# 10 ms alcanzan para promediar el ruido del reloj y son despreciables frente a la ventana.
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
    variantes: dict[str, str] = field(default_factory=dict)  # algoritmo -> complejidad
    # Qué hace cada variante, en lenguaje llano y en tres líneas como máximo: el informe lo
    # inserta antes del gráfico de cada experimento, para que se entienda qué se comparó.
    descripciones: dict[str, str] = field(default_factory=dict)
    # Escalas con las que §5.3 extrapola las emisiones de este experimento. El default
    # (un millón y mil millones de ejecuciones) tiene sentido para una función invocada por
    # un servicio; para un entrenamiento de modelo no, y cada experimento puede declarar las
    # suyas: lista de (multiplicador, descripción).
    escalas: list[tuple[int, str]] | None = None


EXPERIMENTOS: dict[str, Experimento] = {
    "ordenamiento": Experimento(
        clave="ordenamiento",
        titulo="Algoritmos de ordenamiento",
        pregunta=(
            "¿La complejidad computacional se traduce en una diferencia medible de "
            "emisiones cuando el resultado producido es idéntico?"
        ),
        tamanios_completo=[1000, 2000, 4000, 8000],
        tamanios_rapido=[500, 1000],
        unidad_n="cantidad de elementos",
        notas=(
            "Las tres variantes ordenan exactamente la misma lista de enteros "
            "generada con semilla fija y devuelven el mismo resultado."
        ),
        variantes={
            "bubble_sort": "O(n²)",
            "merge_sort": "O(n log n)",
            "timsort_nativo": "O(n log n) en C",
        },
        descripciones={
            "bubble_sort": (
                "Compara elementos vecinos y los intercambia si están desordenados, y "
                "repite el recorrido hasta que no queda ningún intercambio por hacer. Es el "
                "método más simple de escribir y el que más trabajo hace."
            ),
            "merge_sort": (
                "Parte la lista en mitades hasta quedarse con elementos sueltos y después "
                "las va uniendo de a pares, ya ordenadas. Escrito en Python."
            ),
            "timsort_nativo": (
                "El ordenamiento que trae Python de fábrica, escrito en C. Usa la misma idea "
                "de unir mitades ordenadas, pero además detecta y aprovecha los tramos que "
                "ya venían en orden."
            ),
        },
    ),
    "fibonacci": Experimento(
        clave="fibonacci",
        titulo="Cálculo de Fibonacci",
        pregunta=(
            "¿Cuánto cuesta ambientalmente recalcular trabajo ya hecho? "
            "Comparación entre crecimiento exponencial y lineal."
        ),
        tamanios_completo=[20, 25, 30, 32],
        tamanios_rapido=[18, 22],
        unidad_n="término n de la sucesión",
        notas=(
            "Se acota en n=32 porque la variante recursiva ingenua crece de forma "
            "exponencial y dominaría el tiempo total del benchmark."
        ),
        variantes={
            "fib_recursivo": "O(φⁿ)",
            "fib_memoizado": "O(n)",
            "fib_iterativo": "O(n)",
        },
        descripciones={
            "fib_recursivo": (
                "Para obtener un término suma los dos anteriores, y para cada uno de ellos "
                "vuelve a empezar de cero, sin recordar nada. Termina recalculando los "
                "mismos valores una cantidad enorme de veces."
            ),
            "fib_memoizado": (
                "Hace lo mismo, pero anota cada resultado la primera vez que lo calcula y "
                "después lo reutiliza en lugar de volver a calcularlo."
            ),
            "fib_iterativo": (
                "Recorre la sucesión una sola vez, de abajo hacia arriba, guardando "
                "únicamente los dos últimos valores."
            ),
        },
    ),
    "matrices": Experimento(
        clave="matrices",
        titulo="Multiplicación de matrices",
        pregunta=(
            "A igual complejidad algorítmica O(n³), ¿cuánto pesa ambientalmente la "
            "elección de la implementación (Python puro contra una biblioteca numérica optimizada)?"
        ),
        tamanios_completo=[100, 200, 300],
        tamanios_rapido=[60, 100],
        unidad_n="dimensión n de la matriz n×n",
        notas=(
            "Ambas variantes resuelven el mismo producto con la misma complejidad "
            "asintótica. La diferencia de huella es puro costo de implementación."
        ),
        variantes={
            "matmul_python": "O(n³) en Python",
            "matmul_numpy": "O(n³) vectorizado",
        },
        descripciones={
            "matmul_python": (
                "Multiplica las matrices elemento por elemento, con tres bucles anidados "
                "escritos en Python. Cada operación pasa por el intérprete."
            ),
            "matmul_numpy": (
                "Delega la misma multiplicación a una biblioteca numérica compilada, que "
                "opera sobre bloques de datos a la vez en lugar de número por número."
            ),
        },
    ),
    "aprendizaje_knn": Experimento(
        clave="aprendizaje_knn",
        titulo="Entrenamiento e inferencia de un modelo de ML (KNN)",
        pregunta=(
            "A igual resultado predictivo exacto, ¿cuánto cambia la huella según la "
            "implementación de la búsqueda de vecinos, y qué pasa cuando una de ellas usa "
            "todos los núcleos en lugar de uno?"
        ),
        tamanios_completo=[2500, 5000, 10000, 20000],
        tamanios_rapido=[2000, 4000],
        unidad_n="muestras del dataset",
        notas=(
            "El modelo es un **clasificador de vecinos más cercanos**, que no deduce ninguna "
            "regla: para decidir a qué categoría pertenece un dato nuevo, busca los 31 datos "
            "más parecidos entre los que ya conoce y le asigna la categoría que predomina "
            "entre esos 31. «Parecido» quiere decir cercano, midiendo la distancia entre las "
            "20 características que describen a cada dato.\n\n"
            "Lo costoso es justamente encontrar esos 31 vecinos entre miles de datos, y es "
            "ahí donde se diferencian las tres variantes. Se mide el entrenamiento y la "
            "clasificación como una sola unidad de trabajo, y las tres devuelven exactamente "
            "las mismas predicciones."
        ),
        variantes={
            "knn_brute": "O(n·m·d) vectorizado",
            "knn_kd_tree": "O(n·d) + O(n log n)",
            "knn_ball_tree": "O(n·d) + O(n log n)",
        },
        descripciones={
            "knn_brute": (
                "Mide la distancia del dato nuevo contra todos los datos conocidos, uno por "
                "uno, y se queda con los 31 más cercanos. No descarta nada, pero hace esas "
                "cuentas de a bloques y reparte el trabajo entre todos los núcleos."
            ),
            "knn_kd_tree": (
                "Antes de clasificar, acomoda los datos conocidos dividiendo el espacio con "
                "cortes rectos, como una grilla irregular. Al buscar los vecinos descarta de "
                "golpe las zonas que quedaron lejos, en lugar de recorrer dato por dato."
            ),
            "knn_ball_tree": (
                "Hace lo mismo que `knn_kd_tree` —descartar zonas enteras en vez de recorrer "
                "todo—, pero agrupando los datos conocidos en burbujas en lugar de cortarlos "
                "con líneas rectas. Usa un solo núcleo."
            ),
        },
        # El ajuste del informe se hace sobre CO2, no sobre tiempo, y para este experimento
        # los dos no coinciden. El trabajo es O(n·m·d) con m = 0,2·n, o sea cuadrático en n
        # para las tres variantes: la construcción O(n log n) de los árboles no domina porque
        # en 20 dimensiones la consulta deja de podar (maldición de la dimensionalidad).
        # `brute` reparte ese trabajo cuadrático entre todos los núcleos, así que su TIEMPO
        # crece más despacio, pero la energía cuenta núcleo-segundos y su exponente de CO2
        # vuelve a acercarse a 2.
        escalas=[
            (365, "un reentrenamiento diario durante un año"),
            (8_760, "un reentrenamiento por hora durante un año"),
        ],
    ),
}


# --------------------------------------------------------------------------------------
# Equivalencias para traducir kgCO2eq a magnitudes tangibles
# --------------------------------------------------------------------------------------

# Se leen de `datos/equivalencias_co2.json` en tiempo de ejecución. Las equivalencias
# eléctricas se guardan como CONSUMO en kWh y se convierten con FACTOR_EMISION_AR, para
# que no puedan quedar desfasadas del factor de emisión vigente. Las directas guardan su
# valor con la fuente y la URL de donde sale.

ARCHIVO_EQUIVALENCIAS = DIR_DATOS / "equivalencias_co2.json"


def cargar_equivalencias() -> tuple[list[tuple[str, float, str]], dict[str, Any]]:
    """
    Devuelve las equivalencias como (nombre, kgCO2eq por unidad, fuente) y el crudo.

    El crudo se devuelve además para que el informe pueda citar URLs y fechas de consulta.
    """
    if not ARCHIVO_EQUIVALENCIAS.is_file():
        raise RuntimeError(
            f"Falta el archivo de equivalencias en {ARCHIVO_EQUIVALENCIAS}. "
            "Es un archivo versionado con el proyecto; no debería faltar."
        )
    with ARCHIVO_EQUIVALENCIAS.open(encoding="utf-8") as archivo:
        crudo = json.load(archivo)

    lista: list[tuple[str, float, str]] = []
    for item in crudo.get("directas", []):
        lista.append((item["nombre"], float(item["kg_co2_por_unidad"]), item["fuente"]))
    for item in crudo.get("vehiculares", []):
        # kgCO2/km = (L/100 km ÷ 100) × kgCO2/L. Los dos términos son datos argentinos.
        consumo = float(item["consumo_l_por_100km"])
        factor_combustible = float(item["factor_kg_co2_por_litro"])
        consumo_txt = f"{consumo:.1f}".replace(".", ",")
        combustible_txt = f"{factor_combustible:.4f}".replace(".", ",")
        fuente = (
            f"{consumo_txt} L/100 km (consumo medio de vehículos livianos en Argentina) × "
            f"{combustible_txt} kgCO₂/L ({item['combustible']})"
        )
        lista.append((item["nombre"], consumo / 100 * factor_combustible, fuente))
    for item in crudo.get("electricas", []):
        consumo = float(item["consumo_kwh"])
        detalle = item["detalle"]
        # coma decimal, igual que el resto del informe
        consumo_txt = f"{consumo:.3f}".replace(".", ",")
        factor_txt = f"{FACTOR_EMISION_AR:.3f}".replace(".", ",")
        fuente = (
            f"{detalle[:1].upper()}{detalle[1:]}: {consumo_txt} kWh × "
            f"{factor_txt} kgCO₂eq/kWh (FE {ANIO_FACTOR_EMISION})"
        )
        lista.append((item["nombre"], consumo * FACTOR_EMISION_AR, fuente))
    return lista, crudo


EQUIVALENCIAS, EQUIVALENCIAS_CRUDO = cargar_equivalencias()
