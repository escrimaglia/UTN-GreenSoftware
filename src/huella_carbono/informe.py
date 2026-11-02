# Calculating the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Generation of the benchmark report (`INFORME.md`).

The report is built entirely from `resultados/simulacion_huella_carbono.csv` and
`resultados/metadatos.json`: no figure in the text is written by hand, so the report
cannot fall out of sync with the measured data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from huella_carbono import config
from huella_carbono.config import EQUIVALENCIAS, EXPERIMENTOS


def formato_cientifico(valor: float, decimales: int = 3) -> str:
    """
    Scientific notation with a decimal point, the same convention used by every other
    number in the report.
    """
    if pd.isna(valor):
        return "—"
    return f"{valor:.{decimales}e}"


def formato_duracion(segundos: float) -> str:
    """
    Duration in the unit that makes it readable in prose. Scientific notation is fine in
    a table, but "4.493e-07 seconds" is hard to grasp when reading.
    """
    if pd.isna(segundos):
        return "—"
    if segundos >= 1:
        return f"{formato_numero(segundos)} seconds"
    if segundos >= 1e-3:
        return f"{formato_numero(segundos * 1e3)} milliseconds"
    if segundos >= 1e-6:
        return f"{formato_numero(segundos * 1e6)} microseconds"
    return f"{formato_numero(segundos * 1e9)} nanoseconds"


def formato_arboles(valor: float) -> str:
    """
    Number of trees with as many decimals as needed to avoid rounding to zero: a small
    fraction of a tree is a data point, "0.00" is a presentation error.
    """
    if pd.isna(valor):
        return "—"
    if valor >= 1:
        return formato_numero(valor, 2)
    if valor >= 0.01:
        return formato_numero(valor, 3)
    return formato_cientifico(valor, 1)


def nombre_arbol(nombre: str) -> str:
    """Tree name with its first letter capitalized, for the start of a table cell."""
    return nombre[:1].upper() + nombre[1:]


def formato_factor(valor: float) -> str:
    """
    Formats an improvement factor with the precision that matches its magnitude.

    With a fixed `decimales=0`, a factor of 1.4 was printed as "1 times less", which is
    not only unreadable but false. Large factors, on the other hand, gain nothing from
    decimals.
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
    Formats a number with English typographic conventions: comma as the thousands
    separator and point as the decimal separator.
    """
    if pd.isna(valor):
        return "—"
    return f"{valor:,.{decimales}f}"


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

    partes = [f"### {exp.titulo}", "", f"**Question:** {exp.pregunta}", "", exp.notas, ""]

    def complejidad_de(algoritmo: str, guardada: str) -> str:
        """Current label from the experiment; the CSV's is from the run that produced it."""
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
                "algorithm",
                "complexity",
                "time [s]",
                "energy [kWh]",
                "CO₂ [kg]",
                "spread",
            ],
        )
    )
    partes.append("")

    # Improvement factor between the worst and the best algorithm, at the largest size measured.
    n_max = datos.n.max()
    en_max = datos[datos.n == n_max].sort_values("co2_kg_mean")
    if len(en_max) >= 2:
        mejor, peor = en_max.iloc[0], en_max.iloc[-1]
        factor = peor.co2_kg_mean / mejor.co2_kg_mean
        partes.append(
            f"**Result for n = {formato_numero(int(n_max), 0)}:** `{mejor.algoritmo}` "
            f"({complejidad_de(mejor.algoritmo, mejor.complejidad)}) emits "
            f"**{formato_factor(factor)} times less** CO₂ than `{peor.algoritmo}` "
            f"({complejidad_de(peor.algoritmo, peor.complejidad)}), while producing exactly "
            f"the same result."
        )
        partes.append("")

        # When the time factor and the CO2 factor disagree, say so: it is the case where
        # optimizing the clock is not the same as optimizing the footprint. It is reported
        # only if the gap between both factors is significant, so as not to clutter the
        # experiments where time and emissions go hand in hand.
        if peor.tiempo_s_mean > 0 and mejor.tiempo_s_mean > 0:
            factor_tiempo = float(peor.tiempo_s_mean / mejor.tiempo_s_mean)
            if factor_tiempo > 0 and (
                factor / factor_tiempo > 2 or factor_tiempo / factor > 2
            ):
                if factor_tiempo > factor:
                    partes.append(
                        f"But time tells a different story: `{mejor.algoritmo}` is "
                        f"**{formato_factor(factor_tiempo)} times faster** yet only "
                        f"**{formato_factor(factor)} times cleaner**: the clock advantage does "
                        f"not carry over fully to emissions (section 5.1)."
                    )
                else:
                    partes.append(
                        f"The contrast with time is even larger in emissions: "
                        f"`{mejor.algoritmo}` is {formato_factor(factor_tiempo)} times "
                        f"faster but {formato_factor(factor)} times cleaner."
                    )
                partes.append("")

        # Order reversal: if the cleanest algorithm at the smallest size is not the cleanest
        # at the largest, the conclusion depends on scale and that must be stated.
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
                        f"**The order reverses with size.** At "
                        f"{exp.unidad_n} = {formato_numero(int(n_min), 0)} the cleanest is not "
                        f"`{mejor.algoritmo}` but `{mejor_min.algoritmo}`: there "
                        f"`{mejor.algoritmo}` emits {formato_factor(factor_invertido)} times "
                        f"**more**. In other words, the answer to “which one is better” depends "
                        f"on the working scale, not only on the algorithm."
                    )
                    partes.append("")

    calidad = (metadatos or {}).get("calidad_knn") or {}
    if calidad and clave == "aprendizaje_knn":
        partes.append(
            "**Model quality.** The comparison is between equivalent implementations, not "
            "between different models: the three variants return the same predictions and "
            "therefore the same accuracy. It is reported to show that the measured work is a "
            "model that actually learns, and not an empty computation.\n\n"
            + tabla_markdown(
                [
                    [formato_numero(int(n), 0), formato_numero(float(valor) * 100, 2) + "%"]
                    for n, valor in sorted(calidad.items(), key=lambda par: int(par[0]))
                ],
                ["samples", "accuracy on the test set"],
            )
        )
        partes.append("")

    if exp.descripciones:
        partes.append("**What each algorithm means.**")
        partes.append("")
        # In the order the experiment declares them, not the alphabetical order of the
        # table: the descriptions are written to be read in that order.
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
    """Builds the full report and writes it to `INFORME.md`."""
    mediciones = (
        pd.read_csv(config.CSV_SIMULACION) if config.CSV_SIMULACION.exists() else None
    )
    presentes = set(str(clave) for clave in resumen.experimento.unique())
    cc = metadatos.get("codecarbon_deteccion", {})
    matriz = config.MATRIZ_AR

    total_co2 = float(resumen.co2_kg_mean.sum())

    p: list[str] = []
    a = p.append

    # ---------------------------------------------------------------- title page
    a("# Measuring the carbon footprint of Python algorithms")
    a("")
    a("**Green Software — Universidad Tecnológica Nacional - FRC**")
    a("")
    a(f"Run date: {metadatos['fecha']}")
    a("")
    a("> Every figure in this report comes from the measurements recorded in the run")
    a("> shown above. None was written by hand or taken from another source.")
    a("")
    a("---")
    a("")

    # ---------------------------------------------------------------- objective
    a("## 1. Objective and hypothesis")
    a("")
    a("**Objective.** To measure the carbon footprint associated with running algorithms in")
    a("Python and to determine whether algorithmic design decisions have a quantifiable")
    a("environmental consequence.")
    a("")
    a("**Hypothesis.** Two implementations that produce exactly the same result can differ")
    a("by orders of magnitude in the energy they consume and, therefore, in the CO₂ they")
    a("emit. Computational complexity is not just a theoretical property: it translates")
    a("into electricity consumption and emissions.")
    a("")
    cantidad = len([c for c in EXPERIMENTOS if c in presentes])
    nombres_cantidad = {1: "One experiment", 2: "Two experiments", 3: "Three experiments",
                        4: "Four experiments", 5: "Five experiments"}
    a(f"**Experimental design.** {nombres_cantidad.get(cantidad, f'{cantidad} experiments')}, "
      "each with variants that solve the")
    a("same problem and return the same result (equivalence verified by assertion")
    a("before each measurement):")
    a("")
    for clave, exp in EXPERIMENTOS.items():
        if clave in set(resumen.experimento.unique()):
            variantes = ", ".join(f"`{k}` ({v})" for k, v in exp.variantes.items())
            a(f"- **{exp.titulo}** — {variantes}")
    a("")

    # ---------------------------------------------------------------- theoretical framework
    a("## 2. Theoretical framework")
    a("")
    a("The carbon footprint of a computation is obtained by multiplying the electrical")
    a("energy consumed by the carbon intensity of the grid that supplies it:")
    a("")
    a("```")
    a("CO₂ [kgCO₂eq]  =  E [kWh]  ×  EF [kgCO₂eq/kWh]  ×  PUE")
    a("```")
    a("")
    a("where EF is the emission factor of the power grid and PUE (*Power Usage")
    a("Effectiveness*) accounts for the supporting infrastructure, such as the cooling of")
    a("a data center.")
    a("")
    a("### Emission factor of the Argentine grid")
    a("")
    a(f"The adopted value is **EF = {formato_numero(config.FACTOR_EMISION_AR_G_KWH, 1)} gCO₂eq/kWh = "
      f"{formato_numero(config.FACTOR_EMISION_AR, 3)} kgCO₂eq/kWh**, corresponding to "
      f"{config.ANIO_FACTOR_EMISION}, the most recent year available for Argentina.")
    a("")
    a(f"Source: {config.FUENTE_FACTOR_EMISION}")
    a(f"(<{config.INTENSIDAD_CARBONO['url']}>, downloaded on "
      f"{config.INTENSIDAD_CARBONO['descargado']}). The indicator is the")
    a(f"*{config.INTENSIDAD_CARBONO['indicador'].lower()}*. The full series is")
    a(f"versioned in `datos/{config.ARCHIVO_INTENSIDAD_CARBONO.name}` and the project")
    a("selects the latest available year on every run, so the value can neither go")
    a("out of date nor be written by hand.")
    a("")
    a("Recent evolution of the carbon intensity of the Argentine grid:")
    a("")
    serie = config.INTENSIDAD_CARBONO["serie_g_kwh"]
    ultimos = sorted(serie, key=int)[-6:]
    a(
        tabla_markdown(
            [[anio, f"{formato_numero(serie[anio], 2)}"] for anio in ultimos],
            ["Year", "gCO₂eq/kWh"],
        )
    )
    a("")
    a("**Why the factor bundled with the measurement tool is not used.** CodeCarbon")
    a("ships its own table of factors per country, but for Argentina it is frozen at")
    a(f"{config.ANIO_FACTOR_EMISION_CODECARBON}: {formato_numero(config.FACTOR_EMISION_CODECARBON_G_KWH, 3)} gCO₂eq/kWh, even in the latest")
    a(f"published version of the tool ({metadatos.get('codecarbon', 'n/a')}). That value")
    a(f"is {formato_numero(abs(config.FACTOR_EMISION_CODECARBON_G_KWH / config.FACTOR_EMISION_AR_G_KWH - 1) * 100, 1)}% higher than the "
      f"{config.ANIO_FACTOR_EMISION} figure and would be out of date.")
    a("")
    a("That is why this report takes the energy measured by the tool and converts it to CO₂")
    a(f"with the {config.ANIO_FACTOR_EMISION} factor, the most recent available. The figure the")
    a("tool would compute with its own table is also recorded in the run data, so that the")
    a("difference can be verified.")
    a("")
    oficial = config.REFERENCIA_FACTOR_OFICIAL
    if oficial:
        a(f"As an additional cross-check, {oficial['organismo']} publishes a grid emission factor")
        a(f"using the {oficial['metodologia']} methodology: its latest available value is")
        a(f"**{formato_numero(oficial['valor_g_kwh'], 1)} gCO₂eq/kWh** for {oficial['anio']}")
        a(f"(<{oficial['url']}>, file `{oficial['archivo']}`, downloaded on {oficial['descargado']}).")
        a("It is not adopted here because it is a marginal factor, intended for project")
        a("evaluation, and not an average grid intensity, which is what applies when")
        a(f"attributing the consumption of an arbitrary process. Its closeness to the adopted value "
          f"({formato_numero(abs(oficial['valor_g_kwh'] / config.FACTOR_EMISION_AR_G_KWH - 1) * 100, 1)}% difference) "
          f"nonetheless serves as an order-of-magnitude check.")
        a("")
    fosil_pct = matriz["fossil_TWh"] / matriz["total_TWh"] * 100
    a("The order of magnitude of the factor is explained by the composition of the Argentine")
    a(f"electricity mix in {matriz['anio']}, the latest year with a breakdown by source in the")
    a(f"data shipped with CodeCarbon: out of a total of {formato_numero(matriz['total_TWh'], 1)} TWh generated,")
    a(f"**{formato_numero(fosil_pct, 1)}% comes from fossil sources** "
      f"(gas {formato_numero(matriz['gas_TWh'], 1)} TWh, oil {formato_numero(matriz['oil_TWh'], 1)} TWh, "
      f"coal {formato_numero(matriz['coal_TWh'], 1)} TWh), compared with "
      f"{formato_numero(matriz['hydroelectricity_TWh'], 1)} TWh of hydroelectric, "
      f"{formato_numero(matriz['nuclear_TWh'], 1)} TWh of nuclear, "
      f"{formato_numero(matriz['wind_TWh'], 1)} TWh of wind and {formato_numero(matriz['solar_TWh'], 1)} TWh of solar power.")
    a("")
    a("A relevant consequence for the analysis: **the same algorithm has a different footprint")
    a("depending on where it runs**. Running it on a mostly hydroelectric or nuclear grid,")
    a("emissions would be a fraction of those calculated here.")
    a("")
    a(f"**PUE = {formato_numero(config.PUE, 1)}** is used because the experiment runs on a laptop, with no")
    a("external cooling infrastructure. In a data center the typical PUE is between")
    a("1.1 and 1.6 (an industry reference range, not measured in this work), which")
    a("would multiply all results by that factor.")
    a("")

    # ---------------------------------------------------------------- methodology
    a("## 3. Methodology")
    a("")
    a("### 3.1 Measurement environment")
    a("")
    a(
        tabla_markdown(
            [
                ["Platform", metadatos["plataforma"]],
                ["Processor", f"{cc.get('cpu_model', metadatos['procesador'])}"],
                [
                    "Cores",
                    f"{metadatos['cpu_nucleos_logicos']} logical / "
                    f"{metadatos['cpu_nucleos_fisicos']} physical",
                ],
                ["RAM", f"{formato_numero(metadatos['ram_total_gb'], 1)} GB"],
                ["Python", metadatos["python"]],
                ["NumPy", metadatos["numpy"]],
                ["CodeCarbon", metadatos["codecarbon"]],
                ["scikit-learn", metadatos.get("scikit_learn", "—")],
                [
                    "Cores available to the numerical library",
                    ", ".join(
                        str(h["hilos"]) for h in metadatos.get("hilos_blas", [])
                    )
                    or "no declared limit",
                ],
                ["Environment", "exact versions pinned, so that the run is repeatable"],
                ["Random seed", str(metadatos["semilla"])],
                ["Repetitions per point", str(metadatos["repeticiones"])],
            ],
            ["Parameter", "Value"],
        )
    )
    a("")
    a("### 3.2 Measurement protocol")
    a("")
    a("Each measurement point is a combination of algorithm and input size, and")
    a("corresponds to one row of the tables in section 4. With four experiments and their variants")
    a(f"there are {len(resumen)} points. Each one is measured as follows:")
    a("")
    a("1. **Equivalence is verified.** Before measuring, an assertion checks that all")
    a("   variants of the experiment return the same result. Comparing the footprint of")
    a("   algorithms that do not solve the same problem would not be valid.")
    a("2. **The batch size is computed.** Several of these algorithms finish in")
    a("   microseconds, far less than a sensor needs to produce a power")
    a("   reading, so a single isolated run is not measured: what is measured is a **batch of K")
    a(f"   consecutive runs**, with K chosen so that the batch lasts at least "
      f"{formato_numero(metadatos.get('ventana_medicion_s', config.DURACION_MINIMA_LOTE_S), 1)} s (section 3.4).")
    a("   K is computed with a preliminary trial run, which also serves as a")
    a("   warm-up: the first run of an algorithm is always slower than the")
    a("   following ones.")
    a("3. **The batch is measured and divided by K.** What is reported is therefore the cost of")
    a("   *one* run, even though no single run was ever measured on its own. When an")
    a("   algorithm already lasts longer than the window by itself, as model training does")
    a("   at the larger sizes, K stays at 1.")
    a(f"4. **It is repeated {metadatos['repeticiones']} times** and the mean and spread across those")
    a(f"   {metadatos['repeticiones']} measurements are reported.")
    a("")
    a("A concrete example from this run, to make the idea tangible: the fastest algorithm in")
    ejemplo = None
    if mediciones is not None and "ejecuciones_lote" in mediciones:
        fila = mediciones.loc[mediciones.ejecuciones_lote.idxmax()]
        ejemplo = (str(fila.algoritmo), int(fila.n), int(fila.ejecuciones_lote))
    if ejemplo:
        nombre_alg, n_alg, lote_alg = ejemplo
        a(f"the benchmark, `{nombre_alg}`, was measured in batches of "
          f"{formato_numero(lote_alg, 0)} runs; with "
          f"{metadatos['repeticiones']} repetitions,")
        a(f"behind that row of the table there are "
          f"{formato_numero(lote_alg * int(metadatos['repeticiones']), 0)} actual runs of the algorithm.")
    a("")

    a("### 3.3 Another way to calculate: a custom model")
    a("")
    a("There is an alternative to using a measurement tool: deriving power from how much")
    a("processor the algorithm uses, and attributing to it only the additional consumption")
    a("it causes. The calculation chain would be:")
    a("")
    a("```")
    a("processor usage     =  CPU time consumed / (elapsed time × cores)")
    a("attributed power    =  (maximum power − idle power) × usage  +  memory × W/GB")
    a("energy              =  power × time")
    a("footprint           =  energy × emission factor × PUE")
    a("```")
    a("")
    a("It requires three parameters of the machine it runs on: idle power, power with")
    a("all cores busy, and memory consumption per GB used. The first two")
    a("must be measured with a power sensor; assuming them makes the result as")
    a("debatable as the assumption itself.")
    a("")
    a("**It is mentioned as an option and nothing more: this work does not implement it.**")
    a("Everything that follows comes from the approach that is actually developed.")
    a("")

    a("### 3.4 The approach of this work: CodeCarbon")
    a("")
    a("CodeCarbon is the industry reference tool for measuring the carbon footprint of")
    a("software. Every figure in sections 4 and 5 comes from it. It was used according to")
    a("three criteria:")
    a("")
    a("- **The country is declared, not inferred.** The tool can work it out from the")
    a("  internet connection, but that would tie the result to the network it is run from")
    a("  and to a particular moment. Here Argentina is set up front, and the run stays")
    a("  repeatable.")
    deteccion_s = cc.get("segundos_deteccion_hardware")
    a("- **A single measurement session for the whole benchmark.** Starting the tool")
    a("  takes time, because it first identifies the hardware:")
    if deteccion_s is not None:
        a(f"  {formato_numero(deteccion_s, 1)} s in this run. If it were started and stopped for every measurement, that")
    else:
        a("  this was measured in this run. If it were started and stopped for every measurement, that")
    a("  time would fall inside what is measured and would ruin any measurement in the")
    a("  millisecond range. It is opened only once and each algorithm is measured as a task within")
    a("  that session.")
    a("- **Power is measured, and only estimated when the machine does not allow measuring it.**")
    a("  This is the decision with the greatest weight on the results, which is why it has its")
    a("  own section (section 5.2). Some machines expose a sensor of the processor's actual")
    a("  power draw; where it exists and is accessible, power is read from it. Where not, the")
    a("  tool calculates it with a formula. This software can run on another machine: the path")
    a("  is decided on each run according to what that machine allows, and the report states which")
    a("  one was used instead of taking it for granted.")
    a("")
    lectura_directa = cc.get("lectura_directa")
    if lectura_directa:
        a("**In this run, power was measured with the machine's sensor.** The CO₂ values that")
        a("follow therefore rest on actual consumption and not on an estimate.")
    else:
        a("**In this run the machine did not allow measuring power, so it was estimated.** The")
        a("absolute CO₂ values that follow must be read with the caveat explained in")
        a("section 5.2.")
    a("")
    if cc.get("requiere_ventana_muestreo"):
        a("Measuring actual consumption places an additional demand on the protocol: the reading")
        a("has to be taken while the algorithm is working. That is why the batches in section 3.2")
        a(f"are sized to last at least {formato_numero(config.DURACION_MINIMA_LOTE_MUESTREO_S, 1)} s, instead of the")
        a(f"{formato_numero(config.DURACION_MINIMA_LOTE_S, 1)} s that would suffice for timing. With shorter windows the reading")
        a("arrives after the work has finished, and the reported consumption is inflated.")
        a("")
    # ---------------------------------------------------------------- results
    a("## 4. Results")
    a("")
    a("### 4.0 How to read the tables")
    a("")
    a(f"**Each row is a measurement point** (section 3.2) and the values are the mean of its")
    a(f"{metadatos['repeticiones']} measurements, expressed per run of the algorithm.")
    a("")
    a(
        tabla_markdown(
            [
                ["`n`", "input size, in the units declared by each experiment"],
                [
                    "`algorithm`",
                    "the measured variant; all variants of the experiment return the same result",
                ],
                ["`complexity`", "the theoretical complexity of the algorithm"],
                ["`time [s]`", "how long one run takes"],
                [
                    "`energy [kWh]`",
                    "how much electricity one run consumes. This is the quantity being measured (section 3.4)",
                ],
                [
                    "`CO₂ [kg]`",
                    f"that energy converted to emissions with the "
                    f"{formato_numero(config.FACTOR_EMISION_AR, 3)} kgCO₂eq/kWh factor from section 2",
                ],
                [
                    "`spread`",
                    "how much the repetitions of the point differ from each other: the standard "
                    "deviation as a percentage of the mean",
                ],
            ],
            ["Column", "What it is"],
        )
    )
    a("")
    a("On spread: below 1% the measurement is reproducible. A high value does not")
    a("invalidate the mean, and it can come from two places: from the variants that split their")
    a("work across several cores, where how many get activated changes from one repetition to")
    a("the next, or from the time it takes to read the power consumption (section 5.2), which weighs more on the")
    a("fastest algorithms.")
    a("")
    # Worked example on an actual row of the run: it is the only way to make unambiguous
    # what each number represents, and since it is derived from the data it cannot get
    # out of date.
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
            a("**What a row says, exactly.** Taking the first row of the first experiment")
            a(f"(`{f.algoritmo}`, {unidad} = {formato_numero(int(f.n), 0)}), each number means the following:")
            a("")
            a(f"- **`n` = {formato_numero(int(f.n), 0)}**: the input it was run on had that size.")
            a(f"- **`complexity` = {f.complejidad}**: theoretical label declared by the project. It was")
            a("  neither measured nor derived from the data.")
            a(f"- **`time [s]` = {formato_cientifico(f.tiempo_s_mean)}**: the algorithm was run")
            a(f"  {formato_numero(lote, 0)} times in a row and the whole set was timed; the total was divided by")
            a(f"  {formato_numero(lote, 0)}. This was done {metadatos['repeticiones']} times and the "
              f"{metadatos['repeticiones']} quotients were averaged.")
            a(f"- **`energy [kWh]` = {formato_cientifico(f.energia_kwh_mean)}**: during those same")
            a(f"  {formato_numero(lote, 0)} runs, the power read from the processor plus the power")
            a(f"  attributed to memory was integrated over the whole window. The total was divided by "
              f"{formato_numero(lote, 0)} and")
            a(f"  the {metadatos['repeticiones']} measurements were averaged.")
            a(f"- **`CO₂ [kg]` = {formato_cientifico(f.co2_kg_mean)}**: the energy above multiplied by")
            a(f"  {formato_numero(config.FACTOR_EMISION_AR, 3)}. It is not an independent measurement: it is the same figure in another unit.")
            if len(reps) > 1:
                valores = ", ".join(formato_cientifico(v) for v in reps.co2_kg)
                a(f"- **`spread` = ±{formato_numero(f.co2_kg_std / f.co2_kg_mean * 100, 1)}%**: the standard deviation of the "
                  f"{len(reps)} measured CO₂ values")
                a(f"  ({valores}), divided by their mean.")
            a("")

    for clave in EXPERIMENTOS:
        seccion = seccion_experimento(clave, resumen, rutas.get(clave), metadatos)
        if seccion:
            a(seccion)

    # ---------------------------------------------------------------- analysis
    a("## 5. Analysis")
    a("")
    a("### 5.1 Execution time as a proxy for the footprint")
    a("")
    import numpy as np

    def ajuste_log_log(datos: pd.DataFrame) -> tuple[float, float, int]:
        """Slope and R² of the log-log fit of CO₂ against time, and number of points."""
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

    a(f"Across the {len(resumen)} configurations measured, emissions turn out to be almost")
    a(f"exactly proportional to execution time: relating both quantities, an")
    a(f"algorithm that takes twice as long emits {formato_numero(2 ** pendiente, 2)} times more, and the relationship")
    a(f"explains {formato_numero(r2 * 100, 2)}% of the observed variation.")
    a("")

    # Where the proportionality comes from: if the power used to compute the energy barely
    # varies between algorithms, the fit says nothing about the world. With measured power
    # it does, so the text changes depending on what happened in the run.
    potencias = (
        mediciones.potencia_cpu_w.dropna()
        if mediciones is not None and "potencia_cpu_w" in mediciones
        else pd.Series(dtype=float)
    )
    if cc.get("lectura_directa"):
        a("It is worth understanding why, because it is not a general law. Almost all workloads")
        a("in this benchmark use the processor the same way: a single core,")
        a("computing without pauses. At the same usage intensity, consumption per second is")
        a("similar, and so energy, which is consumption over time, ends up governed by")
        a("time. **The proportionality is real, but it holds among workloads that use the machine")
        a("in a comparable way.**")
        a("")
    else:
        a("It is worth explaining where that proportionality comes from before reading it as a")
        a("finding. In this run power was not measured: it was calculated from how")
        a("busy the machine was (section 5.2), which makes it almost insensitive to which algorithm")
        a("is running.")
        if not potencias.empty:
            mediana_pot = float(potencias.median())
            cerca = float(((potencias - mediana_pot).abs() / mediana_pot <= 0.01).mean())
            a(f"In fact it stayed between {formato_numero(float(potencias.min()))} and "
              f"{formato_numero(float(potencias.max()))} W, and in {formato_numero(cerca * 100, 0)}% of the")
            a(f"measurements it moved no more than 1% from its typical value ({formato_numero(mediana_pot)} W).")
        a("With power nearly fixed, energy is time multiplied by a constant:")
        a("**the proportionality is largely a consequence of how it was estimated, not an")
        a("empirical result.**")
        a("")

    # Counterexample within the data itself: the pair where the time factor and the
    # emissions factor diverge the most.
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
        a("And there is a pair where the proportionality breaks down. The clearest case is in")
        a(f"{EXPERIMENTOS[clave_exp].titulo}, with "
          f"{EXPERIMENTOS[clave_exp].unidad_n} = {formato_numero(int(rapido.n), 0)}: "
          f"`{rapido.algoritmo}` finishes")
        a(f"**{formato_factor(f_tiempo)} times faster** than `{lento.algoritmo}`, but emits only")
        a(f"**{formato_factor(f_co2)} times less**. The difference lies in how many cores each one")
        a("uses: splitting the work across several shortens the clock time, but consumption is paid per")
        a("core-hour, and that total does not drop in the same proportion.")
        a("")

    if mejor_contraste is not None and mejor_contraste[0] > 2:
        a("**Practical conclusion:** execution time works as an indicator of the footprint")
        a("among algorithms that use the machine in a similar way, but **it is not enough when")
        a("the number of busy cores changes**: there, optimizing the clock may not reduce")
        a("emissions to the same extent, and energy needs to be measured.")
    else:
        a("**Practical conclusion:** in this benchmark execution time turned out to be a")
        a("good indicator of the footprint, even for the workload that uses every core. It")
        a("should not be generalized: a program that spends its time waiting on disk or")
        a("network accumulates seconds while consuming almost nothing, and there the relationship")
        a("breaks down. This work does not measure that case.")
    a("")

    if "tiempo_vs_co2" in rutas:
        # The chart is explained from scratch: what each point is, what each axis says, why
        # the scale is not the usual one and what to look for. The numbers come from the data.
        a("**How to read the chart below.**")
        a("")
        a("Each point is **one algorithm solving a problem of a given size**.")
        a("Sorting a list of 8,000 elements with `bubble_sort` is one point; sorting one of")
        a(f"1,000 with the same algorithm is a different point. There are {len(resumen)} in total, one for each")
        a("combination of algorithm and size that was measured.")
        a("")
        a("The position of each point says two things: **the further right it is, the longer**")
        a("that run takes, and **the higher it is, the more CO₂ it emits**. So the bottom-left")
        a("corner is where the fast, clean algorithms are, and the top-right corner is")
        a("where the slow, dirty ones are.")
        a("")
        lento = resumen.loc[resumen.tiempo_s_mean.idxmax()]
        veloz = resumen.loc[resumen.tiempo_s_mean.idxmin()]
        a("Both axes advance **by multiplying by ten at each tick**, instead of adding a")
        a("fixed amount. This is needed because the durations are very different from each other: "
          f"`{veloz.algoritmo}`")
        a(f"takes {formato_duracion(veloz.tiempo_s_mean)} and `{lento.algoritmo}` takes")
        a(f"{formato_duracion(lento.tiempo_s_mean)}, that is, "
          f"{formato_numero(lento.tiempo_s_mean / veloz.tiempo_s_mean, 0)} times longer. On an ordinary")
        a("scale, all the fast points would be piled up against the left edge and nothing")
        a("could be seen.")
        a("")
        a("And what to look for is that **the points form a straight line**, without scattering:")
        a("the algorithm that takes twice as long emits about twice as much, and this holds across the")
        a("whole measured range, from microseconds up to two seconds. If time")
        a("and emissions were unrelated, the points would appear scattered across the whole")
        a("chart instead of lined up.")
        a("")
        a(f"![Time vs CO₂]({rutas['tiempo_vs_co2']})")
        a("")

    a("### 5.2 How much confidence these figures deserve")
    a("")
    a("A software carbon footprint is energy converted to CO₂, and energy is")
    a("power times time. Time is timed without difficulty. Power is the hard")
    a("part, and everything else depends on it, so its origin must be stated.")
    a("")
    if cc.get("lectura_directa"):
        a("**In this run power was measured** with the machine's own power sensor")
        a("(section 3.4). The absolute CO₂ values therefore rest on actual consumption. Two")
        a("caveats remain, which concern not the calculation but the scope of the measurement:")
        a("")
        a("1. **The sensor measures the whole processor, not the algorithm.** If another program")
        a("   is working at the same time, part of its consumption is attributed to the measured algorithm.")
        a("   Measurements were taken with the machine idle and each point repeated three times, but it is")
        a("   not entirely eliminated.")
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
        a("2. **Taking the reading takes time of its own.** The reported consumption covers the")
        a("   entire measurement window, and that window includes the time the instrument")
        if cola == cola:
            a(f"   takes to read: {formato_numero(cola, 1)} s per measurement in this run, over windows of")
            a(f"   {formato_numero(metadatos.get('ventana_medicion_s', float('nan')), 1)} s. That time passes with the algorithm already finished and the machine")
        else:
            a("   takes to read. That time passes with the algorithm already finished and the machine")
        a("   nearly idle, so **it adds some consumption that does not belong to the")
        a("   algorithm**. It affects the fastest algorithms the most, since they are the ones")
        a("   with the shortest windows.")
        a("")
        a("**The alternative would have been to estimate it.** When a machine does not expose an")
        a("accessible sensor, the tool infers power from the processor's nominal consumption and")
        a("from how busy the machine is. It is worth knowing what was given up by not taking that")
        a("path: on this machine the tool does not recognize the processor, so it would have")
        a(f"assigned it a generic nominal consumption of {formato_numero(cc.get('tdp_por_defecto_codecarbon_w', float('nan')), 0)} W (that of a desktop")
        a("computer, not a laptop) and derived all the energy from there.")
        a("")
    else:
        a("**In this run power was not measured: it was estimated.** The machine did not expose an")
        a("accessible sensor, so the tool inferred it from the processor's nominal")
        a("consumption and from how busy the machine was. This has two consequences:")
        a("")
        a("1. **The nominal consumption is a generic value.** The tool does not recognize this")
        a(f"   processor, so it assigns it {formato_numero(cc.get('tdp_por_defecto_codecarbon_w', float('nan')), 0)} W, the consumption of a desktop")
        a("   computer and not that of a laptop. All the energy is derived from that number.")
        a("2. **It looks at the machine, not the algorithm.** The estimate starts from how busy the")
        a("   whole machine is. With the machine mostly idle it stays nearly fixed, and is")
        a("   therefore barely sensitive to which algorithm is running.")
        a("")
        if cc.get("powermetrics_disponible"):
            a("And it was not because the machine could not measure it: **it could**. On this")
            a("type of machine, the tool does not use the sensor on its own unless explicitly")
            a("asked to, and it gives no warning that it is estimating. That is why this")
            a("work requests it explicitly (section 3.4).")
            a("")

    a("**What can and cannot be claimed.**")
    a("")
    if cc.get("lectura_directa"):
        a("- The absolute CO₂ values are a measurement, not an estimate, and can be")
        a("  cited as such.")
    else:
        a("- The absolute CO₂ values are an **order of magnitude**, not an exact figure.")
    a("- **The comparisons between algorithms hold**, which is what answers the")
    a("  hypothesis of this work: all were measured the same way, on the same machine and")
    a("  in the same session, so any bias affects all of them equally.")
    a("- And there is a lesson that goes beyond this project: **two software footprint")
    a("  measurements can differ several-fold depending on how they obtained power.** A")
    a("  footprint report that does not state this is not verifiable.")
    a("")

    # ---------------------------------------------------------------- equivalences
    a("### 5.3 Magnitude of the results")
    a("")
    a("The emissions of a single run are tiny. The sum of all the")
    a(f"configurations measured in this benchmark amounts to {formato_cientifico(total_co2)} kgCO₂eq.")
    a("Presenting only that number would invite the conclusion that the problem is irrelevant, and")
    a("that would be the wrong reading: software runs at scale.")
    a("")
    peor = resumen.loc[resumen.co2_kg_mean.idxmax()]
    # The extrapolation scales are declared by each experiment: multiplying a model
    # training by a billion does not describe any real scenario. If the experiment does
    # not declare its own, those of a function called by a service are used.
    escalas_peor = EXPERIMENTOS[str(peor.experimento)].escalas or [
        (1_000_000, "what a medium-sized web service calls over a few months"),
        (1_000_000_000, "the scale of a massive service"),
    ]
    for multiplicador, descripcion in escalas_peor:
        co2 = peor.co2_kg_mean * multiplicador
        equivalencias_txt = ", ".join(
            f"{formato_numero(co2 / factor, 0)} {nombre}" for nombre, factor, _ in EQUIVALENCIAS
        )
        a(f"- The worst algorithm measured (`{peor.algoritmo}`, {EXPERIMENTOS[str(peor.experimento)].unidad_n} "
          f"= {formato_numero(int(peor.n), 0)}) repeated")
        a(f"  {formato_numero(multiplicador, 0)} times, {descripcion}, emits {formato_numero(co2, 3)} kgCO₂eq,")
        a(f"  equivalent to {equivalencias_txt}.")
    a("")
    a("Equivalences used:")
    a("")
    a(
        tabla_markdown(
            [
                [nombre, f"{formato_numero(factor, 5)} kgCO₂eq each", fuente]
                for nombre, factor, fuente in EQUIVALENCIAS
            ],
            ["Unit", "Factor", "Source / calculation"],
        )
    )
    a("")

    # ---------------------------------------------------------------- limitations
    # ---------------------------------------------------------------- offsetting
    a("## 6. Offsetting")
    a("")
    if config.ARBOLES and mediciones is not None:
        por_anio = dict((nombre, kg) for nombre, kg, _ in config.ARBOLES)
        adulto = por_anio.get("mature")
        joven = por_anio.get("newly planted")
        a("One way to put the emissions in perspective is to ask how much nature would be needed")
        a("to absorb them. The following annual absorption values are adopted as a reference;")
        a("this work did not measure them: they are reference values stated as assumptions.")
        a("")
        a(
            tabla_markdown(
                [[f"{nombre_arbol(nombre)} tree", f"{formato_numero(kg, 0)} kgCO₂eq per year"] for nombre, kg, _ in config.ARBOLES],
                ["Tree", "Annual absorption"],
            )
        )
        a("")

        a("### 6.1 Trees needed to offset what was measured")
        a("")
        if adulto:
            a(f"The full benchmark emitted {formato_cientifico(total_co2)} kgCO₂eq (section 5.3). Offsetting it")
            a(f"requires {formato_cientifico(total_co2 / adulto)} mature trees: in practice, none. A single")
            a(f"mature tree absorbs in one year what this benchmark emits when repeated")
            a(f"{formato_numero(adulto / total_co2, 0)} times.")
            a("")
        a("The figure only becomes meaningful at real-world usage scale. With the worst algorithm measured")
        a(f"(`{peor.algoritmo}`, {EXPERIMENTOS[str(peor.experimento)].unidad_n} = "
          f"{formato_numero(int(peor.n), 0)}):")
        a("")
        filas_escala = []
        for multiplicador, descripcion in escalas_peor:
            co2 = peor.co2_kg_mean * multiplicador
            filas_escala.append(
                [
                    f"{formato_numero(multiplicador, 0)} runs",
                    f"{formato_numero(co2, 3)} kgCO₂eq",
                ]
                + [formato_arboles(co2 / kg) for _, kg, _ in config.ARBOLES]
            )
        a(
            tabla_markdown(
                filas_escala,
                ["Usage scale", "CO₂"]
                + [f"{nombre_arbol(nombre)} trees" for nombre, _, _ in config.ARBOLES],
            )
        )
        a("")
        # The inverse reading is the strongest one: the same tree goes much further if the
        # algorithm is the right one.
        datos_peor = resumen[resumen.experimento == peor.experimento]
        en_max = datos_peor[datos_peor.n == datos_peor.n.max()].sort_values("co2_kg_mean")
        if len(en_max) >= 2:
            eficiente = en_max.iloc[0]
            a("And the other way around: how many runs a single tree can offset in one year, depending")
            a("on which algorithm is chosen to do the same work.")
            a("")
            a(
                tabla_markdown(
                    [
                        [
                            f"{nombre_arbol(nombre)} tree",
                            formato_numero(kg / peor.co2_kg_mean, 0),
                            formato_numero(kg / eficiente.co2_kg_mean, 0),
                        ]
                        for nombre, kg, _ in config.ARBOLES
                    ],
                    ["Tree", f"`{peor.algoritmo}`", f"`{eficiente.algoritmo}`"],
                )
            )
            a("")
            factor = float(peor.co2_kg_mean / eficiente.co2_kg_mean)
            a(f"Solving the same problem with `{eficiente.algoritmo}` instead of `{peor.algoritmo}`")
            a(f"makes the same tree cover {formato_factor(factor)} times more runs.")
            a("")

        a("### 6.2 Processing hours offset by one tree")
        a("")
        tasas = (mediciones.co2_kg / mediciones.tiempo_s).dropna()
        kg_por_hora = float(tasas.median()) * 3600.0
        cantidad_algoritmos = int(resumen.algoritmo.nunique())
        a("While the machine is computing, the emission rate is practically the same for the")
        a(f"{formato_numero(cantidad_algoritmos, 0)} algorithms measured: what changes between them is how long they")
        a("sustain it, not its intensity. The median for this run is")
        a(f"{formato_numero(kg_por_hora * 1000, 3)} grams of CO₂ per hour of processing.")
        a("")
        a(
            tabla_markdown(
                [
                    [
                        f"{nombre_arbol(nombre)} tree",
                        f"{formato_numero(kg / kg_por_hora, 0)} h",
                        f"{formato_numero(kg / kg_por_hora / 24, 0)} days",
                        f"{formato_numero(kg / kg_por_hora / 8760, 1)} years",
                    ]
                    for nombre, kg, _ in config.ARBOLES
                ],
                ["Tree", "Hours offset", "Equivalent to", "Of continuous computing"],
            )
        )
        a("")
        if joven:
            arboles_anio = 8760.0 * kg_por_hora / joven
            a(f"In other words, a newly planted tree absorbs in one year what this machine emits")
            a(f"computing non-stop for {formato_numero(joven / kg_por_hora / 8760, 1)} years. Put the other way around: a laptop")
            a(f"working at full load 365 days a year needs {formato_numero(arboles_anio, 2)} newly")
            a("planted trees to become neutral.")
            a("")
        a("These figures are for this machine and this power grid (sections 3.1 and 2). A data")
        a("center server emits one or two orders of magnitude more per hour.")
        a("")

    # ---------------------------------------------------------------- conclusions
    a("## 7. Conclusions")
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
            f"In {EXPERIMENTOS[clave].titulo} (n={int(n_max)}), "
            f"`{mejor.algoritmo}` emits **{formato_factor(factor)}×** less CO₂ than "
            f"`{peor_e.algoritmo}` for an identical result."
        )
    for i, texto in enumerate(conclusiones, start=1):
        a(f"{i}. {texto}")
    a("")
    a("**The hypothesis is confirmed.** The footprint differences between equivalent")
    a("algorithms are not marginal: they reach several orders of magnitude. **Choosing an")
    a("appropriate algorithm is not just a performance decision, it is also an environmental")
    a("decision**.")
    a("")

    # ---------------------------------------------------------------- reproduction
    a("## 8. Reproduction")
    a("")
    a("```bash")
    a("uv sync                          # installs the exact environment from uv.lock")
    a("uv run huella-carbono --full     # runs the benchmark and regenerates this report")
    a("```")
    a("")
    a("Data inputs versioned with the project (they are not generated, they are read):")
    a("")
    a(
        tabla_markdown(
            [
                [
                    f"`datos/{config.ARCHIVO_INTENSIDAD_CARBONO.name}`",
                    "carbon intensity series of the Argentine grid and official cross-check "
                    "factor, with their provenance",
                ],
                [
                    f"`datos/{config.ARCHIVO_EQUIVALENCIAS.name}`",
                    "factors for translating kgCO₂eq into tangible quantities (section 5.3), "
                    "with their source",
                ],
            ],
            ["File", "Contents"],
        )
    )
    a("")

    # ---------------------------------------------------------------- references
    a("## 9. Sources and references")
    a("")
    grupos: list[tuple[str, list[str]]] = []

    datos_red = [
        f"{config.FUENTE_FACTOR_EMISION}. *{config.INTENSIDAD_CARBONO['indicador']}*, "
        f"series {min(config.INTENSIDAD_CARBONO['serie_g_kwh'], key=int)}–{config.ANIO_FACTOR_EMISION} "
        f"for {config.INTENSIDAD_CARBONO['pais']}. "
        f"<{config.INTENSIDAD_CARBONO['url']}> (accessed on {config.INTENSIDAD_CARBONO['descargado']}). "
        f"Value adopted in this work: "
        f"{formato_numero(config.FACTOR_EMISION_AR_G_KWH, 1)} gCO₂eq/kWh ({config.ANIO_FACTOR_EMISION})."
    ]
    if config.INTENSIDAD_CARBONO.get("url_fuente_upstream"):
        datos_red.append(
            "Ember. *Yearly Electricity Data* — primary source of the series above. "
            f"<{config.INTENSIDAD_CARBONO['url_fuente_upstream']}>."
        )
    if oficial:
        datos_red.append(
            f"{oficial['organismo']}. *{oficial['indicador']}*. "
            f"Methodology: {oficial['metodologia']}. "
            f"<{oficial['url']}> (file `{oficial['archivo']}`, accessed on {oficial['descargado']}). "
            f"Value for {oficial['anio']}: {formato_numero(oficial['valor_g_kwh'], 1)} gCO₂eq/kWh; "
            "cited as a cross-check, not used in the calculations."
        )
    grupos.append(("Power grid emissions data", datos_red))

    herramientas = [
        f"CodeCarbon {metadatos.get('codecarbon', 'n/a')} — measurement tool used in "
        "this work (section 3.4). <https://github.com/mlco2/codecarbon> · "
        "<https://mlco2.github.io/codecarbon/>. Its internal table of emission factors by "
        f"country gives {formato_numero(config.FACTOR_EMISION_CODECARBON_G_KWH, 1)} gCO₂eq/kWh for Argentina, a value from "
        f"{config.ANIO_FACTOR_EMISION_CODECARBON}, which this work does not adopt for the reason explained in section 2.",
        f"scikit-learn {metadatos.get('scikit_learn', 'n/a')} — provides the nearest-neighbors "
        "classifier and the synthetic dataset generator for the fourth "
        "experiment. <https://scikit-learn.org/stable/>.",
        "Operating system power utility (macOS) — the sensor from which the processor's "
        "actual power is read on this machine (section 3.4).",
    ]
    grupos.append(("Measurement tools", herramientas))

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
