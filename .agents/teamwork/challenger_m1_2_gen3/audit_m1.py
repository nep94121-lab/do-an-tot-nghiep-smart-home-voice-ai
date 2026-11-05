import pathlib
from bs4 import BeautifulSoup

ROOT = pathlib.Path(".")
PAGES = {
    "/": ROOT / "simulator/static/index.html",
    "/auth": ROOT / "simulator/static/auth.html",
    "/wokwi": ROOT / "simulator/static/wokwi.html",
    "/logs": ROOT / "simulator/static/logs.html",
    "/app": ROOT / "mobile_app/index.html",
    "/guest_enroll": ROOT / "simulator/static/guest_enroll.html",
    "/login": ROOT / "simulator/static/login.html",
    "/register": ROOT / "simulator/static/register.html",
}

print("========================================")
print("AUDIT PART 1: 8-ROUTE MATRIX & DOM ATTRIBUTES")
print("========================================")
routes = list(PAGES.keys())
matrix_results = {}

for current_route, path in PAGES.items():
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    all_links = soup.find_all("a", href=True)
    href_to_tags = {}
    for a in all_links:
        href = a.get("href")
        if href in routes:
            href_to_tags.setdefault(href, []).append(a)

    print(f"\nPage: {current_route} ({path.name})")
    missing = [r for r in routes if r not in href_to_tags]
    if missing:
        print(f"  [FAIL] Missing routes: {missing}")
    else:
        print("  [PASS] All 8 routes present.")

    # Check active classes and aria-current="page"
    self_links = href_to_tags.get(current_route, [])
    active_found = False
    aria_page_found = False
    for a in self_links:
        classes = a.get("class", [])
        if "active" in classes:
            active_found = True
        if a.get("aria-current") == "page":
            aria_page_found = True

    print(f"  Self-link count: {len(self_links)}")
    print(f"  Has 'active' class on self-link: {active_found}")
    print(f"  Has aria-current='page' on self-link: {aria_page_found}")
    matrix_results[current_route] = {
        "missing": missing,
        "active": active_found,
        "aria_page": aria_page_found,
    }

print("\n========================================")
print("AUDIT PART 2: CREDENTIAL MASKING & STATIC VALUE")
print("========================================")
for current_route, path in PAGES.items():
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    all_inputs = soup.find_all("input")
    pw_inputs = [i for i in all_inputs if i.get("type") == "password" or "password" in i.get("id", "").lower() or "password" in i.get("name", "").lower()]
    print(f"\nPage: {current_route} ({path.name}) - Found {len(pw_inputs)} password input(s)")
    for p in pw_inputs:
        val = p.get("value")
        has_val_attr = "value" in p.attrs
        is_empty = (val == "")
        status = "PASS" if (has_val_attr and is_empty) else "WARN/FAIL"
        print(f"  [{status}] id={p.get('id')} name={p.get('name')} type={p.get('type')} has_value_attr={has_val_attr} value='{val}'")

print("\n========================================")
print("AUDIT PART 3: HTML PURITY & ENCODING")
print("========================================")
import re
for current_route, path in PAGES.items():
    raw = path.read_bytes()
    text = path.read_text(encoding="utf-8")
    crlf = raw.count(b"\r\n")
    bom = raw.startswith(b"\xef\xbb\xbf")
    styles = re.findall(r"<style\b", text, re.IGNORECASE)
    scripts = re.findall(r"<script\b([^>]*)>", text, re.IGNORECASE)
    inline_scripts = [s for s in scripts if "src=" not in s.lower()]
    print(f"Page: {current_route:14} CRLF={crlf} BOM={bom} <style>_tags={len(styles)} inline_<script>={len(inline_scripts)}")
