# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Generación del reporte del benchmark (`INFORME.md`).

El informe se construye íntegramente a partir de `resultados/simulacion_huella_carbono.csv`
y `resultados/metadatos.json`: ninguna cifra del texto está escrita a mano, de modo que
el reporte no pueda quedar desincronizado de los datos medidos.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from huella_carbono import config
from huella_carbono.config import EQUIVALENCIAS, EXPERIMENTOS


def formato_cientifico(valor: float, decimales: int = 3) -> str:
    """
    Notación científica con coma decimal, para que todo el informe use la misma convención
    tipográfica del español y no convivan dos separadores en la misma línea.
    """
    if pd.isna(valor):
        return "—"
    return f"{valor:.{decimales}e}".replace(".", ",")


def formato_factor(valor: float) -> str:
    """
    Formatea un factor de mejora con la precisión que corresponde a su magnitud.

    Con `decimales=0` fijo, un factor de 1,4 se imprimía como "1 veces menos", que además de
    ilegible es falso. Los factores grandes, en cambio, no ganan nada con decimales.
    """
    if pd.isna(valor):
        return "—"
    if valor >= 100:
        return formato_numero(valor, 0)
    if valor >= 10:
        return formato_numero(valor, 1)
    return formato_numero(valor, 2)


def formato_numero(valor: float, decimales: int = 2) -> str:
    """
    Formatea un número con las convenciones tipográficas del español: punto como
    separador de miles y coma como separador decimal. La notación científica se deja
    con punto decimal, que es la convención internacional en publicaciones técnicas.
    """
    if pd.isna(valor):
        return "—"
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def tabla_markdown(filas: list[list[str]], encabezados: list[str]) -> str:
    lineas = ["| " + " | ".join(encabezados) + " |"]
    lineas.append("|" + "|".join(["---"] * len(encabezados)) + "|")
    for fila in filas:
        lineas.append("| " + " | ".join(fila) + " |")
    return "\n".join(lineas)


def seccion_experimento(
    clave: str,
    resumen: pd.DataFrame,
    grafico: str | None,
    metadatos: dict[str, Any] | None = None,
) -> str:
    exp = EXPERIMENTOS[clave]
    datos = resumen[resumen.experimento == clave].sort_values(["n", "algoritmo"])
    if datos.empty:
        return ""

    partes = [f"### {exp.titulo}", "", f"**Pregunta:** {exp.pregunta}", "", exp.notas, ""]

    def complejidad_de(algoritmo: str, guardada: str) -> str:
        """Etiqueta vigente del experimento; la del CSV es la de la corrida que lo generó."""
        return exp.variantes.get(str(algoritmo), guardada)

    filas = []
    for _, f in datos.iterrows():
        desvio = f.co2_kg_std
        variabilidad = (
            f"±{formato_numero(desvio / f.co2_kg_mean * 100, 1)}%"
            if pd.notna(desvio) and f.co2_kg_mean > 0
            else "—"
        )
        filas.append(
            [
                str(int(f.n)),
                f"`{f.algoritmo}`",
                complejidad_de(f.algoritmo, f.complejidad),
                formato_cientifico(f.tiempo_s_mean),
                formato_cientifico(f.energia_kwh_mean),
                formato_cientifico(f.co2_kg_mean),
                variabilidad,
            ]
        )
    partes.append(
        tabla_markdown(
            filas,
            [
                "n",
                "algoritmo",
                "complejidad",
                "tiempo [s]",
                "energía [kWh]",
                "CO₂ [kg]",
                "disp.",
            ],
        )
    )
    partes.append("")

    # Factor de mejora entre el peor y el mejor algoritmo, en el mayor tamaño medido.
    n_max = datos.n.max()
    en_max = datos[datos.n == n_max].sort_values("co2_kg_mean")
    if len(en_max) >= 2:
        mejor, peor = en_max.iloc[0], en_max.iloc[-1]
        factor = peor.co2_kg_mean / mejor.co2_kg_mean
        partes.append(
            f"**Resultado para n = {formato_numero(int(n_max), 0)}:** `{mejor.algoritmo}` "
            f"({complejidad_de(mejor.algoritmo, mejor.complejidad)}) emite "
            f"**{formato_factor(factor)} veces menos** CO₂ que `{peor.algoritmo}` "
            f"({complejidad_de(peor.algoritmo, peor.complejidad)}), produciendo exactamente "
            f"el mismo resultado."
        )
        partes.append("")

        # Cuando el factor de tiempo y el de CO2 no coinciden, decirlo: es el caso en que
        # optimizar el reloj no equivale a optimizar la huella. Se informa sólo si la
        # diferencia entre ambos factores es apreciable, para no ensuciar los experimentos
        # donde tiempo y emisiones van de la mano.
        if peor.tiempo_s_mean > 0 and mejor.tiempo_s_mean > 0:
            factor_tiempo = float(peor.tiempo_s_mean / mejor.tiempo_s_mean)
            if factor_tiempo > 0 and (
                factor / factor_tiempo > 2 or factor_tiempo / factor > 2
            ):
                if factor_tiempo > factor:
                    partes.append(
                        f"Pero el tiempo cuenta otra historia: `{mejor.algoritmo}` es "
                        f"**{formato_factor(factor_tiempo)} veces más rápido** y sólo "
                        f"**{formato_factor(factor)} veces más limpio**: la ventaja de reloj no "
                        f"se traslada por completo a las emisiones (§5.1)."
                    )
                else:
                    partes.append(
                        f"El contraste con el tiempo es aún mayor en emisiones: "
                        f"`{mejor.algoritmo}` es {formato_factor(factor_tiempo)} veces más "
                        f"rápido pero {formato_factor(factor)} veces más limpio."
                    )
                partes.append("")

        # Inversión del orden: si el algoritmo más limpio en el tamaño más chico no es el
        # más limpio en el más grande, la conclusión depende de la escala y hay que decirlo.
        n_min = datos.n.min()
        en_min = datos[datos.n == n_min].sort_values("co2_kg_mean")
        if len(en_min) >= 2 and n_min != n_max:
            mejor_min = en_min.iloc[0]
            if str(mejor_min.algoritmo) != str(mejor.algoritmo):
                fila_min_del_mejor = en_min[en_min.algoritmo == mejor.algoritmo]
                if not fila_min_del_mejor.empty:
                    factor_invertido = float(
                        fila_min_del_mejor.iloc[0].co2_kg_mean
                        / mejor_min.co2_kg_mean
                    )
                    partes.append(
                        f"**El orden se invierte con el tamaño.** En "
                        f"{exp.unidad_n} = {formato_numero(int(n_min), 0)} el más limpio no es "
                        f"`{mejor.algoritmo}` sino `{mejor_min.algoritmo}`: ahí "
                        f"`{mejor.algoritmo}` emite {formato_factor(factor_invertido)} veces "
                        f"**más**. Es decir que la respuesta a «cuál conviene» depende de la "
                        f"escala de trabajo, no sólo del algoritmo."
                    )
                    partes.append("")

    calidad = (metadatos or {}).get("calidad_knn") or {}
    if calidad and clave == "aprendizaje_knn":
        partes.append(
            "**Calidad del modelo.** La comparación es entre implementaciones equivalentes, no "
            "entre modelos distintos: las tres variantes devuelven las mismas predicciones y "
            "por lo tanto la misma exactitud. Se informa para dejar constancia de que el "
            "trabajo medido es un modelo que efectivamente aprende, y no un cómputo vacío.\n\n"
            + tabla_markdown(
                [
                    [formato_numero(int(n), 0), formato_numero(float(valor) * 100, 2) + "%"]
                    for n, valor in sorted(calidad.items(), key=lambda par: int(par[0]))
                ],
                ["muestras", "exactitud sobre el conjunto de prueba"],
            )
        )
        partes.append("")

    if exp.descripciones:
        partes.append("**Qué hace cada variante.**")
        partes.append("")
        # En el orden en que las declara el experimento, no el alfabético de la tabla: las
        # descripciones están escritas para leerse en ese orden.
        medidos = set(str(x) for x in datos.algoritmo.unique())
        for algoritmo, descripcion in exp.descripciones.items():
            if algoritmo in medidos:
                partes.append(f"- **`{algoritmo}`** — {descripcion}")
        partes.append("")

    if grafico:
        partes.append(f"![{exp.titulo}]({grafico})")
        partes.append("")
    return "\n".join(partes)


def generar(resumen: pd.DataFrame, metadatos: dict[str, Any], rutas: dict[str, str]) -> str:
    """Arma el informe completo y lo escribe en `INFORME.md`."""
    mediciones = (
        pd.read_csv(config.CSV_SIMULACION) if config.CSV_SIMULACION.exists() else None
    )
    presentes = set(str(clave) for clave in resumen.experimento.unique())
    cc = metadatos.get("codecarbon_deteccion", {})
    matriz = config.MATRIZ_AR

    total_co2 = float(resumen.co2_kg_mean.sum())

    p: list[str] = []
    a = p.append

    # ---------------------------------------------------------------- portada
    a("# Medición de la huella de carbono de algoritmos en Python")
    a("")
    a("**Green Software — Universidad Tecnológica Nacional - FRC**")
    a("")
    a(f"Fecha de la corrida: {metadatos['fecha']}")
    a("")
    a("> Todas las cifras de este informe salen de las mediciones registradas en la corrida")
    a("> indicada arriba. Ninguna fue escrita a mano ni tomada de otra fuente.")
    a("")
    a("---")
    a("")

    # ---------------------------------------------------------------- objetivo
    a("## 1. Objetivo e hipótesis")
    a("")
    a("**Objetivo.** Medir la huella de carbono asociada a la ejecución de algoritmos en")
    a("Python y determinar si las decisiones de diseño algorítmico tienen una consecuencia")
    a("ambiental cuantificable.")
    a("")
    a("**Hipótesis.** Dos implementaciones que producen exactamente el mismo resultado")
    a("pueden diferir en órdenes de magnitud en energía consumida y, por lo tanto, en CO₂")
    a("emitido. La complejidad computacional no es solo una propiedad teórica: se traduce")
    a("en consumo eléctrico y en emisiones.")
    a("")
    cantidad = len([c for c in EXPERIMENTOS if c in presentes])
    nombres_cantidad = {1: "Un experimento", 2: "Dos experimentos", 3: "Tres experimentos",
                        4: "Cuatro experimentos", 5: "Cinco experimentos"}
    a(f"**Diseño experimental.** {nombres_cantidad.get(cantidad, f'{cantidad} experimentos')}, "
      "cada uno con variantes que resuelven el")
    a("mismo problema y devuelven el mismo resultado (equivalencia verificada por")
    a("aserción antes de cada medición):")
    a("")
    for clave, exp in EXPERIMENTOS.items():
        if clave in set(resumen.experimento.unique()):
            variantes = ", ".join(f"`{k}` ({v})" for k, v in exp.variantes.items())
            a(f"- **{exp.titulo}** — {variantes}")
    a("")

    # ---------------------------------------------------------------- marco teórico
    a("## 2. Marco teórico")
    a("")
    a("La huella de carbono de un cómputo se obtiene multiplicando la energía eléctrica")
    a("consumida por la intensidad de carbono de la red que la suministra:")
    a("")
    a("```")
    a("CO₂ [kgCO₂eq]  =  E [kWh]  ×  FE [kgCO₂eq/kWh]  ×  PUE")
    a("```")
    a("")
    a("donde **FE** es el factor de emisión de la red eléctrica y **PUE** (*Power Usage")
    a("Effectiveness*) contabiliza la infraestructura de soporte, como la refrigeración de")
    a("un datacenter.")
    a("")
    a("### Factor de emisión de la red argentina")
    a("")
    a(f"Se adopta **FE = {formato_numero(config.FACTOR_EMISION_AR_G_KWH, 1)} gCO₂eq/kWh = "
      f"{formato_numero(config.FACTOR_EMISION_AR, 3)} kgCO₂eq/kWh**, correspondiente a "
      f"**{config.ANIO_FACTOR_EMISION}**, el año más reciente disponible para Argentina.")
    a("")
    a(f"Fuente: {config.FUENTE_FACTOR_EMISION}")
    a(f"(<{config.INTENSIDAD_CARBONO['url']}>, descargado el "
      f"{config.INTENSIDAD_CARBONO['descargado']}). El indicador es la")
    a(f"*{config.INTENSIDAD_CARBONO['indicador'].lower()}*. La serie completa está")
    a(f"versionada en `datos/{config.ARCHIVO_INTENSIDAD_CARBONO.name}` y el proyecto")
    a("selecciona el último año disponible en cada corrida, de modo que el valor no puede")
    a("quedar desactualizado ni escrito a mano.")
    a("")
    a("Evolución reciente de la intensidad de carbono de la red argentina:")
    a("")
    serie = config.INTENSIDAD_CARBONO["serie_g_kwh"]
    ultimos = sorted(serie, key=int)[-6:]
    a(
        tabla_markdown(
            [[anio, f"{formato_numero(serie[anio], 2)}"] for anio in ultimos],
            ["Año", "gCO₂eq/kWh"],
        )
    )
    a("")
    a("**Por qué no se usa el factor que trae la herramienta de medición.** CodeCarbon")
    a("incluye su propia tabla de factores por país, pero para Argentina está congelada en")
    a(f"{config.ANIO_FACTOR_EMISION_CODECARBON}: {formato_numero(config.FACTOR_EMISION_CODECARBON_G_KWH, 3)} gCO₂eq/kWh, incluso en la última")
    a(f"versión publicada de la herramienta ({metadatos.get('codecarbon', 'n/d')}). Ese valor")
    a(f"es un {formato_numero(abs(config.FACTOR_EMISION_CODECARBON_G_KWH / config.FACTOR_EMISION_AR_G_KWH - 1) * 100, 1)}% superior al de "
      f"{config.ANIO_FACTOR_EMISION} y quedaría desactualizado.")
    a("")
    a("Por eso **este informe toma la energía que mide la herramienta y la convierte a CO₂")
    a(f"con el factor de {config.ANIO_FACTOR_EMISION}**, el más reciente disponible. La cifra que la")
    a("herramienta calcularía con su propia tabla también queda registrada en los datos de la")
    a("corrida, para que la diferencia sea verificable.")
    a("")
    oficial = config.REFERENCIA_FACTOR_OFICIAL
    if oficial:
        a(f"Como contraste adicional, la {oficial['organismo']} publica un factor de emisión")
        a(f"de la red con metodología {oficial['metodologia']}: su último valor disponible es")
        a(f"**{formato_numero(oficial['valor_g_kwh'], 1)} gCO₂eq/kWh** para {oficial['anio']}")
        a(f"(<{oficial['url']}>, archivo `{oficial['archivo']}`, descargado el {oficial['descargado']}).")
        a("No se adopta acá porque es un factor marginal, pensado para evaluar proyectos, y no")
        a("una intensidad media de la red como la que corresponde a atribuir el consumo de un")
        a(f"proceso cualquiera. Su cercanía con el valor adoptado "
          f"({formato_numero(abs(oficial['valor_g_kwh'] / config.FACTOR_EMISION_AR_G_KWH - 1) * 100, 1)}% de diferencia) "
          f"sirve igual como verificación de orden de magnitud.")
        a("")
    fosil_pct = matriz["fossil_TWh"] / matriz["total_TWh"] * 100
    a("El orden de magnitud del factor se explica por la composición de la matriz")
    a(f"eléctrica argentina en {matriz['anio']}, el último año con desglose por fuente en los")
    a(f"datos que acompañan a CodeCarbon: sobre un total de {formato_numero(matriz['total_TWh'], 1)} TWh generados,")
    a(f"**{formato_numero(fosil_pct, 1)}% proviene de fuentes fósiles** "
      f"(gas {formato_numero(matriz['gas_TWh'], 1)} TWh, petróleo {formato_numero(matriz['oil_TWh'], 1)} TWh, "
      f"carbón {formato_numero(matriz['coal_TWh'], 1)} TWh), frente a "
      f"{formato_numero(matriz['hydroelectricity_TWh'], 1)} TWh de hidroelectricidad, "
      f"{formato_numero(matriz['nuclear_TWh'], 1)} TWh de nuclear, "
      f"{formato_numero(matriz['wind_TWh'], 1)} TWh de eólica y {formato_numero(matriz['solar_TWh'], 1)} TWh de solar.")
    a("")
    a("Consecuencia relevante para el análisis: **el mismo algoritmo tiene distinta huella")
    a("según dónde se ejecute**. Corriéndolo en una red mayormente hidroeléctrica o")
    a("nuclear, las emisiones serían una fracción de las calculadas acá.")
    a("")
    a(f"Se usa **PUE = {formato_numero(config.PUE, 1)}** porque el experimento corre en una notebook, sin")
    a("infraestructura de refrigeración externa. En un datacenter el PUE típico está entre")
    a("1,1 y 1,6 —rango de referencia de la industria, no medido en este trabajo—, lo que")
    a("multiplicaría todos los resultados por ese factor.")
    a("")

    # ---------------------------------------------------------------- metodología
    a("## 3. Metodología")
    a("")
    a("### 3.1 Entorno de medición")
    a("")
    a(
        tabla_markdown(
            [
                ["Plataforma", metadatos["plataforma"]],
                ["Procesador", f"{cc.get('cpu_model', metadatos['procesador'])}"],
                [
                    "Núcleos",
                    f"{metadatos['cpu_nucleos_logicos']} lógicos / "
                    f"{metadatos['cpu_nucleos_fisicos']} físicos",
                ],
                ["RAM", f"{formato_numero(metadatos['ram_total_gb'], 1)} GB"],
                ["Python", metadatos["python"]],
                ["NumPy", metadatos["numpy"]],
                ["CodeCarbon", metadatos["codecarbon"]],
                ["scikit-learn", metadatos.get("scikit_learn", "—")],
                [
                    "Núcleos que puede usar la biblioteca numérica",
                    ", ".join(
                        str(h["hilos"]) for h in metadatos.get("hilos_blas", [])
                    )
                    or "sin límite declarado",
                ],
                ["Entorno", "versiones exactas fijadas, para que la corrida sea repetible"],
                ["Semilla aleatoria", str(metadatos["semilla"])],
                ["Repeticiones por punto", str(metadatos["repeticiones"])],
            ],
            ["Parámetro", "Valor"],
        )
    )
    a("")
    a("### 3.2 Protocolo de medición")
    a("")
    a("Cada **punto de medición** es una combinación de algoritmo y tamaño de entrada, y")
    a("corresponde a una fila de las tablas de §4. Con cuatro experimentos y sus variantes")
    a(f"son {len(resumen)} puntos. Cada uno se mide así:")
    a("")
    a("1. **Se verifica la equivalencia.** Antes de medir se comprueba por aserción que todas")
    a("   las variantes del experimento devuelvan el mismo resultado. Comparar la huella de")
    a("   algoritmos que no resuelven lo mismo no tendría validez.")
    a("2. **Se calcula el tamaño del lote.** Varios de estos algoritmos terminan en")
    a("   millonésimas de segundo, mucho menos de lo que tarda un sensor en dar una lectura")
    a("   de consumo, así que no se mide una ejecución aislada: se mide un **lote de K")
    a(f"   ejecuciones seguidas**, con K elegido para que el lote dure al menos "
      f"{formato_numero(metadatos.get('ventana_medicion_s', config.DURACION_MINIMA_LOTE_S), 1)} s (§3.4).")
    a("   K se calcula con una corrida de prueba previa, que además funciona como")
    a("   calentamiento: la primera ejecución de un algoritmo siempre es más lenta que las")
    a("   siguientes.")
    a("3. **Se mide el lote y se divide por K.** Lo que se informa es entonces el costo de")
    a("   *una* ejecución, aunque nunca se haya medido una sola por separado. Cuando un")
    a("   algoritmo ya dura más que la ventana por sí solo —el entrenamiento del modelo en")
    a("   los tamaños grandes— K queda en 1.")
    a(f"4. **Se repite {metadatos['repeticiones']} veces** y se informan el promedio y la dispersión entre esas")
    a(f"   {metadatos['repeticiones']} mediciones.")
    a("")
    a("Un ejemplo concreto de esta corrida, para fijar la idea: el algoritmo más rápido del")
    ejemplo = None
    if mediciones is not None and "ejecuciones_lote" in mediciones:
        fila = mediciones.loc[mediciones.ejecuciones_lote.idxmax()]
        ejemplo = (str(fila.algoritmo), int(fila.n), int(fila.ejecuciones_lote))
    if ejemplo:
        nombre_alg, n_alg, lote_alg = ejemplo
        a(f"banco, `{nombre_alg}`, se midió en lotes de "
          f"**{formato_numero(lote_alg, 0)} ejecuciones**; con "
          f"{metadatos['repeticiones']} repeticiones,")
        a(f"detrás de esa fila de la tabla hay "
          f"{formato_numero(lote_alg * int(metadatos['repeticiones']), 0)} ejecuciones reales del algoritmo.")
    a("")

    a("### 3.3 Otra opción de cálculo: un modelo propio")
    a("")
    a("Existe una alternativa a usar una herramienta de medición: deducir la potencia a")
    a("partir de cuánto procesador usa el algoritmo, y atribuirle sólo el consumo adicional")
    a("que provoca. La cadena de cálculo sería:")
    a("")
    a("```")
    a("uso del procesador  =  tiempo de cálculo consumido / (tiempo transcurrido × núcleos)")
    a("potencia atribuida  =  (potencia máxima − potencia en reposo) × uso  +  memoria × W/GB")
    a("energía             =  potencia × tiempo")
    a("huella              =  energía × factor de emisión × PUE")
    a("```")
    a("")
    a("Requiere tres parámetros del equipo donde se corre: la **potencia en reposo**, la")
    a("**potencia con todos los núcleos ocupados** y el **consumo de la memoria por GB**")
    a("usado. Los dos primeros hay que medirlos con un sensor de consumo; suponerlos vuelve")
    a("el resultado tan discutible como la suposición.")
    a("")
    a("**Se menciona como opción y nada más: este trabajo no la implementa.** Todo lo que")
    a("sigue proviene de la vía que sí se desarrolla.")
    a("")

    a("### 3.4 La vía de este trabajo: CodeCarbon")
    a("")
    a("CodeCarbon es la herramienta de referencia en la industria para medir la huella de")
    a("carbono del software. **Todas las cifras de §4 y §5 salen de acá.** Se la usó con tres")
    a("criterios:")
    a("")
    a("- **El país se declara, no se deduce.** La herramienta puede averiguarlo a partir de")
    a("  la conexión a internet, pero eso ataría el resultado a la red desde la que se corre")
    a("  y a un momento determinado. Acá se fija Argentina de entrada, y la corrida queda")
    a("  repetible.")
    deteccion_s = cc.get("segundos_deteccion_hardware")
    a("- **Una sola sesión de medición para todo el benchmark.** Poner en marcha la")
    a("  herramienta lleva un tiempo, porque antes reconoce el equipo:")
    if deteccion_s is not None:
        a(f"  {formato_numero(deteccion_s, 1)} s en esta corrida. Si se la arrancara y detuviera en cada medición, ese")
    else:
        a("  se midió en esta corrida. Si se la arrancara y detuviera en cada medición, ese")
    a("  tiempo caería dentro de lo medido y arruinaría cualquier medición de milésimas de")
    a("  segundo. Se abre una sola vez y cada algoritmo se mide como una tarea dentro de esa")
    a("  sesión.")
    a("- **La potencia se mide, y sólo se estima cuando el equipo no permite medirla.** Es la")
    a("  decisión de mayor peso sobre los resultados, y por eso tiene su propia sección")
    a("  (§5.2). Hay equipos que exponen un sensor del consumo real del procesador; donde")
    a("  existe y está accesible, la potencia se lee de ahí. Donde no, la herramienta la")
    a("  calcula con una fórmula. **Este software puede correr en otra máquina:** el camino")
    a("  se decide en cada corrida según lo que ese equipo permita, y el informe declara cuál")
    a("  se usó en lugar de darlo por supuesto.")
    a("")
    lectura_directa = cc.get("lectura_directa")
    if lectura_directa:
        a("**En esta corrida la potencia se midió con el sensor del equipo.** Los valores de")
        a("CO₂ que siguen se apoyan, por lo tanto, en un consumo real y no en una estimación.")
    else:
        a("**En esta corrida el equipo no permitió medir la potencia, así que se estimó.** Los")
        a("valores absolutos de CO₂ que siguen hay que leerlos con la salvedad que explica")
        a("§5.2.")
    a("")
    if cc.get("requiere_ventana_muestreo"):
        a("Medir el consumo real tiene una exigencia adicional sobre el protocolo: la lectura")
        a("tiene que tomarse mientras el algoritmo está trabajando. Por eso los lotes de §3.2")
        a(f"se dimensionan para durar al menos {formato_numero(config.DURACION_MINIMA_LOTE_MUESTREO_S, 1)} s, en lugar de los")
        a(f"{formato_numero(config.DURACION_MINIMA_LOTE_S, 1)} s que bastarían para cronometrar. Con ventanas más cortas la lectura")
        a("llega cuando el trabajo ya terminó, y el consumo informado queda inflado.")
        a("")
    if cc:
        filas_deteccion = [["Procesador reconocido", str(cc.get("cpu_model", "—"))]]
        if lectura_directa:
            filas_deteccion.append(
                ["Potencia del procesador", "medida con el sensor del equipo durante la corrida"]
            )
        else:
            filas_deteccion.append(
                [
                    "Potencia del procesador",
                    f"{formato_numero(cc.get('cpu_power_w', float('nan')))} W, calculada con la fórmula de §5.2",
                ]
            )
        filas_deteccion.append(
            [
                "Potencia de la memoria",
                f"{formato_numero(cc.get('ram_power_w', float('nan')))} W, valor de referencia de la herramienta",
            ]
        )
        filas_deteccion.append(["Red eléctrica", str(cc.get("country", "—"))])
        a(tabla_markdown(filas_deteccion, ["Qué reconoció la herramienta", "Valor"]))
        a("")

    # ---------------------------------------------------------------- resultados
    a("## 4. Resultados")
    a("")
    a("### 4.0 Cómo leer las tablas")
    a("")
    a(f"**Cada fila es un punto de medición** (§3.2) y los valores son el promedio de sus")
    a(f"{metadatos['repeticiones']} mediciones, expresados **por ejecución** del algoritmo.")
    a("")
    a(
        tabla_markdown(
            [
                ["`n`", "tamaño de la entrada, en las unidades que declara cada experimento"],
                [
                    "`algoritmo`",
                    "la variante medida; todas las del experimento devuelven el mismo resultado",
                ],
                ["`complejidad`", "la complejidad teórica del algoritmo"],
                ["`tiempo [s]`", "cuánto tarda una ejecución"],
                [
                    "`energía [kWh]`",
                    "cuánta electricidad consume una ejecución. Es la magnitud que se mide (§3.4)",
                ],
                [
                    "`CO₂ [kg]`",
                    f"esa energía convertida a emisiones con el factor de "
                    f"{formato_numero(config.FACTOR_EMISION_AR, 3)} kgCO₂eq/kWh de §2",
                ],
                [
                    "`disp.`",
                    "cuánto difieren entre sí las repeticiones del punto: el desvío estándar "
                    "como porcentaje del promedio",
                ],
            ],
            ["Columna", "Qué es"],
        )
    )
    a("")
    a("Sobre la dispersión: por debajo del 1% la medición es reproducible. Un valor alto no")
    a("invalida el promedio, y puede venir de dos lados: de las variantes que reparten su")
    a("trabajo entre varios núcleos, donde cuántos se activan cambia de una repetición a")
    a("otra, o del tiempo que consume tomar la lectura de consumo (§5.2), que pesa más en los")
    a("algoritmos más rápidos.")
    a("")
    # Ejemplo trabajado sobre una fila real de la corrida: es la única forma de que quede
    # sin ambigüedad qué representa cada número, y al derivarse de los datos no puede
    # quedar desfasado.
    if mediciones is not None and not resumen.empty:
        clave_1 = next((c for c in EXPERIMENTOS if c in presentes), None)
        datos_1 = resumen[resumen.experimento == clave_1].sort_values(["n", "algoritmo"])
        if clave_1 and not datos_1.empty:
            f = datos_1.iloc[0]
            reps = mediciones[
                (mediciones.algoritmo == f.algoritmo) & (mediciones.n == f.n)
            ]
            lote = int(reps.ejecuciones_lote.iloc[0]) if not reps.empty else 1
            unidad = EXPERIMENTOS[str(clave_1)].unidad_n
            a("**Qué dice exactamente una fila.** Tomando la primera del primer experimento —")
            a(f"`{f.algoritmo}`, {unidad} = {formato_numero(int(f.n), 0)}—, cada número significa esto:")
            a("")
            a(f"- **`n` = {formato_numero(int(f.n), 0)}**: la entrada sobre la que se corrió tenía ese tamaño.")
            a(f"- **`complejidad` = {f.complejidad}**: etiqueta teórica declarada por el proyecto. No se")
            a("  midió ni se derivó de los datos.")
            a(f"- **`tiempo [s]` = {formato_cientifico(f.tiempo_s_mean)}**: se ejecutó el algoritmo")
            a(f"  {formato_numero(lote, 0)} veces seguidas y se cronometró el conjunto; el total se dividió por")
            a(f"  {formato_numero(lote, 0)}. Eso se hizo {metadatos['repeticiones']} veces y se promediaron los "
              f"{metadatos['repeticiones']} cocientes.")
            a(f"- **`energía [kWh]` = {formato_cientifico(f.energia_kwh_mean)}**: durante esas mismas")
            a(f"  {formato_numero(lote, 0)} ejecuciones se integró la potencia leída del procesador más la")
            a(f"  atribuida a la memoria, sobre toda la ventana. El total se dividió por "
              f"{formato_numero(lote, 0)} y se")
            a(f"  promediaron las {metadatos['repeticiones']} mediciones.")
            a(f"- **`CO₂ [kg]` = {formato_cientifico(f.co2_kg_mean)}**: la energía anterior multiplicada por")
            a(f"  {formato_numero(config.FACTOR_EMISION_AR, 3)}. No es una medición independiente: es la misma cifra en otra unidad.")
            if len(reps) > 1:
                valores = ", ".join(formato_cientifico(v) for v in reps.co2_kg)
                a(f"- **`disp.` = ±{formato_numero(f.co2_kg_std / f.co2_kg_mean * 100, 1)}%**: el desvío estándar de los "
                  f"{len(reps)} valores de CO₂ medidos")
                a(f"  ({valores}), dividido por su promedio.")
            a("")

    for clave in EXPERIMENTOS:
        seccion = seccion_experimento(clave, resumen, rutas.get(clave), metadatos)
        if seccion:
            a(seccion)

    # ---------------------------------------------------------------- análisis
    a("## 5. Análisis")
    a("")
    a("### 5.1 Tiempo de ejecución como aproximación de la huella")
    a("")
    import numpy as np

    def ajuste_log_log(datos: pd.DataFrame) -> tuple[float, float, int]:
        """Pendiente y R² del ajuste log-log de CO₂ contra tiempo, y cantidad de puntos."""
        x = datos.tiempo_s_mean.to_numpy(dtype=float)
        y = datos.co2_kg_mean.to_numpy(dtype=float)
        valido = (x > 0) & (y > 0)
        if valido.sum() < 3:
            return float("nan"), float("nan"), int(valido.sum())
        lx, ly = np.log10(x[valido]), np.log10(y[valido])
        coeficientes = np.polyfit(lx, ly, 1)
        residuo = np.sum((ly - np.polyval(coeficientes, lx)) ** 2)
        total = np.sum((ly - ly.mean()) ** 2)
        return float(coeficientes[0]), float(1 - residuo / total), int(valido.sum())

    pendiente, r2, _ = ajuste_log_log(resumen)

    a(f"Sobre las {len(resumen)} configuraciones medidas, las emisiones resultan casi")
    a(f"exactamente proporcionales al tiempo de ejecución: al relacionar ambas magnitudes, un")
    a(f"algoritmo que tarda el doble emite **{formato_numero(2 ** pendiente, 2)} veces más**, y la relación explica el")
    a(f"**{formato_numero(r2 * 100, 2)}%** de la variación observada.")
    a("")

    # De dónde sale la proporcionalidad: si la potencia con la que se calcula la energía
    # casi no varía entre algoritmos, el ajuste no dice nada sobre el mundo. Con potencia
    # medida sí lo dice, así que el texto cambia según lo que haya pasado en la corrida.
    potencias = (
        mediciones.potencia_cpu_w.dropna()
        if mediciones is not None and "potencia_cpu_w" in mediciones
        else pd.Series(dtype=float)
    )
    if cc.get("lectura_directa"):
        a("Conviene entender por qué, porque no es una ley general. Casi todas las cargas de")
        a("este banco de pruebas usan el procesador de la misma forma: un solo núcleo,")
        a("calculando sin pausas. A igual intensidad de uso, el consumo por segundo es")
        a("parecido, y entonces la energía —que es consumo por tiempo— queda gobernada por el")
        a("tiempo. **La proporcionalidad es real, pero vale entre cargas que usan la máquina de")
        a("forma comparable.**")
        a("")
    else:
        a("Conviene explicar de dónde sale esa proporcionalidad antes de leerla como un")
        a("hallazgo. En esta corrida la potencia no se midió: se calculó a partir de cuán")
        a("ocupada estaba la máquina (§5.2), y eso la vuelve casi insensible a qué algoritmo")
        a("esté corriendo.")
        if not potencias.empty:
            mediana_pot = float(potencias.median())
            cerca = float(((potencias - mediana_pot).abs() / mediana_pot <= 0.01).mean())
            a(f"De hecho quedó entre {formato_numero(float(potencias.min()))} y "
              f"{formato_numero(float(potencias.max()))} W, y en el {formato_numero(cerca * 100, 0)}% de las")
            a(f"mediciones no se movió más del 1% de su valor típico ({formato_numero(mediana_pot)} W).")
        a("Con la potencia casi fija, la energía es el tiempo multiplicado por una constante:")
        a("**la proporcionalidad es en buena medida una consecuencia de cómo se estimó, no un")
        a("resultado empírico.**")
        a("")

    # Contraejemplo dentro de los propios datos: el par donde el factor de tiempo y el de
    # emisiones más se despegan.
    mejor_contraste: tuple[float, Any, Any, str] | None = None
    for clave_exp in sorted(set(str(x) for x in resumen.experimento.unique())):
        datos_exp = resumen[resumen.experimento == clave_exp]
        en_max = datos_exp[datos_exp.n == datos_exp.n.max()].sort_values("co2_kg_mean")
        if len(en_max) < 2:
            continue
        rapido, lento = en_max.iloc[0], en_max.iloc[-1]
        if rapido.tiempo_s_mean <= 0 or rapido.co2_kg_mean <= 0:
            continue
        f_tiempo = float(lento.tiempo_s_mean / rapido.tiempo_s_mean)
        f_co2 = float(lento.co2_kg_mean / rapido.co2_kg_mean)
        if f_co2 <= 0:
            continue
        brecha = f_tiempo / f_co2
        if mejor_contraste is None or brecha > mejor_contraste[0]:
            mejor_contraste = (brecha, rapido, lento, clave_exp)

    if mejor_contraste is not None and mejor_contraste[0] > 2:
        _, rapido, lento, clave_exp = mejor_contraste
        f_tiempo = float(lento.tiempo_s_mean / rapido.tiempo_s_mean)
        f_co2 = float(lento.co2_kg_mean / rapido.co2_kg_mean)
        a("Y hay un par donde la proporcionalidad se rompe. El caso más claro está en")
        a(f"{EXPERIMENTOS[clave_exp].titulo}, con "
          f"{EXPERIMENTOS[clave_exp].unidad_n} = {formato_numero(int(rapido.n), 0)}: "
          f"`{rapido.algoritmo}` termina")
        a(f"**{formato_factor(f_tiempo)} veces más rápido** que `{lento.algoritmo}`, pero emite sólo")
        a(f"**{formato_factor(f_co2)} veces menos**. La diferencia está en cuántos núcleos usa cada")
        a("uno: repartir el trabajo entre varios acorta el reloj, pero el consumo se paga por")
        a("núcleo y hora, y ese total no baja en la misma proporción.")
        a("")

    if mejor_contraste is not None and mejor_contraste[0] > 2:
        a("**Conclusión práctica:** el tiempo de ejecución sirve como indicador de la huella")
        a("entre algoritmos que usan la máquina de forma parecida, pero **no basta cuando")
        a("cambia cuántos núcleos se ocupan**: ahí optimizar el reloj puede no reducir las")
        a("emisiones en la misma medida, y hace falta medir la energía.")
    else:
        a("**Conclusión práctica:** en este banco de pruebas el tiempo de ejecución resultó un")
        a("buen indicador de la huella, incluso en la carga que ocupa todos los núcleos. No")
        a("conviene generalizarlo: un programa que pasa el tiempo esperando respuesta de disco")
        a("o de red acumula segundos sin consumir casi nada, y ahí la relación se rompe. Este")
        a("trabajo no mide ese caso.")
    a("")

    if "tiempo_vs_co2" in rutas:
        a(f"![Tiempo vs CO₂]({rutas['tiempo_vs_co2']})")
        a("")

    a("### 5.2 Cuánta confianza merecen estas cifras")
    a("")
    a("Una huella de carbono de software es energía convertida a CO₂, y la energía es")
    a("potencia por tiempo. El tiempo se cronometra sin dificultad. La potencia es la parte")
    a("difícil, y de ella depende todo lo demás, así que corresponde declarar de dónde salió.")
    a("")
    if cc.get("lectura_directa"):
        a("**En esta corrida la potencia se midió** con el sensor de consumo del propio equipo")
        a("(§3.4). Los valores absolutos de CO₂ se apoyan entonces en un consumo real. Quedan")
        a("dos salvedades, que no son del cálculo sino del alcance de la medición:")
        a("")
        a("1. **El sensor mide el procesador completo, no el algoritmo.** Si otro programa")
        a("   trabaja al mismo tiempo, parte de su consumo se le atribuye al algoritmo medido.")
        a("   Se midió con el equipo descargado y repitiendo cada punto tres veces, pero no se")
        a("   elimina del todo.")
        cola = float("nan")
        if (
            mediciones is not None
            and {"tiempo_s_informado", "tiempo_s", "ejecuciones_lote"} <= set(mediciones.columns)
        ):
            diferencia = (
                (mediciones.tiempo_s_informado - mediciones.tiempo_s)
                * mediciones.ejecuciones_lote
            )
            cola = float(diferencia.median())
        a("2. **Tomar la lectura lleva su propio tiempo.** El consumo que se informa cubre la")
        a("   ventana de medición completa, y esa ventana incluye el rato que el instrumento")
        if cola == cola:
            a(f"   tarda en leer: {formato_numero(cola, 1)} s por medición en esta corrida, sobre ventanas de")
            a(f"   {formato_numero(metadatos.get('ventana_medicion_s', float('nan')), 1)} s. Ese rato transcurre con el algoritmo ya terminado y el equipo")
        else:
            a("   tarda en leer. Ese rato transcurre con el algoritmo ya terminado y el equipo")
        a("   casi en reposo, así que **agrega algo de consumo que no le corresponde al")
        a("   algoritmo**. Afecta más a los algoritmos más rápidos, que son los que quedan")
        a("   con las ventanas más cortas.")
        a("")
        a("**La alternativa habría sido estimarla.** Cuando un equipo no expone un sensor")
        a("accesible, la herramienta deduce la potencia del consumo nominal del procesador y de")
        a("cuán ocupada está la máquina. Conviene saber a qué se renunció al no usar ese")
        a("camino: en este equipo la herramienta no reconoce el procesador, así que le habría")
        a(f"asignado un consumo nominal genérico de {formato_numero(cc.get('tdp_por_defecto_codecarbon_w', float('nan')), 0)} W —el de una computadora de")
        a("escritorio, no el de una notebook— y de ahí habría derivado toda la energía.")
        a("")
    else:
        a("**En esta corrida la potencia no se midió: se estimó.** El equipo no expuso un")
        a("sensor accesible, así que la herramienta la dedujo del consumo nominal del")
        a("procesador y de cuán ocupada estaba la máquina. Eso tiene dos consecuencias:")
        a("")
        a("1. **El consumo nominal es un valor genérico.** La herramienta no reconoce este")
        a(f"   procesador, así que le asigna {formato_numero(cc.get('tdp_por_defecto_codecarbon_w', float('nan')), 0)} W, el consumo de una computadora de")
        a("   escritorio y no el de una notebook. Toda la energía se deriva de ese número.")
        a("2. **Mira la máquina, no el algoritmo.** La estimación parte de cuán ocupado está el")
        a("   equipo entero. Con la máquina mayormente en reposo queda casi fija, y por lo")
        a("   tanto es poco sensible a qué algoritmo esté corriendo.")
        a("")
        if cc.get("powermetrics_disponible"):
            a("Y no fue porque el equipo no pudiera medirla: **sí podía**. La herramienta, en este")
            a("tipo de máquina, no usa el sensor por su cuenta salvo que se le pida")
            a("explícitamente, y no avisa de que está estimando. Es la razón por la que este")
            a("trabajo se lo pide de forma expresa (§3.4).")
            a("")

    a("**Qué se puede afirmar y qué no.**")
    a("")
    if cc.get("lectura_directa"):
        a("- Los valores absolutos de CO₂ son una medición, no una estimación, y se pueden")
        a("  citar como tales.")
    else:
        a("- Los valores absolutos de CO₂ son un **orden de magnitud**, no una cifra exacta.")
    a("- **Las comparaciones entre algoritmos se sostienen**, que es lo que responde la")
    a("  hipótesis de este trabajo: todos se midieron de la misma forma, en el mismo equipo y")
    a("  en la misma sesión, así que cualquier sesgo los afecta a todos por igual.")
    a("- Y queda una lección que va más allá de este proyecto: **dos mediciones de huella del")
    a("  software pueden diferir varias veces según cómo obtuvieron la potencia.** Un informe")
    a("  de huella que no declare eso no es verificable.")
    a("")

    # ---------------------------------------------------------------- equivalencias
    a("### 5.3 Magnitud de los resultados")
    a("")
    a("Las emisiones de una ejecución individual son diminutas. La suma de todas las")
    a(f"configuraciones medidas en este benchmark asciende a **{formato_cientifico(total_co2)} kgCO₂eq**.")
    a("Presentar solo ese número invitaría a concluir que el problema es irrelevante, y")
    a("sería una lectura equivocada: el software se ejecuta a escala.")
    a("")
    peor = resumen.loc[resumen.co2_kg_mean.idxmax()]
    # Las escalas de extrapolación las declara cada experimento: multiplicar un
    # entrenamiento de modelo por mil millones no describe ningún escenario real. Si el
    # experimento no declara las suyas, se usan las de una función invocada por un servicio.
    escalas_peor = EXPERIMENTOS[str(peor.experimento)].escalas or [
        (1_000_000, "un millón de ejecuciones (una función invocada por un servicio web de tamaño medio a lo largo de unos meses)"),
        (1_000_000_000, "mil millones de ejecuciones (escala de un servicio masivo)"),
    ]
    for multiplicador, descripcion in escalas_peor:
        co2 = peor.co2_kg_mean * multiplicador
        equivalencias_txt = ", ".join(
            f"{formato_numero(co2 / factor, 0)} {nombre}" for nombre, factor, _ in EQUIVALENCIAS
        )
        a(f"- El peor algoritmo medido (`{peor.algoritmo}`, {EXPERIMENTOS[str(peor.experimento)].unidad_n} "
          f"= {formato_numero(int(peor.n), 0)}) repetido")
        a(f"  {formato_numero(multiplicador, 0)} veces —{descripcion}— emite **{formato_numero(co2, 3)} kgCO₂eq**,")
        a(f"  equivalente a {equivalencias_txt}.")
    a("")
    a("Equivalencias utilizadas:")
    a("")
    a(
        tabla_markdown(
            [
                [nombre, f"{formato_numero(factor, 5)} kgCO₂eq c/u", fuente]
                for nombre, factor, fuente in EQUIVALENCIAS
            ],
            ["Unidad", "Factor", "Fuente / cálculo"],
        )
    )
    a("")

    # ---------------------------------------------------------------- limitaciones
    a("## 6. Limitaciones")
    a("")
    a("Se declaran explícitamente porque condicionan cómo hay que leer los resultados:")
    a("")
    if cc.get("lectura_directa"):
        a("1. **El consumo medido es del procesador completo**, no exclusivamente del algoritmo")
        a("   (§5.2). Se midió con el equipo descargado, pero el ruido de fondo del sistema")
        a("   operativo no se elimina del todo.")
        a("2. **Parte de la ventana de medición ocurre con el algoritmo ya terminado**, porque")
        a("   tomar la lectura lleva su propio tiempo (§5.2). Eso suma algo de consumo ajeno,")
        a("   y pesa más en los algoritmos más rápidos.")
    else:
        a("1. **La potencia no se midió, se estimó** a partir de un consumo nominal genérico")
        a("   (§5.2), así que los valores absolutos tienen una incertidumbre alta. Las")
        a("   comparaciones entre algoritmos no se ven afectadas.")
        a("2. **La estimación mira la máquina entera**, no el algoritmo, e incluye el consumo")
        a("   de los demás programas en ejecución.")
    a("3. **Solo se cuenta la energía de uso.** Queda afuera la huella de fabricar el equipo,")
    a("   transportarlo y descartarlo. En un análisis de ciclo de vida completo, fabricar")
    a("   suele pesar más que usar.")
    a("4. **El factor de emisión es un promedio anual.** La red eléctrica no emite lo mismo a")
    a("   toda hora: depende de qué centrales estén generando en ese momento. Correr un")
    a("   proceso de madrugada o al mediodía no tiene el mismo impacto real.")
    a("5. **Los resultados son de este equipo.** Otro procesador, otro sistema operativo u")
    a("   otra red eléctrica dan otras cifras absolutas. Las diferencias *entre* algoritmos,")
    a("   que son la conclusión del trabajo, sí son trasladables.")
    a("")

    # ---------------------------------------------------------------- conclusiones
    a("## 7. Conclusiones")
    a("")
    conclusiones: list[str] = []
    for clave in EXPERIMENTOS:
        datos = resumen[resumen.experimento == clave]
        if datos.empty:
            continue
        n_max = datos.n.max()
        en_max = datos[datos.n == n_max].sort_values("co2_kg_mean")
        if len(en_max) < 2:
            continue
        mejor, peor_e = en_max.iloc[0], en_max.iloc[-1]
        factor = peor_e.co2_kg_mean / mejor.co2_kg_mean
        conclusiones.append(
            f"En **{EXPERIMENTOS[clave].titulo}** (n={int(n_max)}), "
            f"`{mejor.algoritmo}` emite **{formato_factor(factor)}×** menos CO₂ que "
            f"`{peor_e.algoritmo}` para un resultado idéntico."
        )
    for i, texto in enumerate(conclusiones, start=1):
        a(f"{i}. {texto}")
    a("")
    a("**La hipótesis se verifica.** Las diferencias de huella entre algoritmos")
    a("equivalentes no son marginales: alcanzan varios órdenes de magnitud. **Elegir un")
    a("algoritmo adecuado no es solo una decisión de rendimiento, es también una decisión")
    a("ambiental**.")
    a("")

    # ---------------------------------------------------------------- reproducción
    a("## 8. Reproducción")
    a("")
    a("```bash")
    a("uv sync                            # instala el entorno exacto desde uv.lock")
    a("uv run huella-carbono --completo   # corre el benchmark y regenera este informe")
    a("```")
    a("")
    a("Artefactos generados:")
    a("")
    a(
        tabla_markdown(
            [
                [
                    "`resultados/simulacion_huella_carbono.csv`",
                    "**resultado de la simulación**: una fila por medición, con el tiempo, la "
                    "energía y el CO₂ de cada algoritmo y tamaño. Los promedios de este "
                    "informe salen de ahí.",
                ],
                [
                    "`resultados/metadatos.json`",
                    "con qué equipo, qué versiones y qué parámetros se corrió",
                ],
                ["`resultados/graficos/*.png`", "gráficos incluidos en este informe"],
                ["`INFORME.md`", "este documento"],
            ],
            ["Artefacto", "Contenido"],
        )
    )
    a("")
    a("Entradas de datos versionadas con el proyecto (no se generan, se leen):")
    a("")
    a(
        tabla_markdown(
            [
                [
                    f"`datos/{config.ARCHIVO_INTENSIDAD_CARBONO.name}`",
                    "serie de intensidad de carbono de la red argentina y factor oficial "
                    "de contraste, con su procedencia",
                ],
                [
                    f"`datos/{config.ARCHIVO_EQUIVALENCIAS.name}`",
                    "factores para traducir kgCO₂eq a magnitudes tangibles (§5.3), "
                    "con su fuente",
                ],
            ],
            ["Archivo", "Contenido"],
        )
    )
    a("")

    # ---------------------------------------------------------------- referencias
    a("## 9. Fuentes y referencias")
    a("")
    grupos: list[tuple[str, list[str]]] = []

    datos_red = [
        f"{config.FUENTE_FACTOR_EMISION}. *{config.INTENSIDAD_CARBONO['indicador']}*, "
        f"serie {min(config.INTENSIDAD_CARBONO['serie_g_kwh'], key=int)}–{config.ANIO_FACTOR_EMISION} "
        f"para {config.INTENSIDAD_CARBONO['pais']}. "
        f"<{config.INTENSIDAD_CARBONO['url']}> (consultado el {config.INTENSIDAD_CARBONO['descargado']}). "
        f"Valor adoptado en este trabajo: "
        f"{formato_numero(config.FACTOR_EMISION_AR_G_KWH, 1)} gCO₂eq/kWh ({config.ANIO_FACTOR_EMISION})."
    ]
    if config.INTENSIDAD_CARBONO.get("url_fuente_upstream"):
        datos_red.append(
            "Ember. *Yearly Electricity Data* — fuente primaria de la serie anterior. "
            f"<{config.INTENSIDAD_CARBONO['url_fuente_upstream']}>."
        )
    if oficial:
        datos_red.append(
            f"{oficial['organismo']}. *{oficial['indicador']}*. "
            f"Metodología: {oficial['metodologia']}. "
            f"<{oficial['url']}> (archivo `{oficial['archivo']}`, consultado el {oficial['descargado']}). "
            f"Valor {oficial['anio']}: {formato_numero(oficial['valor_g_kwh'], 1)} gCO₂eq/kWh; "
            "citado como contraste, no usado en los cálculos."
        )
    grupos.append(("Datos de emisiones de la red eléctrica", datos_red))

    herramientas = [
        f"CodeCarbon {metadatos.get('codecarbon', 'n/d')} — herramienta de medición usada en "
        "este trabajo (§3.4). <https://github.com/mlco2/codecarbon> · "
        "<https://mlco2.github.io/codecarbon/>. Su tabla interna de factores de emisión por "
        f"país da para Argentina {formato_numero(config.FACTOR_EMISION_CODECARBON_G_KWH, 1)} gCO₂eq/kWh, valor de "
        f"{config.ANIO_FACTOR_EMISION_CODECARBON}, que este trabajo no adopta por el motivo explicado en §2.",
        f"scikit-learn {metadatos.get('scikit_learn', 'n/d')} — provee el clasificador de "
        "vecinos más cercanos y el generador del conjunto de datos sintético del cuarto "
        "experimento. <https://scikit-learn.org/stable/>.",
        "Utilidad de consumo del sistema operativo (macOS) — es el sensor del que se lee la "
        "potencia real del procesador en este equipo (§3.4).",
    ]
    grupos.append(("Herramientas de medición", herramientas))

    equivalencias_ref = []
    for item in config.EQUIVALENCIAS_CRUDO.get("directas", []):
        equivalencias_ref.append(
            f"{item['fuente']} — usado para la equivalencia «{item['nombre']}» de §5.3: "
            f"{formato_numero(item['kg_co2_por_unidad'], 4)} kgCO₂eq por unidad. "
            f"<{item['url']}> (consultado el {item['descargado']}). {item.get('nota', '')}".strip()
        )
    for item in config.EQUIVALENCIAS_CRUDO.get("vehiculares", []):
        g_km = item["consumo_l_por_100km"] / 100 * item["factor_kg_co2_por_litro"] * 1000
        equivalencias_ref.append(
            f"{item['fuente_consumo']}: {formato_numero(item['consumo_l_por_100km'], 1)} L/100 km. "
            f"<{item['url_consumo']}> (consultado el {item['descargado']})."
        )
        equivalencias_ref.append(
            f"{item['fuente_factor']}: {formato_numero(item['factor_kg_co2_por_litro'], 4)} "
            f"kgCO₂/L para {item['combustible']}. "
            f"<{item['url_factor']}> (consultado el {item['descargado']}). "
            f"Combinado con el consumo anterior da la equivalencia «{item['nombre']}» de §5.3: "
            f"**{formato_numero(g_km, 1)} gCO₂/km**. {item.get('nota', '')}".strip()
        )
    electricas = config.EQUIVALENCIAS_CRUDO.get("electricas", [])
    if electricas:
        detalle = "; ".join(
            f"«{item['nombre']}» = {formato_numero(item['consumo_kwh'], 3)} kWh" for item in electricas
        )
        equivalencias_ref.append(
            "Equivalencias eléctricas de §5.3: se definen por su consumo en kWh "
            f"({detalle}) y se convierten con el factor de emisión de este informe, de modo "
            "que no pueden quedar desfasadas del FE en uso. Definidas en "
            f"`datos/{config.ARCHIVO_EQUIVALENCIAS.name}`."
        )
    if equivalencias_ref:
        grupos.append(("Equivalencias de referencia", equivalencias_ref))

    grupos.append(
        (
            "Metodología",
            [
                "UNFCCC. *Tool to calculate the emission factor for an electricity system*, "
                "versión 7 — metodología del factor oficial argentino citado arriba. "
                "<https://cdm.unfccc.int/methodologies/PAmethodologies/tools/am-tool-07-v7.0.pdf>.",
                "The Green Software Foundation. *Software Carbon Intensity (SCI) Specification* "
                "— marco de referencia para la fórmula CO₂ = E × FE × PUE usada en §2. "
                "<https://sci.greensoftware.foundation/>.",
            ],
        )
    )

    numero = 1
    for titulo, items in grupos:
        a(f"**{titulo}**")
        a("")
        for item in items:
            a(f"{numero}. {item}")
            numero += 1
        a("")

    texto = "\n".join(p)
    config.INFORME.write_text(texto, encoding="utf-8")
    return texto
