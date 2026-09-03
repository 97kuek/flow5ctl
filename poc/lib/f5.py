"""Minimal harness for flow5 PoC verification. Not production code."""
import math
import os
import pathlib
import shutil
import subprocess
import time

FLOW5 = "/Applications/flow5.app/Contents/MacOS/flow5"

def naca4(code, n=80):
    m = int(code[0])/100.0; p = int(code[1])/10.0; t = int(code[2:])/100.0
    def cam(x):
        if p == 0: return 0.0, 0.0
        if x < p: return m/p**2*(2*p*x-x*x), 2*m/p**2*(p-x)
        return m/(1-p)**2*((1-2*p)+2*p*x-x*x), 2*m/(1-p)**2*(p-x)
    def th(x):
        return 5*t*(0.2969*math.sqrt(x)-0.1260*x-0.3516*x**2+0.2843*x**3-0.1036*x**4)
    xs = [(1-math.cos(i*math.pi/n))/2 for i in range(n+1)]
    up, lo = [], []
    for x in xs:
        yc, dy = cam(x); tt = th(x); a = math.atan(dy)
        up.append((x-tt*math.sin(a), yc+tt*math.cos(a)))
        lo.append((x+tt*math.sin(a), yc-tt*math.cos(a)))
    return list(reversed(up)) + lo[1:]

def write_foil(path, name, pts):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(name+"\n")
        for x, y in pts: f.write(f"{x:11.7f} {y:11.7f}\n")

def run(script_path, timeout=600, progress=True):
    """Run flow5 on a script. Returns (elapsed, stdout)."""
    cmd = [FLOW5] + (["-p"] if progress else []) + ["-s", str(script_path)]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") + "\n***TIMEOUT***"
    return time.time()-t0, out

MARKERS = {
    "script_rejected":  "Error reading script...aborting",
    "script_ok":        "Script imported, no parsing error",
    "foils_missing":    "foils not found ...discarding this plane",
    "no_pairs":         "Made 0 valid analysis pairs",
    "panel_ok":         "Panel analysis completed successfully",
    "panel_err":        "Panel analysis completed ... Errors encountered",
    "llt_ok":           "LLT analysis completed successfully",
    "llt_err":          "LLT analysis completed ... Errors encountered",
}

def verdict(out):
    hits = [k for k, v in MARKERS.items() if v in out]
    if "script_rejected" in hits: return "SCRIPT_REJECTED", hits
    if "panel_ok" in hits or "llt_ok" in hits: return "OK", hits
    if "panel_err" in hits or "llt_err" in hits: return "SOLVER_ERROR", hits
    return "UNKNOWN", hits

def clean(d):
    if os.path.exists(d): shutil.rmtree(d)
    os.makedirs(d, exist_ok=True)

def polar_table(csv_path):
    """Parse a flow5 polar CSV -> (header_dict, colnames, rows)."""
    txt = pathlib.Path(csv_path).read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines()
    hi = None
    for i, ln in enumerate(lines):
        if "CL" in ln and ("α" in ln or "alpha" in ln.lower()) and "CD" in ln:
            hi = i; break
    if hi is None: return {}, [], []
    cols = lines[hi].split()
    rows = []
    for ln in lines[hi+1:]:
        parts = ln.split()
        if len(parts) < 5: continue
        try: rows.append([float(x) for x in parts])
        except ValueError: continue
    hdr = {}
    for ln in lines[:hi]:
        if "=" in ln:
            k, _, v = ln.partition("=")
            hdr[k.strip()] = v.strip()
    return hdr, cols, rows
