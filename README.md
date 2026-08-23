# Huella de carbono de algoritmos en Python

Green Software — Universidad Tecnológica Nacional - FRC.

## Qué es

Un banco de pruebas que **mide la energía consumida y el CO₂ emitido al ejecutar
algoritmos**, y genera un informe con los resultados.

No estima a partir de una tabla ni de un modelo teórico: corre los algoritmos en el
equipo, lee el consumo real del procesador mientras trabajan y lo convierte a emisiones
con el factor de la red eléctrica argentina.

## De qué se trata

La pregunta que responde es: **¿la complejidad computacional tiene una consecuencia
ambiental medible?**

Para responderla compara variantes que resuelven **exactamente el mismo problema y
devuelven el mismo resultado** —verificado por aserción antes de cada medición—, de modo
que la única diferencia entre ellas sea cómo llegan a ese resultado. Si un algoritmo
emite mil veces más que otro para producir lo mismo, la diferencia es atribuible a la
decisión de diseño y a nada más.

Son cuatro experimentos, cada uno con una pregunta propia:

| Experimento | Qué pone a prueba | Variantes |
|---|---|---|
| `ordenamiento` | complejidad: O(n²) contra O(n log n) | `bubble_sort`, `merge_sort`, `timsort_nativo` |
| `fibonacci` | el costo de recalcular trabajo ya hecho | `fib_recursivo`, `fib_memoizado`, `fib_iterativo` |
| `matrices` | a igual complejidad, cuánto pesa la implementación | `matmul_python`, `matmul_numpy` |
| `aprendizaje_knn` | el efecto del paralelismo, entrenando un modelo real | `knn_brute`, `knn_kd_tree`, `knn_ball_tree` |

Diferencia de emisiones entre la mejor y la peor variante de cada experimento, en su
tamaño más grande. Se informa la potencia de diez inmediatamente inferior al factor
medido, para que este README no quede desincronizado al volver a medir:

| Experimento | Diferencia de emisiones |
|---|---|
| Ordenamiento | más de 10³× |
| Fibonacci | más de 10⁵× |
| Matrices | más de 10²× |
| KNN | más de 10¹× |

Las cifras exactas de la última corrida están en [`INFORME.md`](INFORME.md).

## Para qué se usa

- **Para sostener con mediciones un argumento que suele darse por sentado.** "Elegir bien
  el algoritmo ahorra energía" es una afirmación verificable, y este proyecto la verifica
  en lugar de repetirla.
- **Para traducir emisiones a magnitudes comprensibles.** El informe extrapola cada
  algoritmo a escalas reales de uso y expresa el resultado en kilómetros de auto y cargas
  de teléfono, no sólo en microgramos de CO₂.
- **Para mostrar cuánto depende una medición de huella del método con que se hizo.** El
  mismo banco de pruebas da valores absolutos distintos según si la potencia se midió o se
  estimó, y el informe declara con cuál de los dos caminos obtuvo los suyos en lugar de
  presentar el número como si fuera único.
- **Como base para medir otro código.** La estructura —verificar equivalencia, medir por
  lotes, repetir, informar dispersión— sirve para cualquier comparación de huella, no sólo
  para estos algoritmos.

## Cómo se usa

### Instalación

```bash
uv sync        # instala el entorno exacto desde uv.lock
```

Requiere Python 3.12 y [uv](https://docs.astral.sh/uv/).

**El proyecto es agnóstico de plataforma:** corre en macOS, Linux y Windows sin cambiar
nada. Ninguna parte del banco de pruebas está atada a un sistema operativo —no hay código
que se elija según el sistema— y lo único que se adapta es de dónde sale la potencia, que
se resuelve en cada corrida preguntándole al equipo qué ofrece. Donde no hay lectura
disponible, se estima y se deja constancia. La única función condicionada al sistema es la
calibración opcional de la vía A (`--calibrar`), que fuera de macOS informa que no está
disponible y conserva los valores de referencia en lugar de fallar.

Corrido y verificado en macOS con Apple Silicon; en Linux y Windows no se verificó.

### Correr el banco de pruebas

```bash
uv run huella-carbono --completo   # los 4 experimentos, todos los tamaños (~12 min)
uv run huella-carbono --rapido     # los 4 experimentos con tamaños reducidos (~6 min)
```

`--completo` es el modo por defecto: `uv run huella-carbono` sin argumentos hace lo mismo.
Cada corrida sobrescribe `resultados/` e `INFORME.md`.

Los tiempos son aproximados y los domina la ventana de medición, no el trabajo de los
algoritmos: leer la potencia del hardware exige al menos 3 s por punto, y son 42
configuraciones en el modo completo y 22 en el rápido. Cuando la potencia se estima en
lugar de medirse basta con 0,5 s y la corrida completa baja a unos 2,5 min.

### Medir la potencia en lugar de estimarla

Es la decisión que más afecta a los resultados, y es también lo que hace al proyecto
independiente de la plataforma: en lugar de asumir un sistema operativo, **lee la potencia
real del procesador siempre que el equipo lo permita y sólo la estima cuando no**. La
corrida nunca falla por esto; lo que cambia es la calidad del dato, y el informe lo
declara.

| Plataforma | Cómo se lee la potencia | Requisito | Verificado |
|---|---|---|---|
| macOS con Apple Silicon | utilidad de consumo del sistema | `sudo` disponible | sí, en este equipo |
| Linux | contadores del procesador | ninguno | no probado |
| Windows 11 | medidor de energía del sistema | equipo físico, no virtualizado | no probado |
| cualquiera, si no hay lectura | se estima a partir de la carga | — | sí, en este equipo |

Las dos filas marcadas «no probado» son lo que la herramienta de medición intenta en esas
plataformas según su documentación; este proyecto sólo se corrió en macOS.

En macOS hay que autorizar `sudo` en la misma terminal antes de correr:

```bash
sudo -v
uv run huella-carbono --completo
```

Sin eso, la corrida no falla: cae a la estimación, lo deja registrado en
`resultados/metadatos.json` y el informe declara cuál de los dos caminos se usó. La
diferencia importa: con estimación, los valores absolutos se calculan a partir de un
consumo nominal genérico de 85 W, propio de una computadora de escritorio.

### Correr un experimento en particular

`--solo` acepta uno o varios de los cuatro nombres:

```bash
uv run huella-carbono --completo --solo ordenamiento
uv run huella-carbono --completo --solo matrices aprendizaje_knn
uv run huella-carbono --rapido   --solo aprendizaje_knn
```

| Clave | Tamaños en `--completo` |
|---|---|
| `ordenamiento` | 1.000 → 8.000 elementos |
| `fibonacci` | n = 20 → 32 |
| `matrices` | matrices de 100×100 → 300×300 |
| `aprendizaje_knn` | 2.500 → 20.000 muestras |

**Atención:** una corrida con `--solo` reescribe `resultados/` e `INFORME.md` con
*únicamente* esos experimentos, y no hay deshacer. Si los resultados actuales importan,
copiarlos antes.

### Otras opciones

```bash
uv run huella-carbono --repeticiones 5    # repeticiones por punto (por defecto 3)
uv run huella-carbono --solo-informe      # regenera gráficos e informe sin volver a medir
uv run huella-carbono --calibrar          # calibra el modelo de potencia de la vía A
uv run huella-carbono --help
```

`--solo-informe` no mide: relee `resultados/simulacion_huella_carbono.csv` y regenera los
gráficos y el informe. Es lo que hay que usar después de tocar el código del informe.

`--calibrar` mide la potencia en reposo y con todos los núcleos saturados, para el modelo
de la vía A que se describe abajo. Satura el chip con un proceso por núcleo —no con hilos,
que el GIL serializaría dejando activo uno solo— y si la potencia bajo carga no se despega
de la de reposo, descarta la calibración y conserva los valores de referencia.

### Qué produce

| Salida | Contenido |
|---|---|
| `INFORME.md` | el informe completo: metodología, resultados, análisis, limitaciones y fuentes |
| `resultados/simulacion_huella_carbono.csv` | una fila por medición, con tiempo, energía y CO₂ |
| `resultados/metadatos.json` | equipo, versiones y parámetros con que se corrió |
| `resultados/graficos/*.png` | los cinco gráficos que embebe el informe |

Ninguna cifra del informe está escrita a mano: todas se derivan del CSV medido, así que el
reporte no puede quedar desincronizado de los datos.

## El CSV de resultados

`resultados/simulacion_huella_carbono.csv` es el exportable del proyecto: el registro
crudo de lo que se midió. El informe es su lectura; el CSV es la evidencia.

**Por qué existe y por qué es uno solo.** Una medición que no se puede auditar no vale
como medición: cualquier cifra del informe tiene que poder rastrearse hasta el dato que la
originó. Por eso se guarda el grano más fino —cada medición individual, sin promediar— y
todo lo demás se deriva de ahí en el momento de generar el informe. Guardar además una
tabla de promedios sería versionar dos veces la misma información y abrir la puerta a que
las dos versiones se contradigan. También queda como insumo para analizarlo por fuera del
proyecto, con una planilla o con cualquier herramienta de datos.

**Qué contiene.** Una fila por medición y 21 columnas. En una corrida completa son 126
filas: 42 configuraciones —cada combinación de algoritmo y tamaño— por 3 repeticiones.

| Grupo de columnas | Contenido |
|---|---|
| Identificación | experimento, algoritmo, su complejidad teórica, tamaño `n`, número de repetición y cuántas ejecuciones entraron en el lote medido |
| Tiempo y recursos | segundos transcurridos, segundos de procesador consumidos, utilización, núcleos activos y memoria pico |
| Vía B — CodeCarbon | duración, energía en kWh, CO₂ en kg, el CO₂ que la herramienta calcularía con su propio factor de emisión, y la potencia de procesador registrada. **Es la vía que usa el informe.** |
| Vía A — medidor propio | potencia atribuida, energía y CO₂ del algoritmo, y los mismos valores incluyendo el consumo basal de la máquina. Se registran para quien quiera retomar esta vía; el informe no los usa. |

Que estén las dos vías permite recalcular el informe por cualquiera de las dos sin volver
a medir, y comparar una contra otra si hiciera falta.

## Cómo funciona

El proyecto implementa **dos vías de medición** sobre exactamente el mismo trabajo. El
informe **desarrolla la vía B (CodeCarbon)**: todas sus cifras salen de ahí. La vía A queda
implementada y sus columnas se registran en el CSV, pero el informe sólo la documenta como
la alternativa disponible.

**Vía B — CodeCarbon**, la herramienta estándar de la industria, en modo offline con el
factor de emisión de Argentina. Es la vía desarrollada.

**Vía A — medidor propio** (`medidor.py`), no desarrollada. Modelo auditable paso a paso:

```
cpu_s      = Δ(user + sys) de psutil.Process().cpu_times()
u          = cpu_s / (tiempo_s × n_núcleos)
P_marginal = (P_max − P_idle) × u  +  ΔRAM_GB × P_ram
E [kWh]    = P × tiempo_s / 3 600 000
CO₂ [kg]   = E × FE × PUE
```

Decisiones metodológicas que sostienen los resultados:

- **Verificación de equivalencia.** Antes de medir se comprueba que todas las variantes
  devuelvan el mismo resultado. Comparar la huella de algoritmos que no resuelven lo mismo
  no tendría validez.
- **Medición por lotes.** Varios algoritmos terminan en microsegundos, mucho menos de lo
  que tarda cualquier lectura de consumo. Se ejecutan K veces dentro de la ventana medida
  y se divide por K, con K calibrado por una corrida de prueba previa. La ventana mínima
  depende de la fuente de potencia: 3 s si se lee del hardware, 0,5 s si se estima.
- **Repeticiones.** Cada punto se mide 3 veces y se informan media y dispersión. En la
  última corrida la dispersión mediana fue del 1,4%.
- **Factor de emisión al día.** Se lee en cada corrida del último año disponible de la
  serie argentina versionada en `datos/`, en lugar del valor de 2023 que trae CodeCarbon.
- **Un solo CSV.** Los promedios y desvíos se derivan en memoria, para no versionar dos
  veces la misma información.

## Estructura

```
src/huella_carbono/
├── config.py       parámetros del modelo energético, cada uno con su fuente
├── algoritmos.py   las implementaciones clásicas y la verificación de equivalencia
├── ml.py           el experimento de KNN (scikit-learn), en módulo aparte para no
│                   pagar el costo de importar sklearn cuando no se usa
├── medidor.py      las dos vías de medición + calibración de la vía A
├── benchmark.py    orquestación y volcado al CSV
├── graficos.py     los 5 gráficos del informe
├── informe.py      genera INFORME.md a partir del CSV
└── main.py         interfaz de línea de comandos

datos/              entradas versionadas, no generadas: factor de emisión de la red
                    argentina y factores de equivalencia, cada uno con su procedencia
resultados/         salidas de la última corrida
├── simulacion_huella_carbono.csv    el resultado de la simulación (ver más arriba)
├── metadatos.json  equipo, versiones y parámetros con que se corrió
└── graficos/       los cinco PNG que embebe el informe

INFORME.md          el informe, generado
```
