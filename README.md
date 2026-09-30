# CP2K k-point validation data

Numerical companion to *Symmetry-reduced k-point sampling and Wannier analysis
with localized Gaussian orbitals* and its Supporting Information. This release
contains the calculations actually reported for Si and Al, their three targeted
unit-test results, the documented threading diagnostic, and the scripts needed
to regenerate the two manuscript tables. It does not include manuscript drafts,
CP2K source copies, or calculations belonging to the separate topology study.

## Evidence map

| Manuscript or SI claim | Retained evidence |
| --- | --- |
| Mesh convergence and full/time-reversal/K290/SPGLIB equivalence for Si and Al | The 18 `validation/{si,al}-*/sample.inp` and `sample.out` pairs, `validation/results.json`, and `validation_tables.tex` |
| Forces, stress, occupations, FFT-requested comparisons | The same raw outputs and `validation/summarize_validation.py` |
| Reproducible build and execution settings | `validation/build_metadata.json` and each case's `run_metadata.json` |
| Three successful targeted unit tests | `validation/unit_results.json` and the three `validation/*_unittest.ssmp.out` files |
| Failed two-thread Si diagnostic mentioned in the SI | `validation/si-2-full-fft-off/failed-two-threads.out` and `validation/threading-diagnostic/repeat-two-threads.out` |
| Version boundaries and source inspection | `provenance/README.md`, `provenance/source-inspection.md`, and `validation/source_history.json` |

The 18 converged calculations use a single OpenMP thread and a single BLAS
thread. The failed threaded runs are diagnostics, not part of the 18 successful
cases. The Si/Al data do **not** validate the separately described Wannier90
library interface, later DFT+U support, or every capability listed in the SI.
There are no figure datasets for the current k-point manuscript, which has no
data figure. Topological spectra and their raw calculations belong to a
different study.

## Reproduce the tables

Python 3.10 or newer and its standard library are sufficient for reanalysis:

```sh
python3 tools/verify_integrity.py
python3 validation/summarize_validation.py
```

The summarizer checks that all 18 logs are complete and converged, reparses
energies, forces, stress and solved k-point counts, then writes
`validation_tables.tex`. The retained file matches the table source in the
current manuscript. For a fresh CP2K calculation, build the public CP2K source
revision recorded in `validation/build_metadata.json` with the required
libraries, then run the following commands in a **copy** of this repository:

```sh
python3 validation/run_validation.py --source /path/to/cp2k \
  --binary /path/to/cp2k.ssmp --threads 1 --rerun
python3 validation/summarize_validation.py
```

`--rerun` replaces case outputs and metadata in that working copy. The
original inputs point to `BASIS_MOLOPT` and `GTH_POTENTIALS` in the pinned
CP2K checkout. No duplicate CP2K data files are required here. The build
metadata include the original compiler flags and executable SHA-256;
machine-specific absolute paths are provenance, not portable dependencies.

This GitHub repository is an inspectable data release, not a DOI-granting
archive. A versioned deposit with a persistent identifier remains a separate
submission step. The CP2K source retains its own license. No blanket license
for the research data or contributor-written scripts is asserted here.
