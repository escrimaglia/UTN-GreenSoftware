# Calcular la huella de carbono de los algoritmos de Python
# By Ed Scrimaglia

"""
Implementaciones a comparar.

Todas las funciones son puras: reciben la entrada, devuelven el resultado y no hacen
I/O ni imprimen nada. Eso es indispensable para que la medición refleje el costo del
algoritmo y no el de operaciones ajenas.

Dentro de cada experimento, todas las variantes resuelven EXACTAMENTE el mismo problema
y producen el mismo resultado. Esa equivalencia se verifica con `validar_experimento()`
antes de medir: comparar la huella de dos algoritmos que no hacen lo mismo no tendría
sentido.
"""

from __future__ import annotations

import random
import sys
from functools import lru_cache
from typing import Any, Callable

import numpy as np

from huella_carbono.config import SEMILLA

# La variante recursiva ingenua de Fibonacci alcanza profundidades moderadas, pero
# merge_sort recursivo sobre 8000 elementos llega a ~log2(8000) ≈ 13 niveles, así que
# el límite por defecto alcanza. Se eleva igual por seguridad ante entradas mayores.
sys.setrecursionlimit(10_000)


# ======================================================================================
# Experimento 1 — Ordenamiento
# ======================================================================================


def bubble_sort(datos: list[int]) -> list[int]:
    """Ordenamiento burbuja con corte temprano. Complejidad O(n²)."""
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
    """Ordenamiento por mezcla, recursivo, en Python puro. Complejidad O(n log n)."""
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
    """`sorted()` de CPython: Timsort, O(n log n), implementado en C."""
    return sorted(datos)


def generar_entrada_ordenamiento(n: int) -> list[int]:
    """Lista pseudoaleatoria reproducible: misma semilla -> misma entrada."""
    rng = random.Random(SEMILLA)
    return [rng.randint(0, 10 * n) for _ in range(n)]


# ======================================================================================
# Experimento 2 — Fibonacci
# ======================================================================================


def fib_recursivo(n: int) -> int:
    """Recursión ingenua: recalcula los mismos subproblemas. Complejidad O(φⁿ)."""
    if n < 2:
        return n
    return fib_recursivo(n - 1) + fib_recursivo(n - 2)


def fib_memoizado(n: int) -> int:
    """Misma recursión, pero cacheando subproblemas. Complejidad O(n)."""

    @lru_cache(maxsize=None)
    def fib(k: int) -> int:
        if k < 2:
            return k
        return fib(k - 1) + fib(k - 2)

    # La caché se crea dentro de la función para que cada medición parta de cero y no
    # se beneficie de las corridas anteriores (lo que falsearía las repeticiones).
    return fib(n)


def fib_iterativo(n: int) -> int:
    """Versión iterativa, sin recursión ni caché. Complejidad O(n), memoria O(1)."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


# ======================================================================================
# Experimento 3 — Multiplicación de matrices
# ======================================================================================


def matmul_python(par: tuple[list[list[float]], list[list[float]]]) -> list[list[float]]:
    """Producto matricial con triple bucle en Python puro. Complejidad O(n³)."""
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
    """Mismo producto delegado a NumPy/BLAS. Misma complejidad O(n³)."""
    a, b = par
    resultado = np.asarray(a) @ np.asarray(b)
    return resultado.tolist()


def generar_entrada_matrices(n: int) -> tuple[list[list[float]], list[list[float]]]:
    """Dos matrices n×n reproducibles, como listas de listas para no favorecer a NumPy."""
    rng = np.random.default_rng(SEMILLA)
    a = rng.random((n, n)).round(6)
    b = rng.random((n, n)).round(6)
    return a.tolist(), b.tolist()


# ======================================================================================
# Experimento 4 — Aprendizaje automático (en `ml.py`)
# ======================================================================================

# El experimento de KNN vive en `ml.py` porque importar scikit-learn cuesta ~1,5 s medidos,
# y este módulo se importa también cuando sólo se regenera el informe. Acá se registran
# adaptadores que resuelven el módulo real en la primera llamada y lo dejan cacheado.

CLAVE_ML = "aprendizaje_knn"
MODULO_ML: Any = None


def modulo_ml() -> Any:
    """Importa `huella_carbono.ml` la primera vez que se lo necesita y lo cachea."""
    global MODULO_ML
    if MODULO_ML is None:
        from huella_carbono import ml

        MODULO_ML = ml
    return MODULO_ML


def generar_entrada_knn(n: int) -> Any:
    """Adaptador perezoso de `ml.generar_entrada_knn`."""
    return modulo_ml().generar_entrada_knn(n)


def variante_knn(nombre: str) -> Callable[[Any], Any]:
    """
    Adaptador perezoso de una variante de KNN.

    La resolución del módulo es una consulta a `sys.modules` ya cacheada, del orden del
    microsegundo, contra ventanas de medición de medio segundo como mínimo: no contamina
    la medición.
    """

    def ejecutar(entrada: Any) -> Any:
        return modulo_ml().VARIANTES[nombre](entrada)

    ejecutar.__name__ = nombre
    return ejecutar


# ======================================================================================
# Registro de experimentos
# ======================================================================================

# clave del experimento -> (generador de entrada, {nombre de algoritmo: función})
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
    Compara dos resultados del mismo experimento despachando por TIPO, no por experimento.

    Antes esto era un `if clave == "matrices"`, lo que dejaba a cualquier experimento nuevo
    en la rama de igualdad exacta: con arrays de numpy, `obtenido == referencia` devuelve un
    array y el `if` posterior levanta `ValueError: truth value of an array is ambiguous` en
    lugar de un error legible.

    - arrays de numpy: comparación exacta para enteros (etiquetas de clase), con tolerancia
      para punto flotante;
    - listas de listas de floats (matrices): con tolerancia, porque el orden de las sumas
      difiere entre el intérprete y BLAS;
    - todo lo demás: igualdad estructural.
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
    Verifica que todas las variantes del experimento produzcan el mismo resultado.

    Es la precondición de todo el proyecto: solo tiene sentido comparar la huella de carbono
    de algoritmos que resuelven el mismo problema con la misma salida.
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
                f"[{clave}] '{nombre}' no coincide con '{nombre_referencia}' para n={n}. "
                "Los algoritmos no son equivalentes: la comparación de huella no sería válida."
            )

    if clave == CLAVE_ML and referencia is not None:
        modulo_ml().medir_calidad(n, entrada, referencia)
