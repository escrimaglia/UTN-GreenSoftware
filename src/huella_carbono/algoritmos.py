# Compute the carbon footprint of Python algorithms
# By Ed Scrimaglia

"""
Implementations to compare.

All functions are pure: they take the input, return the result, and do no
I/O and print nothing. This is essential so that the measurement reflects the cost of the
algorithm and not that of unrelated operations.

Within each experiment, all variants solve EXACTLY the same problem
and produce the same result. That equivalence is verified with `validar_experimento()`
before measuring: comparing the footprint of two algorithms that do not do the same thing
would make no sense.
"""

from __future__ import annotations

import random
import sys
from functools import lru_cache
from typing import Any, Callable

import numpy as np

from huella_carbono.config import SEMILLA

# The naive recursive Fibonacci variant reaches moderate depths, and recursive
# merge_sort over 8000 elements reaches ~log2(8000) ≈ 13 levels, so the default
# limit is enough. It is raised anyway as a safeguard against larger inputs.
sys.setrecursionlimit(10_000)


# ======================================================================================
# Experiment 1 — Sorting
# ======================================================================================


def bubble_sort(datos: list[int]) -> list[int]:
    """Bubble sort with early exit. Complexity O(n²)."""
    a = list(datos)
    n = len(a)
    for i in range(n - 1):
        hubo_intercambio = False
        for j in range(n - 1 - i):
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
                hubo_intercambio = True
        if not hubo_intercambio:
            break
    return a


def merge_sort(datos: list[int]) -> list[int]:
    """Recursive merge sort in pure Python. Complexity O(n log n)."""
    a = list(datos)
    if len(a) <= 1:
        return a
    medio = len(a) // 2
    izq = merge_sort(a[:medio])
    der = merge_sort(a[medio:])
    return mezclar(izq, der)


def mezclar(izq: list[int], der: list[int]) -> list[int]:
    resultado: list[int] = []
    i = j = 0
    while i < len(izq) and j < len(der):
        if izq[i] <= der[j]:
            resultado.append(izq[i])
            i += 1
        else:
            resultado.append(der[j])
            j += 1
    resultado.extend(izq[i:])
    resultado.extend(der[j:])
    return resultado


def timsort_nativo(datos: list[int]) -> list[int]:
    """CPython's `sorted()`: Timsort, O(n log n), implemented in C."""
    return sorted(datos)


def generar_entrada_ordenamiento(n: int) -> list[int]:
    """Reproducible pseudorandom list: same seed -> same input."""
    rng = random.Random(SEMILLA)
    return [rng.randint(0, 10 * n) for _ in range(n)]


# ======================================================================================
# Experiment 2 — Fibonacci
# ======================================================================================


def fib_recursivo(n: int) -> int:
    """Naive recursion: recomputes the same subproblems. Complexity O(φⁿ)."""
    if n < 2:
        return n
    return fib_recursivo(n - 1) + fib_recursivo(n - 2)


def fib_memoizado(n: int) -> int:
    """Same recursion, but caching subproblems. Complexity O(n)."""

    @lru_cache(maxsize=None)
    def fib(k: int) -> int:
        if k < 2:
            return k
        return fib(k - 1) + fib(k - 2)

    # The cache is created inside the function so that each measurement starts from scratch and
    # does not benefit from previous runs (which would distort the repetitions).
    return fib(n)


def fib_iterativo(n: int) -> int:
    """Iterative version, with no recursion or cache. Complexity O(n), memory O(1)."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


# ======================================================================================
# Experiment 3 — Matrix multiplication
# ======================================================================================


def matmul_python(par: tuple[list[list[float]], list[list[float]]]) -> list[list[float]]:
    """Matrix product with a triple loop in pure Python. Complexity O(n³)."""
    a, b = par
    n = len(a)
    m = len(b[0])
    p = len(b)
    resultado = [[0.0] * m for _ in range(n)]
    for i in range(n):
        fila_a = a[i]
        fila_res = resultado[i]
        for k in range(p):
            valor = fila_a[k]
            if valor == 0.0:
                continue
            fila_b = b[k]
            for j in range(m):
                fila_res[j] += valor * fila_b[j]
    return resultado


def matmul_numpy(par: tuple[list[list[float]], list[list[float]]]) -> list[list[float]]:
    """Same product delegated to NumPy/BLAS. Same complexity O(n³)."""
    a, b = par
    resultado = np.asarray(a) @ np.asarray(b)
    return resultado.tolist()


def generar_entrada_matrices(n: int) -> tuple[list[list[float]], list[list[float]]]:
    """Two reproducible n×n matrices, as lists of lists so as not to favor NumPy."""
    rng = np.random.default_rng(SEMILLA)
    a = rng.random((n, n)).round(6)
    b = rng.random((n, n)).round(6)
    return a.tolist(), b.tolist()


# ======================================================================================
# Experiment 4 — Machine learning (in `ml.py`)
# ======================================================================================

# The KNN experiment lives in `ml.py` because importing scikit-learn takes ~1.5 s (measured),
# and this module is also imported when only the report is regenerated. Here we register
# adapters that resolve the real module on the first call and keep it cached.

CLAVE_ML = "aprendizaje_knn"
MODULO_ML: Any = None


def modulo_ml() -> Any:
    """Import `huella_carbono.ml` the first time it is needed and cache it."""
    global MODULO_ML
    if MODULO_ML is None:
        from huella_carbono import ml

        MODULO_ML = ml
    return MODULO_ML


def generar_entrada_knn(n: int) -> Any:
    """Lazy adapter for `ml.generar_entrada_knn`."""
    return modulo_ml().generar_entrada_knn(n)


def variante_knn(nombre: str) -> Callable[[Any], Any]:
    """
    Lazy adapter for a KNN variant.

    Resolving the module is an already cached `sys.modules` lookup, on the order of a
    microsecond, against measurement windows of at least half a second: it does not
    contaminate the measurement.
    """

    def ejecutar(entrada: Any) -> Any:
        return modulo_ml().VARIANTES[nombre](entrada)

    ejecutar.__name__ = nombre
    return ejecutar


# ======================================================================================
# Experiment registry
# ======================================================================================

# experiment key -> (input generator, {algorithm name: function})
REGISTRO: dict[str, tuple[Callable[[int], Any], dict[str, Callable[[Any], Any]]]] = {
    "ordenamiento": (
        generar_entrada_ordenamiento,
        {
            "bubble_sort": bubble_sort,
            "merge_sort": merge_sort,
            "timsort_nativo": timsort_nativo,
        },
    ),
    "fibonacci": (
        lambda n: n,
        {
            "fib_recursivo": fib_recursivo,
            "fib_memoizado": fib_memoizado,
            "fib_iterativo": fib_iterativo,
        },
    ),
    "matrices": (
        generar_entrada_matrices,
        {
            "matmul_python": matmul_python,
            "matmul_numpy": matmul_numpy,
        },
    ),
    CLAVE_ML: (
        generar_entrada_knn,
        {
            "knn_brute": variante_knn("knn_brute"),
            "knn_kd_tree": variante_knn("knn_kd_tree"),
            "knn_ball_tree": variante_knn("knn_ball_tree"),
        },
    ),
}


def resultados_equivalentes(obtenido: Any, referencia: Any) -> bool:
    """
    Compare two results of the same experiment, dispatching by TYPE, not by experiment.

    This used to be an `if clave == "matrices"`, which left any new experiment
    in the exact-equality branch: with numpy arrays, `obtenido == referencia` returns an
    array and the subsequent `if` raises `ValueError: truth value of an array is ambiguous`
    instead of a readable error.

    - numpy arrays: exact comparison for integers (class labels), with tolerance
      for floating point;
    - lists of lists of floats (matrices): with tolerance, because the order of the sums
      differs between the interpreter and BLAS;
    - everything else: structural equality.
    """
    if isinstance(obtenido, np.ndarray) or isinstance(referencia, np.ndarray):
        a, b = np.asarray(obtenido), np.asarray(referencia)
        if a.shape != b.shape:
            return False
        if np.issubdtype(a.dtype, np.floating) or np.issubdtype(b.dtype, np.floating):
            return bool(np.allclose(a, b, rtol=1e-9, atol=1e-9))
        return bool(np.array_equal(a, b))
    if isinstance(obtenido, list) and obtenido and isinstance(obtenido[0], list):
        return bool(
            np.allclose(np.asarray(obtenido), np.asarray(referencia), rtol=1e-9, atol=1e-9)
        )
    return bool(obtenido == referencia)


def validar_experimento(clave: str, n: int) -> None:
    """
    Verify that all variants of the experiment produce the same result.

    It is the precondition of the whole project: comparing the carbon footprint only makes sense
    for algorithms that solve the same problem with the same output.
    """
    generar, variantes = REGISTRO[clave]
    entrada = generar(n)
    referencia = None
    nombre_referencia = ""
    for nombre, funcion in variantes.items():
        obtenido = funcion(entrada)
        if referencia is None:
            referencia, nombre_referencia = obtenido, nombre
            continue
        if not resultados_equivalentes(obtenido, referencia):
            raise AssertionError(
                f"[{clave}] '{nombre}' does not match '{nombre_referencia}' for n={n}. "
                "The algorithms are not equivalent: the footprint comparison would not be valid."
            )

    if clave == CLAVE_ML and referencia is not None:
        modulo_ml().medir_calidad(n, entrada, referencia)
