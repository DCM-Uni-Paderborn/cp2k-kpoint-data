#!/usr/bin/env python3
"""Build publication tables from raw CP2K outputs; never insert reference data."""
import json
from pathlib import Path
import re
from run_validation import parse_output

ROOT = Path(__file__).resolve().parent
results = json.loads((ROOT / "results.json").read_text())
if len(results) != 18:
    raise SystemExit("All 18 calculations must finish before generating tables")
for r in results:
    output = (ROOT / r["case"] / "sample.out").read_text()
    if output.count("PROGRAM STARTED AT") != 1 or "PROGRAM ENDED AT" not in output:
        raise SystemExit(f"Incomplete or appended output: {r['case']}")
    r.update(parse_output(output))
    if not r["converged"] or r["energy_hartree"] is None or r["nk"] is None:
        raise SystemExit(f"Missing result: {r['case']}")
    stress = re.search(r"STRESS\| Analytical stress tensor \[bar\](.*?)STRESS\| 1/3 Trace", output, re.S)
    if not stress:
        raise SystemExit(f"Missing stress: {r['case']}")
    r["stress_bar"] = [[float(v) for v in row] for row in re.findall(
        r"STRESS\|\s+[xyz]\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)\s+([-+\d.Ee]+)", stress[1])]
    if len(r["stress_bar"]) != 3 or len(r.get("forces_hartree_per_bohr", [])) != {"Si": 8, "Al": 4}[r["element"]]:
        raise SystemExit(f"Incomplete force or stress tensor: {r['case']}")


def table(caption, label, spec, heading, rows):
    return "\n".join([r"\begin{table}[htbp]", r"\centering\small\setlength{\tabcolsep}{4pt}", r"\caption{" + caption + "}",
                      r"\label{" + label + "}", r"\begin{tabular}{" + spec + "}", r"\toprule",
                      heading + r" \\", r"\midrule", *[r + r" \\" for r in rows],
                      r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])


mesh_rows, compare_rows = [], []
for element, atoms in (("Si", 8), ("Al", 4)):
    ref = next(r for r in results if r["element"] == element and r["mesh"] == 4 and r["mode"] == "full" and r["fft"] == "OFF")
    mesh_ref = next(r for r in results if r["element"] == element and r["mesh"] == 8 and r["mode"] == "full" and r["fft"] == "OFF")
    for r in results:
        if r["element"] != element:
            continue
        if r["mode"] == "full" and r["fft"] == "OFF":
            delta_mev = (r["energy_hartree"] - mesh_ref["energy_hartree"]) / atoms * 27211.386245988
            mu = "--" if r["fermi_hartree"] is None else f"{r['fermi_hartree']:.8f}"
            mesh_rows.append(f"{element} & ${r['mesh']}^3$ & {r['energy_hartree']/atoms:.10f} & {delta_mev:.3f} & {mu}")
        if r["mesh"] == 4:
            de = abs(r["energy_hartree"] - ref["energy_hartree"])
            df = max(abs(a-b) for x, y in zip(r["forces_hartree_per_bohr"], ref["forces_hartree_per_bohr"], strict=True) for a,b in zip(x,y,strict=True))
            ds = max(abs(a-b) for x, y in zip(r["stress_bar"], ref["stress_bar"], strict=True) for a,b in zip(x,y,strict=True))
            mode = {"full": "Full", "time-reversal": "Time reversal", "K290":"K290", "SPGLIB":"SPGLIB"}[r["mode"]]
            if r["fft"] == "ON":
                mode += ", FFT requested"
            def sci(x):
                return "$" + ("0" if x == 0 else f"{x:.1e}".replace("e-", r"\times10^{-") + "}") + "$"
            compare_rows.append(f"{element} & {mode} & {int(r['nk'])} & {sci(de)} & {sci(df)} & {sci(ds)}")

tables = table(
    "Mesh dependence for conventional cubic Si and Al cells. The tabulated quantity is energy per atom for Si and electronic free energy per atom for Al at 1000 K. Differences refer to the corresponding full $8^3$ mesh. This mesh sequence does not establish the infinite-mesh or complete-basis limit. Chemical potentials use CP2K's internal energy zero.",
    "tab:mesh-validation", "llrrr", r"System & Mesh & $E/N$ or $\mathcal F/N$ ($E_h$) & $\Delta$ (meV/atom) & $\mu$ ($E_h$)", mesh_rows)
tables += table(
    "Same-mesh comparisons at $4^3$, relative to the direct full-grid result. Columns report solved k-points, absolute cell-energy/free-energy differences, maximum force-component differences, and maximum stress-component differences. All runs use one OpenMP thread. The FFT label records the requested option. Independent transform unit tests also check the FFT algebra.",
    "tab:symmetry-validation", "llrrrr", r"System & Mode & $N_k$ & $|\Delta E|$ ($E_h$) & $\|\Delta F\|_\infty$ ($E_h/a_0$) & $\|\Delta\sigma\|_\infty$ (bar)", compare_rows)
(ROOT.parent / "validation_tables.tex").write_text(tables)
print(tables)
