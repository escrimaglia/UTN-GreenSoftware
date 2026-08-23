# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Generación de los gráficos del informe.

Todos los gráficos se construyen a partir del agregado de
`resultados/simulacion_huella_carbono.csv`, de modo que no
puedan desincronizarse de los datos medidos.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # backend sin ventana: el script corre sin entorno gráfico

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from huella_carbono import config

PALETA = {
    "bubble_sort": "#c1443c",
    "merge_sort": "#e0913a",
    "timsort_nativo": "#2f7d5c",
    "fib_recursivo": "#c1443c",
    "fib_memoizado": "#e0913a",
    "fib_iterativo": "#2f7d5c",
    "matmul_python": "#c1443c",
    "matmul_numpy": "#2f7d5c",
    # KNN: el color caliente es la variante multihilo, para que el contraste se lea también
    # en el gráfico de escalado.
    "knn_brute": "#8a4fa8",
    "knn_kd_tree": "#e0913a",
    "knn_ball_tree": "#2f7d5c",
}
POR_DEFECTO = "#4a6fa5"


def aplicar_estilo() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 130,
            "savefig.dpi": 130,
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.autolayout": True,
        }
    )


def guardar_figura(fig: plt.Figure, nombre: str) -> str:
    config.DIR_GRAFICOS.mkdir(parents=True, exist_ok=True)
    ruta = config.DIR_GRAFICOS / nombre
    fig.savefig(ruta, bbox_inches="tight")
    plt.close(fig)
    return str(ruta.relative_to(config.RAIZ))


def color_algoritmo(algoritmo: str) -> str:
    return PALETA.get(algoritmo, POR_DEFECTO)


def escalado_co2(resumen: pd.DataFrame, clave: str, nombre_archivo: str) -> str:
    """CO2 por ejecución en función del tamaño de entrada, en escala log-log."""
    exp = config.EXPERIMENTOS[clave]
    datos = resumen[resumen.experimento == clave]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))

    for algoritmo, grupo in datos.groupby("algoritmo"):
        grupo = grupo.sort_values("n")
        complejidad = grupo.complejidad.iloc[0]
        desvio = grupo.co2_kg_std.fillna(0.0)
        ax.errorbar(
            grupo.n,
            grupo.co2_kg_mean,
            yerr=desvio,
            marker="o",
            capsize=3,
            linewidth=1.8,
            label=f"{algoritmo}  {complejidad}",
            color=color_algoritmo(algoritmo),
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    # Ticks en los tamaños realmente medidos: los ticks automáticos de la escala
    # logarítmica (2×10³, 3×10³, ...) no coinciden con los puntos del experimento.
    tamanios = sorted(datos.n.unique())
    ax.set_xticks(tamanios)
    ax.set_xticklabels([f"{t:,}" for t in tamanios])
    ax.minorticks_off()
    ax.set_xlabel(exp.unidad_n)
    ax.set_ylabel("kgCO₂eq por ejecución")
    ax.set_title(f"{exp.titulo}: huella de carbono vs. tamaño de entrada")
    ax.legend(frameon=False)
    return guardar_figura(fig, nombre_archivo)


def comparativa_barras(resumen: pd.DataFrame, clave: str, nombre_archivo: str) -> str:
    """Barras agrupadas de CO2 por algoritmo y tamaño, en escala logarítmica."""
    exp = config.EXPERIMENTOS[clave]
    datos = resumen[resumen.experimento == clave]
    tamanios = sorted(datos.n.unique())
    algoritmos = list(exp.variantes)

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ancho = 0.8 / len(algoritmos)
    x = np.arange(len(tamanios))

    for i, algoritmo in enumerate(algoritmos):
        serie = datos[datos.algoritmo == algoritmo].set_index("n").reindex(tamanios)
        valores = serie.co2_kg_mean.to_numpy(dtype=float)
        ax.bar(
            x + i * ancho - 0.4 + ancho / 2,
            valores,
            ancho,
            label=f"{algoritmo}  {exp.variantes[algoritmo]}",
            color=color_algoritmo(algoritmo),
        )

    ax.set_yscale("log")
    ax.set_xticks(x, [str(t) for t in tamanios])
    ax.set_xlabel(exp.unidad_n)
    ax.set_ylabel("kgCO₂eq por ejecución (escala log)")
    ax.set_title(f"{exp.titulo}: comparación de emisiones")
    ax.legend(frameon=False)
    return guardar_figura(fig, nombre_archivo)


def tiempo_vs_co2(resumen: pd.DataFrame, nombre_archivo: str = "05_tiempo_vs_co2.png") -> str:
    """
    Dispersión tiempo vs. CO2 sobre todos los experimentos.

    La correlación es casi perfecta, pero eso es en buena medida una propiedad del
    modelo de CodeCarbon —que estima la potencia con la carga global de la máquina— y
    no una ley general. Ver §5.1 y §5.2 del informe.
    """
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    marcadores = {
        "ordenamiento": "o",
        "fibonacci": "s",
        "matrices": "^",
        "aprendizaje_knn": "D",
    }

    for clave, grupo in resumen.groupby("experimento"):
        ax.scatter(
            grupo.tiempo_s_mean,
            grupo.co2_kg_mean,
            s=48,
            marker=marcadores.get(str(clave), "o"),
            alpha=0.85,
            label=config.EXPERIMENTOS[str(clave)].titulo,
            edgecolor="white",
            linewidth=0.6,
        )

    x = resumen.tiempo_s_mean.to_numpy(dtype=float)
    y = resumen.co2_kg_mean.to_numpy(dtype=float)
    valido = (x > 0) & (y > 0)
    if valido.sum() > 1:
        lx, ly = np.log10(x[valido]), np.log10(y[valido])
        coef = np.polyfit(lx, ly, 1)
        r2 = 1 - np.sum((ly - np.polyval(coef, lx)) ** 2) / np.sum((ly - ly.mean()) ** 2)
        xs = np.logspace(lx.min(), lx.max(), 100)
        ax.plot(
            xs,
            10 ** (coef[1]) * xs ** coef[0],
            "--",
            color="#555555",
            linewidth=1.2,
            label=f"ajuste log-log: pendiente {coef[0]:.3f}, R² = {r2:.4f}",
        )
        texto = (
            f"Pendiente {coef[0]:.3f} con R² = {r2:.4f}: casi proporcionalidad.\n"
            "Es en buena parte una propiedad del modelo de CodeCarbon, que estima\n"
            "la potencia con la carga global de la máquina y no con la del proceso:\n"
            "su CO₂ resulta la duración multiplicada por una constante (§5.1)."
        )
        ax.text(
            0.03,
            0.97,
            texto,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f4f4f0", edgecolor="#cccccc"),
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("tiempo de ejecución [s]")
    ax.set_ylabel("kgCO₂eq por ejecución")
    ax.set_title("Relación entre tiempo de ejecución y emisiones")
    ax.legend(frameon=False)
    return guardar_figura(fig, nombre_archivo)


def generar_todos(resumen: pd.DataFrame) -> dict[str, str]:
    """Genera los cinco gráficos del informe y devuelve {clave: ruta relativa}."""
    aplicar_estilo()
    rutas: dict[str, str] = {}
    presentes = set(resumen.experimento.unique())

    if "ordenamiento" in presentes:
        rutas["ordenamiento"] = escalado_co2(resumen, "ordenamiento", "01_ordenamiento_escalado.png")
    if "fibonacci" in presentes:
        rutas["fibonacci"] = comparativa_barras(resumen, "fibonacci", "02_fibonacci_comparacion.png")
    if "matrices" in presentes:
        rutas["matrices"] = comparativa_barras(resumen, "matrices", "03_matrices_comparacion.png")
    if "aprendizaje_knn" in presentes:
        rutas["aprendizaje_knn"] = escalado_co2(
            resumen, "aprendizaje_knn", "04_knn_escalado.png"
        )

    rutas["tiempo_vs_co2"] = tiempo_vs_co2(resumen)
    return rutas
