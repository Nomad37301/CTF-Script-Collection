import sys
import os
import time
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
import requests

# -----------------------------
# Configuration 
# -----------------------------
DEFAULT_CONCURRENCY = 4
DEFAULT_DELAY = 0.25  # seconds between requests in same worker
OUT_DIR = "aggressive_probe_outputs"
MAX_PROBE_LEN = 20000   # safety cap per single probe
REQUEST_TIMEOUT = 15    # seconds

# -----------------------------
# Probe generator (safe)
# -----------------------------
def generate_probes():
    base = []

    # Basic arithmetic / whitespace variations
    base += [
        "1+1", "1 + 1", "1\t+\t1", "1\n+\n1", "   1+1   ",
        "2*3+4/5-6", "100-50*2+3/4", "0", "-1", "+2",
        "1e3", "1e-3", "3.1415", "10/2", "1/3", "1/0"
    ]

    # Delimiters (empty and with spaces) and single/only open/close
    base += [
        "()", "( )", "(  )", "(", ")", "{}", "{ }", "{  }", "[", "]", "[ ]"
    ]

    # Quotes empty / with space (but not including text inside)
    base += [
        "''", "'' ", "' '", '""', '"" ', '" "'
    ]

    # Operators edgecases
    base += [
        "1++2", "1--2", "1**2", "1^2", "1%2", "1//2", "++--", "+-*/%",
        "=== ", "==", "=1", "1=1"
    ]

    # Comments & newline/backslash variants
    base += [
        "# comment only", "1+1 # trailing comment", "\\", "\\n", "\\t", "\\\\"
    ]

    # Dots, attribute-like tokens (just punctuation)
    base += [
        ".", "..", "...", ". .", ".1", "1.", ". + ."
    ]

    # Unicode homoglyphs and fullwidth characters (visually similar)
    base += [
        "1\uFF0B1",  # fullwidth plus
        "1\u22121",  # minus sign
        "1\u00B2 + 2",  # superscript two as part of token (non-eval)
    ]

    # Long arithmetic chains (increasing length) - safe but large
    for n in (50, 200, 1000):
        expr = " + ".join(["1"] * n)
        base.append(expr)

    # Repeated patterns that test filters
    base += [
        "(" * 1 + ")" * 1,  # "()"
        "(" * 5 + ")" * 5,  # nested empties
        "'\"'", "\"'\"",  # quote mixes
    ]

    # Encoded / escaped forms (to test normalization)
    base += [
        "%28", "%29", "%7B", "%7D", "\\(", "\\)", "\\'", '\\"'
    ]

    # Combined permutations (safely built) - don't insert user-supplied or function calls
    combos = []
    for a in ["1+1", "1*2", "3-1"]:
        for b in ["", " ", " #x", " %20"]:
            combos.append(a + b)
    base += combos

    # Filter out any probe that looks like a function call or attribute access to be safe
    safe = []
    for p in base:
        # disallow parentheses content not empty OR any '(' followed by non-space (to respect user's filter findings)
        # But we still include parentheses variants that are empty or only whitespace/newlines/tabs.
        if len(p) > MAX_PROBE_LEN:
            continue
        # disallow any letters followed by "(" (function call style) or presence of "__" (dunder)
        if re.search(r"[A-Za-z_]\s*\(", p):
            continue
        if "__" in p:
            continue
        if re.search(r"\b(import|eval|exec|os|sys|subprocess|open)\b", p, flags=re.IGNORECASE):
            continue
        safe.append(p)
    # Deduplicate while preserving order
    seen = set()
    final = []
    for p in safe:
        if p not in seen:
            final.append(p)
            seen.add(p)
    return final

# -----------------------------
# Request worker
# -----------------------------
def safe_post(target, expr, use_json=False, index=0, out_dir=OUT_DIR):
    if len(expr) > MAX_PROBE_LEN:
        return {"expr": expr, "error": "probe-too-long", "index": index}
    payload = {"expr": expr}
    headers = {}
    try:
        if use_json:
            r = requests.post(target, json=payload, timeout=REQUEST_TIMEOUT)
        else:
            r = requests.post(target, data=payload, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        return {"expr": expr, "index": index, "status": "ERR", "error": str(e)}

    # Save full HTML
    safe_name = re.sub(r"[^0-9a-zA-Z._-]", "_", expr)[:80] or f"probe_{index}"
    filename = f"{index:04d}_{safe_name}.html"
    os.makedirs(out_dir, exist_ok=True)
    fullpath = os.path.join(out_dir, filename)
    with open(fullpath, "w", encoding="utf-8", errors="replace") as f:
        f.write(r.text)

    # Extract <pre> content (if present)
    pre_matches = re.findall(r"<pre[^>]*>(.*?)</pre>", r.text, flags=re.IGNORECASE | re.DOTALL)
    pre_clean = []
    for m in pre_matches:
        # remove HTML tags inside and condense whitespace
        t = re.sub(r"<[^>]+>", "", m)
        t = re.sub(r"\s+", " ", t).strip()
        pre_clean.append(t)
    pre_joined = "\n".join(pre_clean)

    result = {
        "expr": expr,
        "index": index,
        "status_code": r.status_code,
        "elapsed": None,
        "file": fullpath,
        "pre": pre_joined,
        "snippet": r.text[:2000].replace("\n", "\\n")
    }
    return result

# -----------------------------
# Main orchestration
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Aggressive but safe probe script")
    parser.add_argument("target", help="Target URL (e.g. http://example.com/if-i-could-be-a-cons.php)")
    parser.add_argument("--json", action="store_true", help="Send JSON payload instead of form")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay in seconds between requests per worker")
    parser.add_argument("--outdir", default=OUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Limit number of probes to first N (0 = all)")
    args = parser.parse_args()

    target = args.target
    use_json = args.json
    concurrency = max(1, args.concurrency)
    delay = max(0.0, args.delay)
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    probes = generate_probes()
    if args.limit > 0:
        probes = probes[:args.limit]

    print(f"[+] Target: {target}")
    print(f"[+] Probes: {len(probes)}  concurrency={concurrency} delay={delay}s use_json={use_json}")

    results = []
    idx = 0
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {}
        for i, p in enumerate(probes):
            # submit with small stagger to avoid bursting
            futures[ex.submit(safe_post, target, p, use_json, i, outdir)] = (i, p)
            time.sleep(delay)

        for fut in as_completed(futures):
            i, p = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"expr": p, "index": i, "status": "ERR", "error": str(e)}
            results.append(res)
            # basic console output
            st = res.get("status_code") or res.get("status") or res.get("error", "")
            print(f"[{res.get('index')}] {repr(res.get('expr'))} -> {st}")

    # Save results to JSON and CSV summary
    ts = int(time.time())
    json_path = os.path.join(outdir, f"results_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    # Basic CSV summary
    import csv
    csv_path = os.path.join(outdir, f"summary_{ts}.csv")
    with open(csv_path, "w", newline='', encoding="utf-8") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["index", "expr", "status_code", "file", "pre_snippet"])
        for r in results:
            writer.writerow([r.get("index"), r.get("expr"), r.get("status_code"), r.get("file"), (r.get("pre") or "")[:200]])
    print()
    print("[+] Done.")
    print("  JSON results:", json_path)
    print("  CSV summary  :", csv_path)
    print("  Full HTML per-probe saved under:", outdir)

if __name__ == "__main__":
    main()
