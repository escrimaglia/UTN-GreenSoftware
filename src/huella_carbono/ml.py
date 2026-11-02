# Compute the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Experiment 4 — Training and inference of a machine learning model.

The three variants are the SAME classifier —`KNeighborsClassifier(n_neighbors=31)`—
solving the neighbor search in three different ways: `brute`, `kd_tree` and
`ball_tree`. They return identical predictions, so the premise of the project holds:
compare the footprint of implementations that produce exactly the same result.

Why this experiment contributes something the other three cannot: `brute` solves
the search with BLAS matrix products, which use all cores, while the two
trees are single-threaded. It is the only workload in the project that breaks the constant 1/n_cores
utilization of the other experiments, and therefore the only one that lets us measure —instead of
merely warn— that parallelizing reduces time without reducing energy in the same proportion.

This module lives apart from `algoritmos.py` because importing scikit-learn takes about a
second, and `algoritmos.py` is also imported when only the report is regenerated.
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
# Experiment parameters
# --------------------------------------------------------------------------------------

# k = 31 (odd, so there are no ties in binary classification). It is the value from the
# project's reference example.
VECINOS = 31

# 20 features, 10 of them informative. Dimensionality matters for the
# result: in 20 dimensions the trees lose their pruning ability and stop scaling
# as O(log n), which the report presents as a finding.
CARACTERISTICAS = 20
CARACTERISTICAS_INFORMATIVAS = 10

PROPORCION_TEST = 0.2

# Neighbor search strategies. `brute` computes the distance matrix with BLAS
# (multithreaded); the trees build a spatial structure and query one point at a time.
ESTRATEGIAS = ("brute", "kd_tree", "ball_tree")

EntradaKNN = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]

# n -> accuracy. Filled in by `medir_calidad()`, which runs during the equivalence
# validation. Accuracy is identical across the three variants (it is a property of the dataset
# and of k, not of the search strategy), so it is not a per-algorithm metric: it goes to
# `metadatos.json` instead of a column of the simulation CSV.
CALIDAD: dict[int, float] = {}


def generar_entrada_knn(n: int) -> EntradaKNN:
    """
    Generate a reproducible binary classification problem with `n` samples.

    Returns `(X_train, y_train, X_test, y_test)`. All randomness is
    fixed with `config.SEMILLA`: the same `n` always produces exactly the same dataset,
    and the three variants receive the same object.
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
    Factory for the measured function: trains the classifier and predicts on the test set.

    The classifier is built INSIDE the measured function on purpose. The meter runs
    the function several times within the same window (batch measurement), and every run
    must do the same work: if the model were built outside, the first run
    would train and the following ones would reuse the already built tree.

    `n_jobs` is deliberately left at its default value (1). The parallelism of `brute`
    comes from the BLAS threads, which run inside this process and are therefore seen by
    `psutil.Process().cpu_times()`. With `n_jobs>1`, joblib would spawn child processes whose CPU
    time is not attributed to the measured process, and the parallel workload would appear as
    the cleanest of all.
    """

    def entrenar(entrada: EntradaKNN) -> np.ndarray:
        X_entrenamiento, y_entrenamiento, X_prueba, _ = entrada
        knn = KNeighborsClassifier(n_neighbors=VECINOS, algorithm=estrategia)
        knn.fit(X_entrenamiento, y_entrenamiento)
        return knn.predict(X_prueba)

    entrenar.__name__ = f"knn_{estrategia}"
    entrenar.__doc__ = (
        f"KNN with k={VECINOS} and `{estrategia}` search: trains and predicts the test set."
    )
    return entrenar


VARIANTES: dict[str, Callable[[EntradaKNN], np.ndarray]] = {
    f"knn_{estrategia}": entrenar_y_predecir(estrategia) for estrategia in ESTRATEGIAS
}


def medir_calidad(n: int, entrada: EntradaKNN, predicciones: np.ndarray) -> float:
    """
    Record the accuracy of the predictions for size `n` and return it.

    It is called from the equivalence validation, which already runs each variant once: that way
    the model quality costs no extra run.
    """
    _, _, _, y_prueba = entrada
    exactitud = float(accuracy_score(y_prueba, predicciones))
    CALIDAD[int(n)] = exactitud
    return exactitud
