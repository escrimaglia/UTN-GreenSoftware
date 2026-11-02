# Carbon footprint of Python algorithms

Green Software — Universidad Tecnológica Nacional - FRC.

## What it is

A test bench that **measures the energy consumed and the CO₂ emitted when running
algorithms**, and produces a report with the results.

It does not estimate from a table or a theoretical model: it runs the algorithms on the
machine, reads the processor's actual power draw while they work, and converts it to
emissions using the Argentine power grid's emission factor.

## What it is about

The question it answers is: **does computational complexity have a measurable
environmental consequence?**

To answer it, it compares variants that solve **exactly the same problem and return the
same result** —checked by assertion before each measurement—, so that the only difference
between them is how they reach that result. If one algorithm emits a thousand times more
than another to produce the same output, the difference is attributable to the design
decision and nothing else.

There are four experiments, each with its own question:

| Experiment | What it tests | Variants |
|---|---|---|
| `ordenamiento` | complexity: O(n²) versus O(n log n) | `bubble_sort`, `merge_sort`, `timsort_nativo` |
| `fibonacci` | the cost of recomputing work already done | `fib_recursivo`, `fib_memoizado`, `fib_iterativo` |
| `matrices` | at equal complexity, how much the implementation weighs | `matmul_python`, `matmul_numpy` |
| `aprendizaje_knn` | the effect of parallelism, training a real model | `knn_brute`, `knn_kd_tree`, `knn_ball_tree` |

Emissions gap between the best and the worst variant of each experiment, at its largest
size. The power of ten immediately below the measured factor is reported, so that this
README does not fall out of sync when measurements are rerun:

| Experiment | Emissions gap |
|---|---|
| Sorting | more than 10³× |
| Fibonacci | more than 10⁵× |
| Matrices | more than 10²× |
| KNN | more than 10¹× |

The exact figures from the latest run are in [`INFORME.md`](INFORME.md).

## What it is for

- **To back with measurements an argument that is usually taken for granted.** "Choosing
  the right algorithm saves energy" is a verifiable claim, and this project verifies it
  instead of repeating it.
- **To translate emissions into understandable quantities.** The report extrapolates each
  algorithm to real-world usage scales and expresses the result in car kilometers and
  phone charges, not just micrograms of CO₂.
- **To show how much a footprint measurement depends on the method used.** The same test
  bench yields different absolute values depending on whether power was measured or
  estimated, and the report states which of the two paths produced its figures instead of
  presenting the number as if it were the only one.
- **As a basis for measuring other code.** The structure —verify equivalence, measure in
  batches, repeat, report dispersion— works for any footprint comparison, not just for
  these algorithms.

## How to use it

### Installation

```bash
uv sync        # installs the exact environment from uv.lock
```

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

**The project is platform-agnostic:** it runs on macOS, Linux and Windows without changing
anything. No part of the test bench is tied to an operating system —there is no code
selected by system— and the only thing that adapts is where the power reading comes from,
which is resolved on each run by asking the machine what it offers. Where no reading is
available, power is estimated and that fact is recorded. There is no code branch that
depends on the operating system.

Run and verified on macOS with Apple Silicon; not verified on Linux or Windows.

### Running the test bench

```bash
uv run huella-carbono --full    # all 4 experiments, all sizes (~11 min)
uv run huella-carbono --quick   # all 4 experiments with reduced sizes (~6 min)
```

`--full` is the default mode: `uv run huella-carbono` with no arguments does the same.
Each run overwrites `resultados/` and `INFORME.md`.

Run times are dominated by the measurement window, not by the algorithms' work: reading
power from the hardware requires at least 3 s per measured point, and there are 42
configurations in full mode and 22 in quick mode. That is why input size barely changes
the total duration. When power is estimated instead of measured, 0.5 s per point is
enough and the full run drops to about 2.5 min.

### Measuring power instead of estimating it

This is the decision that most affects the results, and it is also what makes the project
platform-independent: instead of assuming an operating system, **it reads the processor's
actual power whenever the machine allows it and only estimates it when it does not**. The
run never fails because of this; what changes is the quality of the data, and the report
states it.

| Platform | How power is read | Requirement | Verified |
|---|---|---|---|
| macOS with Apple Silicon | system power utility | administrator privileges | yes, on this machine |
| Linux | processor counters | none | not tested |
| Windows 11 | system energy meter | physical machine, not virtualized | not tested |
| any, if no reading is available | estimated from load | — | yes, on this machine |

The two rows marked "not tested" are what the measurement tool attempts on those
platforms according to its documentation; this project was only run on macOS.

There is nothing to set up: the run works out on its own where to get the power from. If
the machine does not allow reading it, it does not fail —it falls back to estimation,
records it in `resultados/metadatos.json`, and the report states which of the two paths
was used—. The difference matters: with estimation, absolute values are computed from a
generic nominal draw of 85 W, typical of a desktop computer.

The first line of the run shows which one is active:

```
CPU power: direct reading (apple_powermetrics)  |  measurement window >= 3.0 s
```

### Running a specific experiment

`--only` accepts one or more of the four names:

```bash
uv run huella-carbono --full  --only ordenamiento
uv run huella-carbono --full  --only matrices aprendizaje_knn
uv run huella-carbono --quick --only aprendizaje_knn
```

| Key | Sizes in `--full` |
|---|---|
| `ordenamiento` | 1,000 → 8,000 elements |
| `fibonacci` | n = 20 → 32 |
| `matrices` | 100×100 → 300×300 matrices |
| `aprendizaje_knn` | 2,500 → 20,000 samples |

**Warning:** a run with `--only` rewrites `resultados/` and `INFORME.md` with *only* those
experiments, and there is no undo. If the current results matter, copy them first.

### Other options

```bash
uv run huella-carbono --repetitions 5    # repetitions per point (default 3)
uv run huella-carbono --report-only      # regenerates charts and report without measuring again
uv run huella-carbono --help
```

`--report-only` does not measure: it rereads `resultados/simulacion_huella_carbono.csv`
and regenerates the charts and the report. It is what to use after changing the report
code.

### What it produces

| Output | Contents |
|---|---|
| `INFORME.md` | the full report: methodology, results, analysis, limitations and sources |
| `resultados/simulacion_huella_carbono.csv` | one row per measurement, with time, energy and CO₂ |
| `resultados/metadatos.json` | machine, versions and parameters used for the run |
| `resultados/graficos/*.png` | the five charts embedded in the report |

No figure in the report is written by hand: they are all derived from the measured CSV,
so the report cannot fall out of sync with the data.

## The results CSV

`resultados/simulacion_huella_carbono.csv` is the project's export: the raw record of
what was measured. The report is its reading; the CSV is the evidence.

**Why it exists and why there is only one.** A measurement that cannot be audited is not
worth much as a measurement: every figure in the report has to be traceable back to the
data point it came from. That is why the finest grain is stored —each individual
measurement, without averaging— and everything else is derived from it when the report
is generated. Also storing a table of averages would mean versioning the same information
twice and opening the door to the two versions contradicting each other. It also remains
available as input for analysis outside the project, with a spreadsheet or any data tool.

**What it contains.** One row per measurement and 12 columns. A full run has 126 rows: 42
configurations —each combination of algorithm and size— times 3 repetitions. Column names
are kept as they are in the data file.

| Column | Contents |
|---|---|
| `experimento`, `algoritmo`, `complejidad`, `n` | experiment, algorithm, complexity and input size: what was measured and at what size |
| `repeticion`, `ejecuciones_lote` | which of the three repetitions it is, and how many executions went into the measured batch |
| `tiempo_s` | seconds per execution, timed around the work |
| `tiempo_s_informado` | the duration reported by the tool, which includes the time it takes to read power. It is kept so that this difference is visible |
| `energia_kwh`, `co2_kg` | energy and emissions per execution. **These are the report's figures** |
| `co2_kg_nativo` | the CO₂ the tool would compute with its own emission factor table, instead of the one in section 2 of the report |
| `potencia_cpu_w` | the processor power recorded for that measurement |

## How it works

**The project is built on CodeCarbon**, the industry-standard tool, in offline mode with
Argentina's emission factor. It is the only measurement path: there is no other energy or
emissions calculation in the code. Section 3.3 of the report mentions that power could
alternatively be derived with a custom model, but only as a mention: this project does
not implement it.

Methodological decisions that support the results:

- **Equivalence check.** Before measuring, all variants are checked to return the same
  result. Comparing the footprint of algorithms that do not solve the same problem would
  not be valid.
- **Batch measurement.** Several algorithms finish in microseconds, far less than any
  power reading takes. They are run K times inside the measured window and the result is
  divided by K, with K calibrated by a prior probe run. The minimum window depends on the
  power source: 3 s if read from the hardware, 0.5 s if estimated.
- **Repetitions.** Each point is measured 3 times and the mean and dispersion are
  reported. In the latest run the median dispersion was 4.7%.
- **Up-to-date emission factor.** On each run it is read from the most recent year
  available in the Argentine series versioned in `datos/`, instead of the 2023 value
  bundled with CodeCarbon.
- **A single CSV.** Averages and standard deviations are derived in memory, so the same
  information is not versioned twice.

## Structure

```
src/huella_carbono/          datos/
├── __init__.py              ├── intensidad_carbono_argentina.json
├── config.py                └── equivalencias_co2.json
├── algoritmos.py
├── ml.py                    resultados/
├── medidor.py               ├── simulacion_huella_carbono.csv
├── benchmark.py             ├── metadatos.json
├── graficos.py              └── graficos/
├── informe.py
└── main.py                  INFORME.md
```

**The code**

| File | Contents |
|---|---|
| `__init__.py` | package name and version |
| `config.py` | the energy model parameters, each with its source, and the definition of the four experiments: sizes, variants and descriptions |
| `algoritmos.py` | the sorting, Fibonacci and matrix implementations, plus the check that all variants of an experiment return the same result |
| `ml.py` | the KNN experiment, in a separate module so the cost of importing scikit-learn is not paid when it is not used |
| `medidor.py` | the CodeCarbon measurement and the batch sizing for each point |
| `benchmark.py` | orchestration: iterates over experiments and sizes, measures, and writes the CSV and metadata |
| `graficos.py` | the five charts embedded in the report |
| `informe.py` | generates `INFORME.md` from the CSV and the metadata |
| `main.py` | the command-line interface |

**The data inputs**, versioned with the project and not generated by the runs:

| File | Contents |
|---|---|
| `datos/intensidad_carbono_argentina.json` | the annual gCO₂eq/kWh series for the Argentine grid, with its source and download date. This is where the emission factor used to convert energy into CO₂ comes from |
| `datos/equivalencias_co2.json` | the factors for translating kgCO₂eq into tangible quantities: car kilometers, phone charges and the annual absorption of a tree |

**The outputs** of the latest run:

| File | Contents |
|---|---|
| `resultados/simulacion_huella_carbono.csv` | the simulation result, described above in its own section |
| `resultados/metadatos.json` | which machine, versions and parameters were used for the run, and where the power reading came from |
| `resultados/graficos/` | the five PNGs embedded in the report |
| `INFORME.md` | the report, generated on each run |
