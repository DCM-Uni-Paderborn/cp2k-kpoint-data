#!/usr/bin/env python3
"""Generate and run the manuscript's small, version-pinned CP2K comparisons."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

COMMIT = "dd94896b48d429648fb3640799c9d198ff8de1e3"


def input_text(element, mesh, mode, fft="OFF"):
    length = {"Si": 5.43, "Al": 4.05}[element]
    sites = [(0, 0, 0), (0, .5, .5), (.5, 0, .5), (.5, .5, 0)]
    if element == "Si":
        sites += [(x + .25, y + .25, z + .25) for x, y, z in sites[:]]
    coords = "\n".join(f"      {element} {x} {y} {z}" for x, y, z in sites)
    symmetry = mode in ("K290", "SPGLIB")
    backend = f"SYMMETRY_BACKEND {mode}" if symmetry else ""
    smear = "" if element == "Si" else """
      &SMEAR
        METHOD FERMI_DIRAC
        ELECTRONIC_TEMPERATURE 1000
      &END SMEAR"""
    return f"""&GLOBAL
  PROJECT sample
  RUN_TYPE ENERGY_FORCE
  PRINT_LEVEL MEDIUM
&END GLOBAL
&FORCE_EVAL
  METHOD QUICKSTEP
  STRESS_TENSOR ANALYTICAL
  &DFT
    BASIS_SET_FILE_NAME BASIS_MOLOPT
    POTENTIAL_FILE_NAME GTH_POTENTIALS
    &QS
      EPS_DEFAULT 1.0E-12
    &END QS
    &MGRID
      CUTOFF 600
      REL_CUTOFF 60
    &END MGRID
    &KPOINTS
      SCHEME MONKHORST-PACK {mesh} {mesh} {mesh}
      SYMMETRY {"T" if symmetry else "F"}
      FULL_GRID {"T" if mode == "full" else "F"}
      WAVEFUNCTIONS COMPLEX
      PARALLEL_GROUP_SIZE 0
      LATTICE_FFT {fft}
      {backend}
    &END KPOINTS
    &SCF
      EPS_SCF 1.0E-9
      MAX_SCF 150
      SCF_GUESS ATOMIC
      ADDED_MOS -1
      &DIAGONALIZATION
        ALGORITHM STANDARD
      &END DIAGONALIZATION
      &MIXING
        METHOD BROYDEN_MIXING
        ALPHA 0.15
      &END MIXING
      &PRINT
        &RESTART OFF
        &END RESTART
      &END PRINT
      {smear}
    &END SCF
    &PRINT
      &KPOINTS ON
        FILENAME __STD_OUT__
      &END KPOINTS
    &END PRINT
    &XC
      &XC_FUNCTIONAL PBE
      &END XC_FUNCTIONAL
    &END XC
  &END DFT
  &SUBSYS
    &CELL
      ABC {length} {length} {length}
      PERIODIC XYZ
    &END CELL
    &COORD
      SCALED T
{coords}
    &END COORD
    &KIND {element}
      BASIS_SET DZVP-MOLOPT-SR-GTH
      POTENTIAL GTH-PBE-q{4 if element == "Si" else 3}
    &END KIND
  &END SUBSYS
  &PRINT
    &FORCES ON
    &END FORCES
    &STRESS_TENSOR ON
    &END STRESS_TENSOR
  &END PRINT
&END FORCE_EVAL
"""


def parse_output(text):
    def last(pattern):
        matches = re.findall(pattern, text, re.M)
        return float(matches[-1]) if matches else None

    result = {
        "converged": "SCF run converged" in text and "SCF run NOT converged" not in text,
        "energy_hartree": last(r"ENERGY\| Total FORCE_EVAL.*?([-+0-9.Ee]+)\s*$"),
        "fermi_hartree": last(r"Fermi energy:\s+([-+0-9.Ee]+)"),
        "entropy_hartree": last(r"Electronic entropic energy:\s+([-+0-9.Ee]+)"),
        "nk": last(r"BRILLOUIN\| List of Kpoints.*?\]\s+(\d+)"),
    }
    forces = re.findall(r"^\s*FORCES\|\s+\d+\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)", text, re.M)
    if forces:
        result["forces_hartree_per_bohr"] = [[float(v) for v in row] for row in forces]
    force_blocks = re.findall(r"ATOMIC FORCES in \[a.u.\](.*?)SUM OF ATOMIC FORCES", text, re.S)
    if force_blocks:
        forces = re.findall(r"^\s*\d+\s+\d+\s+\w+\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)\s+([-+0-9.Ee]+)", force_blocks[-1], re.M)
        result["forces_hartree_per_bohr"] = [[float(v) for v in row] for row in forces]
    stress = re.search(r"STRESS\| Analytical stress tensor \[bar\](.*?)STRESS\| 1/3 Trace", text, re.S)
    if stress:
        result["stress_bar"] = [[float(v) for v in row] for row in re.findall(
            r"STRESS\|\s+[xyz]\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)", stress[1])]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--rerun", action="store_true")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    binary, source = args.binary.resolve(), args.source.resolve()
    version = subprocess.check_output([binary, "--version"], text=True)
    revision = re.search(r"Source code revision\s+([0-9a-f]+)", version)
    if not revision or len(revision[1]) < 8 or not COMMIT.startswith(revision[1]):
        raise SystemExit("Binary version does not match the manuscript snapshot")
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip() != COMMIT:
        raise SystemExit("Source snapshot mismatch")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=source).returncode:
        raise SystemExit("Tracked source modifications must not enter the frozen validation")
    root = Path(__file__).resolve().parent
    env = os.environ | {"CP2K_DATA_DIR": str(source / "data"),
                        "OMP_NUM_THREADS": str(args.threads), "OPENBLAS_NUM_THREADS": "1"}
    metadata = {"commit": COMMIT, "version_output": version, "threads": args.threads,
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    metadata_path = root / "build_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    unit_results = []
    for name in ("kpoint_lattice_fft_unittest.ssmp", "kpsym_unittest.ssmp", "kpoint_smearing_unittest.ssmp"):
        exe = binary.parent / name
        unit = subprocess.run([exe], env=env, capture_output=True, text=True, timeout=120)
        (root / (name + ".out")).write_text(unit.stdout + unit.stderr)
        unit_results.append({"test": name, "returncode": unit.returncode})
        if unit.returncode:
            raise RuntimeError(f"Unit test failed: {name}")
    (root / "unit_results.json").write_text(json.dumps(unit_results, indent=2) + "\n")
    results = []
    cases = [(element, n, "full", "OFF") for element in ("Si", "Al") for n in (1, 2, 4, 6, 8)]
    cases += [(element, 4, mode, "OFF") for element in ("Si", "Al") for mode in ("time-reversal", "K290", "SPGLIB")]
    cases += [("Si", 4, "full", "ON"), ("Al", 4, "full", "ON")]
    for element, mesh, mode, fft in cases:
        name = f"{element.lower()}-{mesh}-{mode.lower()}-fft-{fft.lower()}"
        directory = root / name
        directory.mkdir(exist_ok=True)
        inp = input_text(element, mesh, mode, fft)
        input_path, output = directory / "sample.inp", directory / "sample.out"
        case_metadata_path = directory / "run_metadata.json"
        same_build = case_metadata_path.exists() and json.loads(case_metadata_path.read_text()) == metadata
        same = input_path.exists() and input_path.read_text() == inp
        input_path.write_text(inp)
        if not args.rerun and same_build and same and output.exists() and "PROGRAM ENDED AT" in output.read_text():
            elapsed = None
            print(f"Reuse {name}", flush=True)
        else:
            case_metadata_path.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            started = time.monotonic()
            with (directory / "launcher.log").open("w") as log:
                process = subprocess.run([binary, "-i", "sample.inp", "-o", "sample.out"],
                                         cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            elapsed = time.monotonic() - started
            if process.returncode:
                raise RuntimeError(f"{name}: CP2K exited with {process.returncode}; inspect output")
        result = {"case": name, "element": element, "mesh": mesh, "mode": mode, "fft": fft,
                  "wall_seconds": elapsed} | parse_output(output.read_text())
        results.append(result)
        print(json.dumps(result), flush=True)
        if not result["converged"] or result["energy_hartree"] is None:
            raise RuntimeError(f"{name}: no valid converged energy")
        case_metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    # Publish only a complete result set to the synchronized project directory.
    (root / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
