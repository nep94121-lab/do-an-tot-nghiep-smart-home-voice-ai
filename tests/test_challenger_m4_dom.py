"""Bộ Kiểm Thử Đối Kháng Thực Nghiệm DOM & Event Handlers Milestone M4.

Người thực hiện: challenger_m4_1 (Role: M4 DOM Challenger)
Mục tiêu kiểm định:
1. Quét toàn bộ sự kiện inline trong DOM (onclick, onchange, oninput, onsubmit, onkeydown, v.v.)
   trên toàn bộ 6 trang frontend sau khi bóc tách.
2. Trích xuất danh sách tất cả các hàm JavaScript được gọi từ DOM và đối chiếu 100% với
   khai báo / export window.* trong file JS tương ứng.
3. Kiểm tra tính toàn vẹn các selector document.getElementById() / document.querySelector('#...')
   giữa file JS và các phần tử tồn tại trong DOM HTML tương ứng, kiểm tra bảo vệ null-safe guard.
4. Kiểm tra mọi lệnh gán sự kiện qua .addEventListener(...) không bao giờ dereference trên null.
5. Kiểm tra thực nghiệm tải và thực thi an toàn các file JS trong môi trường Node.js DOM Mock (Headless VM).
6. Đưa ra phán quyết thực nghiệm độc lập: CONFIRMED hoặc DISPROVED.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Dict, List, Set, Tuple
from bs4 import BeautifulSoup
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

PAGE_PAIRS = [
    {
        "name": "index",
        "html_path": ROOT / "simulator" / "static" / "index.html",
        "js_paths": [
            ROOT / "simulator" / "static" / "js" / "app.js",
            ROOT / "simulator" / "static" / "house3d.js",
        ],
    },
    {
        "name": "auth",
        "html_path": ROOT / "simulator" / "static" / "auth.html",
        "js_paths": [
            ROOT / "simulator" / "static" / "js" / "auth.js",
        ],
    },
    {
        "name": "guest_enroll",
        "html_path": ROOT / "simulator" / "static" / "guest_enroll.html",
        "js_paths": [
            ROOT / "simulator" / "static" / "js" / "guest_enroll.js",
        ],
    },
    {
        "name": "wokwi",
        "html_path": ROOT / "simulator" / "static" / "wokwi.html",
        "js_paths": [
            ROOT / "simulator" / "static" / "js" / "wokwi.js",
        ],
    },
    {
        "name": "logs",
        "html_path": ROOT / "simulator" / "static" / "logs.html",
        "js_paths": [
            ROOT / "simulator" / "static" / "js" / "logs.js",
        ],
    },
    {
        "name": "mobile_app",
        "html_path": ROOT / "mobile_app" / "index.html",
        "js_paths": [
            ROOT / "simulator" / "static" / "js" / "mobile_app.js",
        ],
    },
]

BUILTIN_FUNCS = {
    "alert", "confirm", "prompt", "console.log", "console.error", "console.warn",
    "history.back", "location.reload", "event.stopPropagation", "event.preventDefault",
    "void", "parseInt", "parseFloat", "encodeURIComponent", "decodeURIComponent"
}

EVENT_ATTR_REGEX = re.compile(r"^on[a-z]+$", re.IGNORECASE)
CALL_EXTRACT_REGEX = re.compile(r"([a-zA-Z_$][a-zA-Z0-9_$]*(?:\.[a-zA-Z_$][a-zA-Z0-9_$]*)?)\s*\(")
STR_LITERAL_REGEX = re.compile(r"(\'(?:\\.|[^\'\\])*\'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)")


def clean_js_expression(expr: str) -> str:
    """Loại bỏ chuỗi ký tự bên trong tham số hàm để tránh trích xuất nhầm các từ khóa trong chuỗi (ví dụ SQL)."""
    return STR_LITERAL_REGEX.sub("''", expr)


def extract_inline_events(html_content: str) -> List[Dict]:
    """Trích xuất tất cả các sự kiện inline từ DOM HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    events = []
    for tag in soup.find_all(True):
        for attr, val in tag.attrs.items():
            if EVENT_ATTR_REGEX.match(attr):
                val_str = " ".join(val) if isinstance(val, list) else str(val)
                cleaned_expr = clean_js_expression(val_str)
                calls = []
                for match in CALL_EXTRACT_REGEX.finditer(cleaned_expr):
                    fn_name = match.group(1).strip()
                    if fn_name not in {"if", "for", "while", "switch", "catch", "return"}:
                        calls.append(fn_name)
                events.append({
                    "tag": tag.name,
                    "id": tag.get("id", ""),
                    "attr": attr.lower(),
                    "expr": val_str,
                    "calls": calls,
                })
    return events


def extract_html_ids(html_content: str) -> Set[str]:
    """Trích xuất tất cả các ID phần tử có trong DOM HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    ids = set()
    for tag in soup.find_all(True):
        if tag.has_attr("id"):
            tag_id = tag["id"].strip()
            if tag_id:
                ids.add(tag_id)
    return ids


def extract_js_symbols_and_ids(js_content: str) -> Tuple[Set[str], Set[str], Set[str]]:
    """Trích xuất:
    1. Các hàm được export lên window / global (window.foo = ...)
    2. Các hàm được khai báo (function foo(...) hoặc const/let foo = ...)
    3. Các selector ID được truy vấn (document.getElementById('foo'), document.querySelector('#foo'))
    """
    window_exports = set(re.findall(r"(?:window|globalThis)\.([a-zA-Z0-9_$]+)\s*=", js_content))
    declared_funcs = set(re.findall(r"(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(", js_content))
    arrow_funcs = set(re.findall(r"(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", js_content))

    all_available_funcs = window_exports | declared_funcs | arrow_funcs

    by_id = set(re.findall(r"document\.getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", js_content))
    by_qs = set(re.findall(r"document\.querySelector(?:All)?\(\s*['\"]#([a-zA-Z0-9_\-]+)['\"]\s*\)", js_content))
    all_queried_ids = by_id | by_qs

    return window_exports, all_available_funcs, all_queried_ids


def check_unconditional_id_access(js_content: str, missing_id: str) -> List[str]:
    """Kiểm tra xem một ID bị thiếu có bị truy cập trực tiếp không qua null-guard hay không."""
    dangerous_patterns = [
        rf"document\.getElementById\(\s*['\"]{re.escape(missing_id)}['\"]\s*\)\.[a-zA-Z_$]",
        rf"document\.querySelector\(\s*['\"]#{re.escape(missing_id)}['\"]\s*\)\.[a-zA-Z_$]",
    ]
    violations = []
    for pat in dangerous_patterns:
        matches = re.findall(pat, js_content)
        if matches:
            violations.extend(matches)
    return violations


def extract_chained_listeners(js_content: str) -> List[Tuple[str, int]]:
    """Tìm tất cả các trường hợp gọi chained trực tiếp document.getElementById('...').addEventListener(...)."""
    results = []
    pattern = re.compile(r"document\.getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)\.addEventListener\(")
    for line_no, line in enumerate(js_content.splitlines(), start=1):
        for m in pattern.finditer(line):
            results.append((m.group(1), line_no))
    return results


NODE_HEADLESS_RUNNER = """
const fs = require('fs');
const vm = require('vm');

function createMockElement(id) {
  return {
    id: id || '',
    addEventListener: () => {},
    removeEventListener: () => {},
    style: {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    innerText: '',
    textContent: '',
    innerHTML: '',
    value: '',
    checked: false,
    disabled: false,
    appendChild: () => {},
    removeChild: () => {},
    setAttribute: () => {},
    getAttribute: () => null,
    hasAttribute: () => false,
    removeAttribute: () => {},
    scrollIntoView: () => {},
    focus: () => {},
    blur: () => {},
    click: () => {}
  };
}

const file = process.argv[1];
const code = fs.readFileSync(file, 'utf8');
const mockWindow = {
  location: { href: 'http://localhost:8088', search: '', protocol: 'http:', host: 'localhost:8088', pathname: '/' },
  addEventListener: () => {},
  removeEventListener: () => {},
  setTimeout: () => {},
  clearTimeout: () => {},
  setInterval: () => {},
  clearInterval: () => {},
  AudioContext: class { createMediaStreamSource() { return { connect() {} }; } },
  webkitAudioContext: class {},
  navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) }, clipboard: { writeText: async () => {} } },
  document: {
    getElementById: (id) => createMockElement(id),
    querySelector: () => createMockElement(),
    querySelectorAll: () => [],
    createElement: (tag) => createMockElement(tag),
    addEventListener: () => {},
    removeEventListener: () => {}
  },
  WebSocket: class { constructor() {} addEventListener() {} send() {} close() {} },
  fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} }
};
mockWindow.window = mockWindow;
mockWindow.globalThis = mockWindow;
mockWindow.document.defaultView = mockWindow;

const ctx = vm.createContext(mockWindow);
try {
  vm.runInContext(code, ctx);
  process.stdout.write(JSON.stringify({ ok: true }));
} catch (err) {
  process.stdout.write(JSON.stringify({ ok: false, error: err.message, stack: err.stack }));
}
"""


# =============================================================================
# PYTEST TEST SUITE
# =============================================================================

class TestMilestoneM4DomIntegrity:
    """Kiểm thử tính toàn vẹn DOM và liên kết sự kiện 6 trang giao diện."""

    @pytest.mark.parametrize("page", PAGE_PAIRS, ids=[p["name"] for p in PAGE_PAIRS])
    def test_all_inline_event_handlers_resolved(self, page):
        """Mọi hàm được gọi từ inline event handler trong HTML phải tồn tại và được export lên window."""
        html_content = page["html_path"].read_text(encoding="utf-8")
        events = extract_inline_events(html_content)

        js_content = ""
        for js_p in page["js_paths"]:
            assert js_p.exists(), f"File JS {js_p} không tồn tại!"
            js_content += "\n" + js_p.read_text(encoding="utf-8")

        window_exports, available_funcs, _ = extract_js_symbols_and_ids(js_content)

        unresolved = []
        for ev in events:
            for fn in ev["calls"]:
                if fn in BUILTIN_FUNCS:
                    continue
                if fn.startswith("window."):
                    clean_fn = fn.split(".", 1)[1]
                    if clean_fn not in window_exports and clean_fn not in available_funcs:
                        unresolved.append((ev["attr"], ev["expr"], fn))
                elif fn.startswith("this.") or fn.startswith("event.") or fn.startswith("document."):
                    continue
                else:
                    if fn not in window_exports and fn not in available_funcs:
                        unresolved.append((ev["attr"], ev["expr"], fn))

        assert not unresolved, (
            f"Trang {page['name']} có các hàm inline bị thiếu hoặc chưa export lên window: {unresolved}"
        )

    @pytest.mark.parametrize("page", PAGE_PAIRS, ids=[p["name"] for p in PAGE_PAIRS])
    def test_window_exports_match_inline_events(self, page):
        """Đối chiếu số lượng hàm inline được gọi và kiểm tra xem 100% có nằm trong window_exports."""
        html_content = page["html_path"].read_text(encoding="utf-8")
        events = extract_inline_events(html_content)

        js_content = ""
        for js_p in page["js_paths"]:
            js_content += "\n" + js_p.read_text(encoding="utf-8")

        window_exports, _, _ = extract_js_symbols_and_ids(js_content)

        called_funcs = set()
        for ev in events:
            for fn in ev["calls"]:
                if fn not in BUILTIN_FUNCS and not fn.startswith(("this.", "event.", "document.")):
                    clean_fn = fn.split(".", 1)[1] if fn.startswith("window.") else fn
                    called_funcs.add(clean_fn)

        missing_from_window = called_funcs - window_exports
        assert not missing_from_window, (
            f"Trang {page['name']} có các hàm inline chưa được gán tường minh vào window: {missing_from_window}"
        )

    @pytest.mark.parametrize("page", PAGE_PAIRS, ids=[p["name"] for p in PAGE_PAIRS])
    def test_no_unconditional_null_dereference_on_missing_ids(self, page):
        """Kiểm tra không có bất kỳ selector ID nào bị thiếu mà bị gọi dereference trực tiếp gây TypeError."""
        html_content = page["html_path"].read_text(encoding="utf-8")
        html_ids = extract_html_ids(html_content)

        js_content = ""
        for js_p in page["js_paths"]:
            js_content += "\n" + js_p.read_text(encoding="utf-8")

        _, _, queried_ids = extract_js_symbols_and_ids(js_content)
        missing_ids = queried_ids - html_ids

        violations = {}
        for m_id in missing_ids:
            v = check_unconditional_id_access(js_content, m_id)
            if v:
                violations[m_id] = v

        assert not violations, (
            f"Trang {page['name']} có các ID thiếu trong HTML nhưng bị dereference trực tiếp: {violations}"
        )

    @pytest.mark.parametrize("page", PAGE_PAIRS, ids=[p["name"] for p in PAGE_PAIRS])
    def test_chained_event_listeners_target_valid_elements(self, page):
        """Kiểm tra các phần tử dùng document.getElementById(...).addEventListener(...) đều tồn tại 100% trong HTML."""
        html_content = page["html_path"].read_text(encoding="utf-8")
        html_ids = extract_html_ids(html_content)

        js_content = ""
        for js_p in page["js_paths"]:
            js_content += "\n" + js_p.read_text(encoding="utf-8")

        chained = extract_chained_listeners(js_content)
        invalid_chained = [(target_id, line) for target_id, line in chained if target_id not in html_ids]

        assert not invalid_chained, (
            f"Trang {page['name']} có chained addEventListener gắn vào ID không tồn tại trong HTML: {invalid_chained}"
        )

    @pytest.mark.parametrize("page", PAGE_PAIRS, ids=[p["name"] for p in PAGE_PAIRS])
    def test_node_syntax_validation(self, page):
        """Kiểm tra cú pháp của tất cả các file JS bằng Node.js CLI --check."""
        for js_p in page["js_paths"]:
            cmd = ["node", "--check", str(js_p)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            assert proc.returncode == 0, f"Lỗi cú pháp Node.js trong {js_p}: {proc.stderr}"

    @pytest.mark.parametrize("page", PAGE_PAIRS, ids=[p["name"] for p in PAGE_PAIRS])
    def test_node_headless_runtime_evaluation(self, page):
        """Kiểm tra thực nghiệm tải và thực thi file JS trong môi trường Node VM mô phỏng trình duyệt.
        Bắt lỗi Uncaught ReferenceError khi file JS được nạp vào browser.
        """
        for js_p in page["js_paths"]:
            # Chỉ chạy cho các file JS chính trong simulator/static/js/
            if "vendor" in str(js_p) or "house3d" in str(js_p):
                continue
            proc = subprocess.run(
                ["node", "-e", NODE_HEADLESS_RUNNER, str(js_p)],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            assert proc.stdout, f"Node không sinh output cho {js_p}: {proc.stderr}"
            data = json.loads(proc.stdout)
            assert data["ok"], f"Lỗi Runtime khi nạp {js_p}: {data.get('error')} -> {data.get('stack')}"


if __name__ == "__main__":
    print("=== PHÂN TÍCH ĐỐI KHÁNG THỰC NGHIỆM DOM & EVENT HANDLERS (M4) ===\n")
    total_events = 0
    total_window_exports = 0
    total_chained = 0
    all_pages_clean = True

    for p in PAGE_PAIRS:
        html_content = p["html_path"].read_text(encoding="utf-8")
        events = extract_inline_events(html_content)
        html_ids = extract_html_ids(html_content)

        js_content = ""
        for js_p in p["js_paths"]:
            js_content += "\n" + js_p.read_text(encoding="utf-8")

        window_exports, available_funcs, queried_ids = extract_js_symbols_and_ids(js_content)

        called_funcs = set()
        for ev in events:
            for fn in ev["calls"]:
                if fn not in BUILTIN_FUNCS and not fn.startswith(("this.", "event.", "document.")):
                    clean_fn = fn.split(".", 1)[1] if fn.startswith("window.") else fn
                    called_funcs.add(clean_fn)

        missing_export = called_funcs - window_exports
        missing_ids = queried_ids - html_ids

        violations = {}
        for m_id in missing_ids:
            v = check_unconditional_id_access(js_content, m_id)
            if v:
                violations[m_id] = v

        chained = extract_chained_listeners(js_content)
        invalid_chained = [(target_id, line) for target_id, line in chained if target_id not in html_ids]

        # Kiểm tra chạy Node Headless
        headless_errors = []
        for js_p in p["js_paths"]:
            if "vendor" in str(js_p) or "house3d" in str(js_p):
                continue
            proc = subprocess.run(
                ["node", "-e", NODE_HEADLESS_RUNNER, str(js_p)],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if proc.stdout:
                try:
                    res_data = json.loads(proc.stdout)
                    if not res_data.get("ok"):
                        headless_errors.append(f"{js_p.name}: {res_data.get('error')}")
                except Exception as ex:
                    headless_errors.append(f"{js_p.name}: {ex}")

        total_events += len(events)
        total_window_exports += len(window_exports)
        total_chained += len(chained)

        print(f"📄 TRANG: {p['name'].upper()} ({p['html_path'].name})")
        print(f"  ├─ Số sự kiện inline trong DOM: {len(events)}")
        print(f"  ├─ Danh sách hàm gọi từ DOM: {sorted(list(called_funcs)) if called_funcs else '(Không dùng inline event)'}")
        print(f"  ├─ Số hàm gán window.* trong JS: {len(window_exports)}")
        print(f"  ├─ Hàm gọi từ DOM thiếu window export: {'KHÔNG CÓ (100% KHỚP)' if not missing_export else missing_export}")
        print(f"  ├─ Số ID trong HTML: {len(html_ids)}")
        print(f"  ├─ Số ID truy cập trong JS: {len(queried_ids)}")
        print(f"  ├─ ID JS truy vấn không có trong HTML: {sorted(list(missing_ids)) if missing_ids else '0'}")
        print(f"  ├─ Dereference nguy hiểm trên ID thiếu: {'KHÔNG CÓ (An toàn 100%)' if not violations else violations}")
        print(f"  ├─ Chained addEventListener: {len(chained)} vị trí")
        print(f"  ├─ Chained addEventListener gãy: {'KHÔNG CÓ (100% TỒN TẠI)' if not invalid_chained else invalid_chained}")
        print(f"  └─ Thực thi Headless DOM: {'THÀNH CÔNG' if not headless_errors else 'THẤT BẠI: ' + str(headless_errors)}\n")

        if missing_export or violations or invalid_chained or headless_errors:
            all_pages_clean = False

    print("=================================================================")
    print(f"TỔNG CỘNG SỰ KIỆN INLINE QUÉT ĐƯỢC: {total_events}")
    print(f"TỔNG SỐ HÀM EXPORT TRÊN WINDOW.*: {total_window_exports}")
    print(f"TỔNG SỐ CHAINED EVENT LISTENERS: {total_chained}")
    print(f"KẾT LUẬN TOÀN DIỆN: {'CONFIRMED (100% AN TOÀN & HỢP LỆ)' if all_pages_clean else 'DISPROVED (PHÁT HIỆN LỖI)'}")
    print("=================================================================")
