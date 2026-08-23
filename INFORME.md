# Medición de la huella de carbono de algoritmos en Python

**Green Software — Universidad Tecnológica Nacional - FRC**

Fecha de la corrida: 2026-08-23 17:39:12

> Todas las cifras de este informe salen de las mediciones registradas en la corrida
> indicada arriba. Ninguna fue escrita a mano ni tomada de otra fuente.

---

## 1. Objetivo e hipótesis

**Objetivo.** Medir la huella de carbono asociada a la ejecución de algoritmos en
Python y determinar si las decisiones de diseño algorítmico tienen una consecuencia
ambiental cuantificable.

**Hipótesis.** Dos implementaciones que producen exactamente el mismo resultado
pueden diferir en órdenes de magnitud en energía consumida y, por lo tanto, en CO₂
emitido. La complejidad computacional no es solo una propiedad teórica: se traduce
en consumo eléctrico y en emisiones.

**Diseño experimental.** Un experimento, cada uno con variantes que resuelven el
mismo problema y devuelven el mismo resultado (equivalencia verificada por
aserción antes de cada medición):

- **Algoritmos de ordenamiento** — `bubble_sort` (O(n²)), `merge_sort` (O(n log n)), `timsort_nativo` (O(n log n) en C)

## 2. Marco teórico

La huella de carbono de un cómputo se obtiene multiplicando la energía eléctrica
consumida por la intensidad de carbono de la red que la suministra:

```
CO₂ [kgCO₂eq]  =  E [kWh]  ×  FE [kgCO₂eq/kWh]  ×  PUE
```

donde **FE** es el factor de emisión de la red eléctrica y **PUE** (*Power Usage
Effectiveness*) contabiliza la infraestructura de soporte, como la refrigeración de
un datacenter.

### Factor de emisión de la red argentina

Se adopta **FE = 346,0 gCO₂eq/kWh = 0,346 kgCO₂eq/kWh**, correspondiente a **2025**, el año más reciente disponible para Argentina.

Fuente: Ember (2026), Yearly Electricity Data — con procesamiento de Our World in Data
(<https://ourworldindata.org/grapher/carbon-intensity-electricity>, descargado el 2026-08-22). El indicador es la
*intensidad de carbono de ciclo de vida de la generación eléctrica*. La serie completa está
versionada en `datos/intensidad_carbono_argentina.json` y el proyecto
selecciona el último año disponible en cada corrida, de modo que el valor no puede
quedar desactualizado ni escrito a mano.

Evolución reciente de la intensidad de carbono de la red argentina:

| Año | gCO₂eq/kWh |
|---|---|
| 2020 | 394,70 |
| 2021 | 406,99 |
| 2022 | 392,69 |
| 2023 | 350,90 |
| 2024 | 344,83 |
| 2025 | 346,00 |

**Por qué no se usa el factor que trae la herramienta de medición.** CodeCarbon
incluye su propia tabla de factores por país, pero para Argentina está congelada en
2023: 354,103 gCO₂eq/kWh, incluso en la última
versión publicada de la herramienta (3.3.0). Ese valor
es un 2,3% superior al de 2025 y quedaría desactualizado.

Por eso **este informe toma la energía que mide la herramienta y la convierte a CO₂
con el factor de 2025**, el más reciente disponible. La cifra que la
herramienta calcularía con su propia tabla también queda registrada en los datos de la
corrida, para que la diferencia sea verificable.

Como contraste adicional, la Secretaría de Energía de la Nación (Argentina) publica un factor de emisión
de la red con metodología UNFCCC, Tool to calculate the emission factor for an electricity system, v7: su último valor disponible es
**343,5 gCO₂eq/kWh** para 2023
(<http://datos.energia.gob.ar/dataset/calculo-del-factor-de-emision-de-co2-de-la-red-argentina-de-energia-electrica>, archivo `factor_de_emision_2013_a_2023.xlsx`, descargado el 2026-08-22).
No se adopta acá porque es un factor marginal, pensado para evaluar proyectos, y no
una intensidad media de la red como la que corresponde a atribuir el consumo de un
proceso cualquiera. Su cercanía con el valor adoptado (0,7% de diferencia) sirve igual como verificación de orden de magnitud.

El orden de magnitud del factor se explica por la composición de la matriz
eléctrica argentina en 2023, el último año con desglose por fuente en los
datos que acompañan a CodeCarbon: sobre un total de 153,4 TWh generados,
**59,5% proviene de fuentes fósiles** (gas 73,4 TWh, petróleo 17,3 TWh, carbón 0,6 TWh), frente a 33,2 TWh de hidroelectricidad, 8,9 TWh de nuclear, 14,5 TWh de eólica y 3,2 TWh de solar.

Consecuencia relevante para el análisis: **el mismo algoritmo tiene distinta huella
según dónde se ejecute**. Corriéndolo en una red mayormente hidroeléctrica o
nuclear, las emisiones serían una fracción de las calculadas acá.

Se usa **PUE = 1.0** porque el experimento corre en una notebook, sin
infraestructura de refrigeración externa. En un datacenter el PUE típico está entre
1,1 y 1,6 —rango de referencia de la industria, no medido en este trabajo—, lo que
multiplicaría todos los resultados por ese factor.

## 3. Metodología

### 3.1 Entorno de medición

| Parámetro | Valor |
|---|---|
| Plataforma | macOS-26.5.2-arm64-arm-64bit |
| Procesador | Apple M2 Pro |
| Núcleos | 12 lógicos / 12 físicos |
| RAM | 16.0 GB |
| Python | 3.12.9 |
| NumPy | 2.5.2 |
| CodeCarbon | 3.3.0 |
| scikit-learn | 1.9.0 |
| Núcleos que puede usar la biblioteca numérica | sin límite declarado |
| Entorno | versiones exactas fijadas, para que la corrida sea repetible |
| Semilla aleatoria | 42 |
| Repeticiones por punto | 3 |

### 3.2 Protocolo de medición

1. **Verificación de equivalencia.** Antes de medir, se comprueba por aserción que
   todas las variantes del experimento devuelvan el mismo resultado. Comparar la
   huella de algoritmos que no resuelven lo mismo no tendría validez.
2. **Warm-up y dimensionado del lote.** Se hace una corrida de sondeo que calienta
   cachés e intérprete y sirve para fijar el tamaño del lote.
3. **Medición por lotes.** Varios de estos algoritmos terminan en millonésimas de
   segundo, mucho menos de lo que tarda cualquier instrumento en tomar una lectura de
   consumo. Medir una sola ejecución no daría una cifra interpretable. Por
   eso se ejecuta el algoritmo K veces dentro de la ventana medida, con K
   autoajustado para que el lote dure al menos 3,0 s —la ventana que pide la fuente de potencia de esta corrida (§3.4)—, y
   luego se divide por K. Es el criterio habitual para cronometrar operaciones muy
   rápidas. El tamaño del lote se calibra con una corrida de prueba previa, porque la
   primera ejecución de un algoritmo siempre es más lenta que las siguientes. Para las cargas que ya superan esa ventana por sí solas —el entrenamiento
   del modelo en los tamaños grandes— K queda en 1 y se mide la ejecución individual;
   el tamaño de lote de cada punto queda registrado en los datos de la corrida.
4. **Repeticiones.** Cada punto se mide 3 veces; se
   reportan media y dispersión.

### 3.3 Otra opción de cálculo: un modelo propio

Existe una alternativa a usar una herramienta de medición: deducir la potencia a
partir de cuánto procesador usa el algoritmo, y atribuirle sólo el consumo adicional
que provoca. La cadena de cálculo sería:

```
uso del procesador  =  tiempo de cálculo consumido / (tiempo transcurrido × núcleos)
potencia atribuida  =  (potencia máxima − potencia en reposo) × uso  +  memoria × W/GB
energía             =  potencia × tiempo
huella              =  energía × factor de emisión × PUE
```

Requiere tres parámetros del equipo donde se corre: la **potencia en reposo**, la
**potencia con todos los núcleos ocupados** y el **consumo de la memoria por GB**
usado. Los dos primeros hay que medirlos con un sensor de consumo; suponerlos vuelve
el resultado tan discutible como la suposición.

**Se menciona como opción y nada más: este trabajo no la implementa.** Todo lo que
sigue proviene de la vía que sí se desarrolla.

### 3.4 La vía de este trabajo: CodeCarbon

CodeCarbon es la herramienta de referencia en la industria para medir la huella de
carbono del software. **Todas las cifras de §4 y §5 salen de acá.** Se la usó con tres
criterios:

- **El país se declara, no se deduce.** La herramienta puede averiguarlo a partir de
  la conexión a internet, pero eso ataría el resultado a la red desde la que se corre
  y a un momento determinado. Acá se fija Argentina de entrada, y la corrida queda
  repetible.
- **Una sola sesión de medición para todo el benchmark.** Poner en marcha la
  herramienta lleva un tiempo, porque antes reconoce el equipo:
  2,9 s en esta corrida. Si se la arrancara y detuviera en cada medición, ese
  tiempo caería dentro de lo medido y arruinaría cualquier medición de milésimas de
  segundo. Se abre una sola vez y cada algoritmo se mide como una tarea dentro de esa
  sesión.
- **La potencia se mide, y sólo se estima cuando el equipo no permite medirla.** Es la
  decisión de mayor peso sobre los resultados, y por eso tiene su propia sección
  (§5.2). Hay equipos que exponen un sensor del consumo real del procesador; donde
  existe y está accesible, la potencia se lee de ahí. Donde no, la herramienta la
  calcula con una fórmula. **Este software puede correr en otra máquina:** el camino
  se decide en cada corrida según lo que ese equipo permita, y el informe declara cuál
  se usó en lugar de darlo por supuesto.

**En esta corrida la potencia se midió con el sensor del equipo.** Los valores de
CO₂ que siguen se apoyan, por lo tanto, en un consumo real y no en una estimación.

Medir el consumo real tiene una exigencia adicional sobre el protocolo: la lectura
tiene que tomarse mientras el algoritmo está trabajando. Por eso los lotes de §3.2
se dimensionan para durar al menos 3,0 s, en lugar de los
0,5 s que bastarían para cronometrar. Con ventanas más cortas la lectura
llega cuando el trabajo ya terminó, y el consumo informado queda inflado.

| Qué reconoció la herramienta | Valor |
|---|---|
| Procesador reconocido | Apple M2 Pro |
| Potencia del procesador | medida con el sensor del equipo durante la corrida |
| Potencia de la memoria | 3,00 W, valor de referencia de la herramienta |
| Red eléctrica | Argentina |

## 4. Resultados

### 4.0 Cómo leer las tablas

- **energía** y **CO₂** corresponden a **una sola ejecución** del algoritmo. El CO₂
  sale de esa energía con el factor de emisión de §2. Cuánta confianza merecen estas
  cifras se analiza en §5.2.
- **disp.** es cuánto varían entre sí las tres repeticiones del mismo punto. Por
  debajo del 1% la medición es reproducible. Hay dos motivos por los que un punto
  puede aparecer con dispersión alta, y ninguno invalida el promedio: en las variantes
  que reparten su trabajo entre varios núcleos, cuántos se activan cambia de una
  repetición a otra —eso es comportamiento del algoritmo—; y en los algoritmos más
  rápidos pesa más el tiempo que consume tomar la lectura de consumo (§5.2), que no
  es el mismo en cada repetición.
- El **exponente medido** resume cuánto crecen las emisiones cuando crece el tamaño
  del problema: un exponente 2 significa que al duplicar el tamaño las emisiones se
  cuadruplican. Se obtiene ajustando una recta a los datos en escala logarítmica. Si la
  complejidad teórica realmente gobierna las emisiones, un algoritmo O(n²) debe dar
  ≈ 2 y uno O(n³), ≈ 3. Para O(n log n) el valor esperado no es exactamente 1: la
  pendiente local de n·log(n) es 1 + 1/ln(n): sobre los tamaños medidos para esos
  algoritmos (n de 500 a 1.000) va de 1,14 a 1,16. Un
  crecimiento exponencial no sigue una ley de potencia, así que para ese caso el
  ajuste no se informa y se reporta en su lugar el factor de crecimiento por unidad
  de n.

### Algoritmos de ordenamiento

**Pregunta:** ¿La complejidad computacional se traduce en una diferencia medible de emisiones cuando el resultado producido es idéntico?

Las tres variantes ordenan exactamente la misma lista de enteros generada con semilla fija y devuelven el mismo resultado.

| n | algoritmo | complejidad | tiempo [s] | energía [kWh] | CO₂ [kg] | disp. |
|---|---|---|---|---|---|---|
| 500 | `bubble_sort` | O(n²) | 6.488e-03 | 6.429e-09 | 2.224e-09 | ±9,9% |
| 500 | `merge_sort` | O(n log n) | 5.555e-04 | 6.920e-10 | 2.394e-10 | ±16,0% |
| 500 | `timsort_nativo` | O(n log n) en C | 2.017e-05 | 2.241e-11 | 7.753e-12 | ±8,7% |
| 1000 | `bubble_sort` | O(n²) | 2.862e-02 | 2.859e-08 | 9.891e-09 | ±2,5% |
| 1000 | `merge_sort` | O(n log n) | 1.197e-03 | 1.259e-09 | 4.358e-10 | ±3,7% |
| 1000 | `timsort_nativo` | O(n log n) en C | 4.700e-05 | 4.669e-11 | 1.615e-11 | ±6,5% |

**Resultado para n = 1.000:** `timsort_nativo` (O(n log n) en C) emite **612 veces menos** CO₂ que `bubble_sort` (O(n²)), produciendo exactamente el mismo resultado.

![Algoritmos de ordenamiento](resultados/graficos/01_ordenamiento_escalado.png)

## 5. Análisis

### 5.1 Tiempo de ejecución como aproximación de la huella

Sobre las 6 configuraciones medidas, las emisiones resultan casi
exactamente proporcionales al tiempo de ejecución: al relacionar ambas magnitudes, un
algoritmo que tarda el doble emite **1,99 veces más**, y la relación explica el
**99,90%** de la variación observada.

Conviene entender por qué, porque no es una ley general. Casi todas las cargas de
este banco de pruebas usan el procesador de la misma forma: un solo núcleo,
calculando sin pausas. A igual intensidad de uso, el consumo por segundo es
parecido, y entonces la energía —que es consumo por tiempo— queda gobernada por el
tiempo. **La proporcionalidad es real, pero vale entre cargas que usan la máquina de
forma comparable.**

**Conclusión práctica:** en este banco de pruebas el tiempo de ejecución resultó un
buen indicador de la huella, incluso en la carga que ocupa todos los núcleos. No
conviene generalizarlo: un programa que pasa el tiempo esperando respuesta de disco
o de red acumula segundos sin consumir casi nada, y ahí la relación se rompe. Este
trabajo no mide ese caso.

![Tiempo vs CO₂](resultados/graficos/05_tiempo_vs_co2.png)

### 5.2 Cuánta confianza merecen estas cifras

Una huella de carbono de software es energía convertida a CO₂, y la energía es
potencia por tiempo. El tiempo se cronometra sin dificultad. La potencia es la parte
difícil, y de ella depende todo lo demás, así que corresponde declarar de dónde salió.

**En esta corrida la potencia se midió** con el sensor de consumo del propio equipo
(§3.4). Los valores absolutos de CO₂ se apoyan entonces en un consumo real. Quedan
dos salvedades, que no son del cálculo sino del alcance de la medición:

1. **El sensor mide el procesador completo, no el algoritmo.** Si otro programa
   trabaja al mismo tiempo, parte de su consumo se le atribuye al algoritmo medido.
   Se midió con el equipo descargado y repitiendo cada punto tres veces, pero no se
   elimina del todo.
2. **Tomar la lectura lleva su propio tiempo.** El consumo que se informa cubre la
   ventana de medición completa, y esa ventana incluye el rato que el instrumento
   tarda en leer: 1,9 s por medición en esta corrida, sobre ventanas de
   3,0 s. Ese rato transcurre con el algoritmo ya terminado y el equipo
   casi en reposo, así que **agrega algo de consumo que no le corresponde al
   algoritmo**. Afecta más a los algoritmos más rápidos, que son los que quedan
   con las ventanas más cortas.

**La alternativa habría sido estimarla.** Cuando un equipo no expone un sensor
accesible, la herramienta deduce la potencia del consumo nominal del procesador y de
cuán ocupada está la máquina. Conviene saber a qué se renunció al no usar ese
camino: en este equipo la herramienta no reconoce el procesador, así que le habría
asignado un consumo nominal genérico de 85 W —el de una computadora de
escritorio, no el de una notebook— y de ahí habría derivado toda la energía.

**Qué se puede afirmar y qué no.**

- Los valores absolutos de CO₂ son una medición, no una estimación, y se pueden
  citar como tales.
- **Las comparaciones entre algoritmos se sostienen**, que es lo que responde la
  hipótesis de este trabajo: todos se midieron de la misma forma, en el mismo equipo y
  en la misma sesión, así que cualquier sesgo los afecta a todos por igual.
- Y queda una lección que va más allá de este proyecto: **dos mediciones de huella del
  software pueden diferir varias veces según cómo obtuvieron la potencia.** Un informe
  de huella que no declare eso no es verificable.

### 5.3 Magnitud de los resultados

Las emisiones de una ejecución individual son diminutas. La suma de todas las
configuraciones medidas en este benchmark asciende a **1.281e-08 kgCO₂eq**.
Presentar solo ese número invitaría a concluir que el problema es irrelevante, y
sería una lectura equivocada: el software se ejecuta a escala.

- El peor algoritmo medido (`bubble_sort`, cantidad de elementos = 1.000) repetido
  1.000.000 veces —un millón de ejecuciones (una función invocada por un servicio web de tamaño medio a lo largo de unos meses)— emite **0,010 kgCO₂eq**,
  equivalente a 0 km recorridos en auto, 3 cargas completas de un smartphone.
- El peor algoritmo medido (`bubble_sort`, cantidad de elementos = 1.000) repetido
  1.000.000.000 veces —mil millones de ejecuciones (escala de un servicio masivo)— emite **9,891 kgCO₂eq**,
  equivalente a 64 km recorridos en auto, 2.859 cargas completas de un smartphone.

Equivalencias utilizadas:

| Unidad | Factor | Fuente / cálculo |
|---|---|---|
| km recorridos en auto | 0,15557 kgCO₂eq c/u | 7,9 L/100 km (consumo medio de vehículos livianos en Argentina) × 1,9693 kgCO₂/L (Nafta Grado 2 (Súper) con bioetanol 12%, CO₂ fósil) |
| cargas completas de un smartphone | 0,00346 kgCO₂eq c/u | Batería de ~10 Wh cargada desde la red: 0,010 kWh × 0,346 kgCO₂eq/kWh (FE 2025) |

## 6. Limitaciones

Se declaran explícitamente porque condicionan cómo hay que leer los resultados:

1. **El consumo medido es del procesador completo**, no exclusivamente del algoritmo
   (§5.2). Se midió con el equipo descargado, pero el ruido de fondo del sistema
   operativo no se elimina del todo.
2. **Parte de la ventana de medición ocurre con el algoritmo ya terminado**, porque
   tomar la lectura lleva su propio tiempo (§5.2). Eso suma algo de consumo ajeno,
   y pesa más en los algoritmos más rápidos.
3. **Solo se cuenta la energía de uso.** Queda afuera la huella de fabricar el equipo,
   transportarlo y descartarlo. En un análisis de ciclo de vida completo, fabricar
   suele pesar más que usar.
4. **El factor de emisión es un promedio anual.** La red eléctrica no emite lo mismo a
   toda hora: depende de qué centrales estén generando en ese momento. Correr un
   proceso de madrugada o al mediodía no tiene el mismo impacto real.
5. **Los resultados son de este equipo.** Otro procesador, otro sistema operativo u
   otra red eléctrica dan otras cifras absolutas. Las diferencias *entre* algoritmos,
   que son la conclusión del trabajo, sí son trasladables.

## 7. Conclusiones

1. En **Algoritmos de ordenamiento** (n=1000), `timsort_nativo` emite **612×** menos CO₂ que `bubble_sort` para un resultado idéntico.

**La hipótesis se verifica.** Las diferencias de huella entre algoritmos
equivalentes no son marginales: alcanzan varios órdenes de magnitud. **Elegir un
algoritmo adecuado no es solo una decisión de rendimiento, es también una decisión
ambiental**.

## 8. Reproducción

```bash
uv sync                            # instala el entorno exacto desde uv.lock
uv run huella-carbono --completo   # corre el benchmark y regenera este informe
```

Artefactos generados:

| Artefacto | Contenido |
|---|---|
| `resultados/simulacion_huella_carbono.csv` | **resultado de la simulación**: una fila por medición, con el tiempo, la energía y el CO₂ de cada algoritmo y tamaño. Los promedios de este informe salen de ahí. |
| `resultados/metadatos.json` | con qué equipo, qué versiones y qué parámetros se corrió |
| `resultados/graficos/*.png` | gráficos incluidos en este informe |
| `INFORME.md` | este documento |

Entradas de datos versionadas con el proyecto (no se generan, se leen):

| Archivo | Contenido |
|---|---|
| `datos/intensidad_carbono_argentina.json` | serie de intensidad de carbono de la red argentina y factor oficial de contraste, con su procedencia |
| `datos/equivalencias_co2.json` | factores para traducir kgCO₂eq a magnitudes tangibles (§5.3), con su fuente |

## 9. Fuentes y referencias

**Datos de emisiones de la red eléctrica**

1. Ember (2026), Yearly Electricity Data — con procesamiento de Our World in Data. *Intensidad de carbono de ciclo de vida de la generación eléctrica*, serie 2000–2025 para Argentina. <https://ourworldindata.org/grapher/carbon-intensity-electricity> (consultado el 2026-08-22). Valor adoptado en este trabajo: 346,0 gCO₂eq/kWh (2025).
2. Ember. *Yearly Electricity Data* — fuente primaria de la serie anterior. <https://ember-energy.org/data/yearly-electricity-data/>.
3. Secretaría de Energía de la Nación (Argentina). *Factor de emisión de CO2 de la red — margen combinado (w_OM = 0,75; w_BM = 0,25)*. Metodología: UNFCCC, Tool to calculate the emission factor for an electricity system, v7. <http://datos.energia.gob.ar/dataset/calculo-del-factor-de-emision-de-co2-de-la-red-argentina-de-energia-electrica> (archivo `factor_de_emision_2013_a_2023.xlsx`, consultado el 2026-08-22). Valor 2023: 343,5 gCO₂eq/kWh; citado como contraste, no usado en los cálculos.

**Herramientas de medición**

4. CodeCarbon 3.3.0 — herramienta de medición usada en este trabajo (§3.4). <https://github.com/mlco2/codecarbon> · <https://mlco2.github.io/codecarbon/>. Su tabla interna de factores de emisión por país da para Argentina 354,1 gCO₂eq/kWh, valor de 2023, que este trabajo no adopta por el motivo explicado en §2.
5. scikit-learn 1.9.0 — provee el clasificador de vecinos más cercanos y el generador del conjunto de datos sintético del cuarto experimento. <https://scikit-learn.org/stable/>.
6. Utilidad de consumo del sistema operativo (macOS) — es el sensor del que se lee la potencia real del procesador en este equipo (§3.4).

**Equivalencias de referencia**

7. GFEI / ONU Medio Ambiente, estudio de línea de base de eficiencia de vehículos livianos en Argentina (2018), sobre los vehículos registrados entre 2006 y 2017: 7,9 L/100 km. <https://www.globalfueleconomy.org/news/event-showcases-argentina-s-new-comparative-vehicle-efficiency-label-and-electric-shift> (consultado el 2026-08-22).
8. Sistema Nacional de Inventario de GEI de Argentina (SNIGEIAR), Factores de Emisión para huella de carbono 2025, Subsecretaría de Ambiente de la Nación, Tabla 2 «Combustibles - Transporte»: 1,9693 kgCO₂/L para Nafta Grado 2 (Súper) con bioetanol 12%, CO₂ fósil. <https://inventariogei.ambiente.gob.ar/files/Factores_de_Emision_SNIGEIAR_para_HC_2025.pdf> (consultado el 2026-08-22). Combinado con el consumo anterior da la equivalencia «km recorridos en auto» de §5.3: **155,6 gCO₂/km**. El factor por km se calcula como consumo × factor del combustible, con datos argentinos en ambos términos. Se cuenta solo el CO₂ fósil: la nafta argentina lleva 12% de bioetanol por norma y su CO₂ biogénico (0,1795 kgCO₂/L, es decir 14,2 gCO₂/km) se informa aparte según la práctica del inventario nacional.
9. Equivalencias eléctricas de §5.3: se definen por su consumo en kWh («cargas completas de un smartphone» = 0,010 kWh) y se convierten con el factor de emisión de este informe, de modo que no pueden quedar desfasadas del FE en uso. Definidas en `datos/equivalencias_co2.json`.

**Metodología**

10. UNFCCC. *Tool to calculate the emission factor for an electricity system*, versión 7 — metodología del factor oficial argentino citado arriba. <https://cdm.unfccc.int/methodologies/PAmethodologies/tools/am-tool-07-v7.0.pdf>.
11. The Green Software Foundation. *Software Carbon Intensity (SCI) Specification* — marco de referencia para la fórmula CO₂ = E × FE × PUE usada en §2. <https://sci.greensoftware.foundation/>.
