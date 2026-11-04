import pathlib
import re
from bs4 import BeautifulSoup

root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
html_file = root / "mobile_app" / "index.html"
js_file = root / "simulator" / "static" / "js" / "mobile_app.js"

html = html_file.read_text(encoding="utf-8")
js = js_file.read_text(encoding="utf-8")

soup = BeautifulSoup(html, "html.parser")

events = []
for tag in soup.find_all(True):
    for k, v in tag.attrs.items():
        if k.lower().startswith("on"):
            events.append((tag.name, tag.get("id", ""), k, v))

print(f"Total inline event handlers in index.html: {len(events)}")
for t, tid, attr, val in events:
    print(f"[{t}] id='{tid}' {attr}='{val}'")

window_exports = set(re.findall(r"(?:window|globalThis)\.([a-zA-Z0-9_$]+)\s*=", js))
declared_funcs = set(re.findall(r"(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(", js))
arrow_funcs = set(re.findall(r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", js))
all_funcs = window_exports | declared_funcs | arrow_funcs

print("\n--- Window Exports in mobile_app.js ---")
for fn in sorted(window_exports):
    print(f"window.{fn}")

print("\n--- Event handler coverage check ---")
for t, tid, attr, val in events:
    m = re.findall(r"([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(", str(val))
    for fn in m:
        if fn in {"if", "for", "while", "return", "this"}:
            continue
        status = "OK" if (fn in all_funcs or fn in window_exports) else "MISSING"
        if status == "MISSING":
            print(f"WARNING: {fn} called in {attr} of {tid} is not found in JS!")
