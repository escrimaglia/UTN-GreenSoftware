# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Experimento 4 — Entrenamiento e inferencia de un modelo de aprendizaje automático.

Las tres variantes son el MISMO clasificador —`KNeighborsClassifier(n_neighbors=31)`—
resolviendo la búsqueda de vecinos de tres formas distintas: `brute`, `kd_tree` y
`ball_tree`. Devuelven predicciones idénticas, así que se mantiene la premisa del trabajo:
comparar la huella de implementaciones que producen exactamente el mismo resultado.

Por qué este experimento aporta algo que los otros tres no pueden aportar: `brute` resuelve
la búsqueda con productos matriciales de BLAS, que usa todos los núcleos, mientras los dos
árboles son monohilo. Es la única carga del proyecto que rompe la utilización constante de 1/n_núcleos
de los otros experimentos, y por lo tanto la única que permite medir —en lugar de sólo
advertir— que paralelizar reduce el tiempo sin reducir la energía en la misma proporción.

Este módulo vive separado de `algoritmos.py` porque importar scikit-learn cuesta cerca de un
segundo, y `algoritmos.py` se importa también cuando sólo se regenera el informe.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from sklearn.datasets import make_classification
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier

from huella_carbono import config

# --------------------------------------------------------------------------------------
# Parámetros del experimento
# --------------------------------------------------------------------------------------

# k = 31 (impar, para que no haya empates en clasificación binaria). Es el valor del ejemplo
# de referencia del proyecto.
VECINOS = 31

# 20 características de las cuales 10 informativas. La dimensionalidad importa para el
# resultado: en 20 dimensiones los árboles pierden su capacidad de poda y dejan de escalar
# como O(log n), lo que el informe reporta como hallazgo.
CARACTERISTICAS = 20
CARACTERISTICAS_INFORMATIVAS = 10

PROPORCION_TEST = 0.2

# Estrategias de búsqueda de vecinos. `brute` calcula la matriz de distancias con BLAS
# (multihilo); los árboles construyen una estructura espacial y consultan de a un punto.
ESTRATEGIAS = ("brute", "kd_tree", "ball_tree")

EntradaKNN = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]

# n -> accuracy. Se llena en `medir_calidad()`, que corre durante la validación de
# equivalencia. La accuracy es idéntica en las tres variantes (es una propiedad del dataset
# y de k, no de la estrategia de búsqueda), así que no es una métrica por algoritmo: viaja a
# `metadatos.json` en lugar de a una columna del CSV de la simulación.
CALIDAD: dict[int, float] = {}


def generar_entrada_knn(n: int) -> EntradaKNN:
    """
    Genera un problema de clasificación binaria reproducible de `n` muestras.

    Devuelve `(X_entrenamiento, y_entrenamiento, X_prueba, y_prueba)`. Todo el azar está
    fijado con `config.SEMILLA`: el mismo `n` produce siempre exactamente el mismo dataset,
    y las tres variantes reciben el mismo objeto.
    """
    X, y = make_classification(
        n_samples=n,
        n_features=CARACTERISTICAS,
        n_informative=CARACTERISTICAS_INFORMATIVAS,
        random_state=config.SEMILLA,
    )
    X_entrenamiento, X_prueba, y_entrenamiento, y_prueba = train_test_split(
        X, y, test_size=PROPORCION_TEST, random_state=config.SEMILLA
    )
    return X_entrenamiento, y_entrenamiento, X_prueba, y_prueba


def entrenar_y_predecir(estrategia: str) -> Callable[[EntradaKNN], np.ndarray]:
    """
    Fábrica de la función medida: entrena el clasificador y predice sobre el conjunto de prueba.

    El clasificador se construye DENTRO de la función medida a propósito. El medidor ejecuta
    la función varias veces dentro de una misma ventana (medición por lotes), y cada ejecución
    tiene que hacer el mismo trabajo: si el modelo se construyera afuera, la primera ejecución
    entrenaría y las siguientes reutilizarían el árbol ya construido.

    `n_jobs` se deja en su valor por defecto (1) deliberadamente. El paralelismo de `brute`
    viene de los hilos de BLAS, que corren dentro de este proceso y por lo tanto los ve
    `psutil.Process().cpu_times()`. Con `n_jobs>1`, joblib lanzaría procesos hijos cuyo tiempo
    de CPU el medidor propio no contabiliza, y la carga paralela aparecería en el informe como
    la más limpia de todas.
    """

    def entrenar(entrada: EntradaKNN) -> np.ndarray:
        X_entrenamiento, y_entrenamiento, X_prueba, _ = entrada
        knn = KNeighborsClassifier(n_neighbors=VECINOS, algorithm=estrategia)
        knn.fit(X_entrenamiento, y_entrenamiento)
        return knn.predict(X_prueba)

    entrenar.__name__ = f"knn_{estrategia}"
    entrenar.__doc__ = (
        f"KNN con k={VECINOS} y búsqueda `{estrategia}`: entrena y predice el conjunto de prueba."
    )
    return entrenar


VARIANTES: dict[str, Callable[[EntradaKNN], np.ndarray]] = {
    f"knn_{estrategia}": entrenar_y_predecir(estrategia) for estrategia in ESTRATEGIAS
}


def medir_calidad(n: int, entrada: EntradaKNN, predicciones: np.ndarray) -> float:
    """
    Registra la accuracy de las predicciones para el tamaño `n` y la devuelve.

    Se llama desde la validación de equivalencia, que ya ejecuta cada variante una vez: así
    la calidad del modelo no cuesta ninguna ejecución extra.
    """
    _, _, _, y_prueba = entrada
    exactitud = float(accuracy_score(y_prueba, predicciones))
    CALIDAD[int(n)] = exactitud
    return exactitud
