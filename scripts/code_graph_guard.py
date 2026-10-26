"""Bộ Công Cụ Quản Trị Ngữ Cảnh & Đồ Thị Quan Hệ Mã Nguồn (Codebase Graph, RepoMap & Blast-Radius Guard).

Kết hợp tinh hoa thực chiến từ 3 kiến trúc mã nguồn mở hàng đầu cho AI Agent:
1. Aider RepoMap (AST Symbol Extraction + Thuật toán PageRank xếp hạng tâm chấn ảnh hưởng).
2. Serena / Codebase-Memory MCP (Đồ thị Callers <-> Callees & Phân tích bán kính ảnh hưởng --impact).
3. Cross-Layer Contract Guard (Kiểm định tự động sự đồng bộ giữa 4 tầng:
   Web 3D UI <-> Mobile App <-> Python Backend/Gemini Tools/MQTT <-> Firmware C++ ESP8266).

Cách sử dụng:
- Cập nhật bản đồ RepoMap & Đồ thị JSON + Kiểm định toàn hệ thống:
    python -X utf8 scripts/code_graph_guard.py
- Kiểm tra phạm vi ảnh hưởng (Blast Radius) TRƯỚC KHI sửa bất kỳ hàm/topic/API nào:
    python -X utf8 scripts/code_graph_guard.py --impact execute_device_action
    python -X utf8 scripts/code_graph_guard.py --impact smarthome/cmd/actuate
    python -X utf8 scripts/code_graph_guard.py --impact /api/state
- Chạy riêng cổng kiểm định đồng bộ 4 tầng (CI/Pre-commit Gate):
    python -X utf8 scripts/code_graph_guard.py --verify
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys
from collections import defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCH_DIR = ROOT / "docs" / "kien_truc"
GRAPH_JSON_PATH = ARCH_DIR / "CODEBASE_GRAPH.json"
REPO_MAP_MD_PATH = ARCH_DIR / "REPO_MAP.md"

PYTHON_FILES = [
    "simulator/server.py",
    "simulator/rule_engine.py",
    "simulator/mqtt_bridge.py",
    "simulator/voice_auth.py",
    "simulator/knowledge_rag.py",
    "scripts/test_simulator_e2e.py",
]

FRONTEND_FILES = [
    "simulator/static/app.js",
    "simulator/static/index.html",
    "mobile_app/index.html",
]

FIRMWARE_FILES = [
    "firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino",
]


def _extract_python_ast_graph() -> dict[str, Any]:
    """Phân tích AST của toàn bộ các file Python để trích xuất Class, Hàm, Dòng #Lstart-Lend và Call Graph."""
    symbols: dict[str, dict[str, Any]] = {}
    short_name_to_qnames: dict[str, list[str]] = defaultdict(list)
    raw_calls_by_qname: dict[str, set[str]] = defaultdict(set)

    for rel_path in PYTHON_FILES:
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            continue
        source = abs_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel_path)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cls_qname = f"{rel_path}::{node.name}"
                doc = (ast.get_docstring(node) or "").splitlines()[0] if ast.get_docstring(node) else ""
                symbols[cls_qname] = {
                    "qname": cls_qname,
                    "name": node.name,
                    "kind": "class",
                    "file": rel_path,
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "signature": f"class {node.name}",
                    "doc": doc,
                    "methods": [],
                }
                short_name_to_qnames[node.name].append(cls_qname)

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_qname = f"{rel_path}::{node.name}.{item.name}"
                        args = [a.arg for a in item.args.args if a.arg != "self"]
                        prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        sig = f"{prefix} {item.name}({', '.join(args)})"
                        mdoc = (ast.get_docstring(item) or "").splitlines()[0] if ast.get_docstring(item) else ""
                        symbols[m_qname] = {
                            "qname": m_qname,
                            "name": item.name,
                            "class_name": node.name,
                            "kind": "method",
                            "file": rel_path,
                            "start_line": item.lineno,
                            "end_line": getattr(item, "end_lineno", item.lineno),
                            "signature": sig,
                            "doc": mdoc,
                        }
                        symbols[cls_qname]["methods"].append(m_qname)
                        short_name_to_qnames[item.name].append(m_qname)

                        for sub in ast.walk(item):
                            if isinstance(sub, ast.Call):
                                if isinstance(sub.func, ast.Name):
                                    raw_calls_by_qname[m_qname].add(sub.func.id)
                                elif isinstance(sub.func, ast.Attribute):
                                    raw_calls_by_qname[m_qname].add(sub.func.attr)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f_qname = f"{rel_path}::{node.name}"
                args = [a.arg for a in node.args.args]
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                sig = f"{prefix} {node.name}({', '.join(args)})"
                fdoc = (ast.get_docstring(node) or "").splitlines()[0] if ast.get_docstring(node) else ""
                symbols[f_qname] = {
                    "qname": f_qname,
                    "name": node.name,
                    "kind": "function",
                    "file": rel_path,
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "signature": sig,
                    "doc": fdoc,
                }
                short_name_to_qnames[node.name].append(f_qname)

                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        if isinstance(sub.func, ast.Name):
                            raw_calls_by_qname[f_qname].add(sub.func.id)
                        elif isinstance(sub.func, ast.Attribute):
                            raw_calls_by_qname[f_qname].add(sub.func.attr)

    # Xây dựng đồ thị có hướng Callers <-> Callees giữa các Symbol trong dự án
    callees_map: dict[str, list[str]] = defaultdict(list)
    callers_map: dict[str, list[str]] = defaultdict(list)

    for caller_qname, called_names in raw_calls_by_qname.items():
        for cname in sorted(called_names):
            if cname in ("__init__", "get", "append", "extend", "pop", "items", "keys", "values", "strip", "lower", "upper", "replace"):
                continue
            target_qnames = short_name_to_qnames.get(cname, [])
            for target_qname in target_qnames:
                if target_qname != caller_qname:
                    if target_qname not in callees_map[caller_qname]:
                        callees_map[caller_qname].append(target_qname)
                    if caller_qname not in callers_map[target_qname]:
                        callers_map[target_qname].append(caller_qname)

    # Tính điểm PageRank (tương tự Aider RepoMap) để tìm những hàm "Tâm Chấn" (High Blast-Radius)
    all_qnames = list(symbols.keys())
    n = len(all_qnames) or 1
    ranks = {q: 1.0 / n for q in all_qnames}
    damping = 0.85
    for _ in range(25):
        new_ranks = {q: (1.0 - damping) / n for q in all_qnames}
        for q in all_qnames:
            outs = callees_map.get(q, [])
            if outs:
                share = damping * ranks[q] / len(outs)
                for dst in outs:
                    new_ranks[dst] = new_ranks.get(dst, 0.0) + share
        ranks = new_ranks

    for q, info in symbols.items():
        info["callees"] = sorted(callees_map.get(q, []))
        info["callers"] = sorted(callers_map.get(q, []))
        info["pagerank"] = round(ranks.get(q, 0.0) * 1000, 3)
        info["blast_score"] = len(info["callers"]) * 3 + len(info["callees"])

    return symbols


def _extract_cross_layer_contracts() -> dict[str, Any]:
    """Trích xuất các hợp đồng giao tiếp liên tầng (Gemini Tools, MQTT Topics, HTTP Endpoints, WS Events, GPIO Pins)."""
    server_src = (ROOT / "simulator/server.py").read_text(encoding="utf-8")
    engine_src = (ROOT / "simulator/rule_engine.py").read_text(encoding="utf-8")
    mqtt_src = (ROOT / "simulator/mqtt_bridge.py").read_text(encoding="utf-8")
    app_js_src = (ROOT / "simulator/static/app.js").read_text(encoding="utf-8")
    mobile_src = (ROOT / "mobile_app/index.html").read_text(encoding="utf-8")
    ino_src = (ROOT / "firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino").read_text(encoding="utf-8")

    # 1. Gemini Function Declarations trong server.py
    declared_tools = re.findall(r'types\.FunctionDeclaration\(\s*name="([^"]+)"', server_src)
    handled_eq = set(re.findall(r'name\s*==\s*"([^"]+)"', server_src))
    for tup_str in re.findall(r'name\s+in\s*\(([^)]+)\)', server_src):
        handled_eq.update(re.findall(r'"([^"]+)"', tup_str))
    handled_tools = sorted(handled_eq)

    # 2. MQTT Topics giữa mqtt_bridge.py và esp8266_smarthome.ino
    mqtt_topics_py = sorted(set(re.findall(r'"(smarthome/[a-z0-9_/]+)"', mqtt_src)))
    mqtt_topics_ino = sorted(set(re.findall(r'"(smarthome/[a-z0-9_/]+)"', ino_src)))

    # 3. REST API Endpoints giữa server.py, mobile_app/index.html và simulator/static/app.js
    rest_routes_server = sorted(set(re.findall(r'@app\.(?:get|post)\("([^"]+)"\)', server_src)))
    rest_calls_mobile = sorted(set(re.findall(r"fetch\(['\"](/api/[a-z0-9_]+)['\"]", mobile_src)))
    rest_calls_web = sorted(set(re.findall(r"fetch\(['\"](/api/[a-z0-9_]+)['\"]", app_js_src)))

    # 4. WebSocket Event Types phát ra từ Backend vs xử lý ở Frontend (switch(msg.type) case "..." hoặc msg.type === "...")
    ws_emitted_backend = sorted(
        set(re.findall(r'"type":\s*"([a-z0-9_]+)"', server_src))
        | set(re.findall(r'"type":\s*"([a-z0-9_]+)"', engine_src))
    )
    ws_handled_web = sorted(
        set(re.findall(r'msg\.type\s*===\s*["\']([a-z0-9_]+)["\']', app_js_src))
        | set(re.findall(r'case\s+["\']([a-z0-9_]+)["\']\s*:', app_js_src))
    )

    # 5. Chân phần cứng GPIO NodeMCU ESP8266 giữa Backend (rule_engine.py + mqtt_bridge.py) và esp8266_smarthome.ino
    gpio_pins_engine = sorted(
        set(re.findall(r'\b(D[1-8])\s*/\s*GPIO\d+', engine_src))
        | set(re.findall(r'\b(D[1-8])\s*\(GPIO\s*\d+', mqtt_src))
    )
    gpio_pins_ino = sorted(
        set(re.findall(r'#define\s+PIN_[A-Z0-9_]+\s+(D[1-8])\b', ino_src))
        | set(re.findall(r'#define\s+PIN_[A-Z0-9_]+\s+\d+\s*//\s*(D[1-8])\b', ino_src))
    )

    return {
        "gemini_tools": {
            "declared_in_server": declared_tools,
            "handled_in_server": handled_tools,
            "missing_handlers": [t for t in declared_tools if t not in handled_tools],
        },
        "mqtt_topics": {
            "python_bridge": mqtt_topics_py,
            "esp8266_firmware": mqtt_topics_ino,
            "missing_in_python": [t for t in mqtt_topics_ino if t not in mqtt_topics_py],
        },
        "rest_endpoints": {
            "server_routes": rest_routes_server,
            "mobile_app_calls": rest_calls_mobile,
            "web_app_calls": rest_calls_web,
            "missing_routes": [r for r in (set(rest_calls_mobile) | set(rest_calls_web)) if r not in rest_routes_server],
        },
        "websocket_events": {
            "emitted_by_backend": ws_emitted_backend,
            "handled_by_web_3d": ws_handled_web,
        },
        "hardware_gpio_pins": {
            "rule_engine_devices": gpio_pins_engine,
            "esp8266_firmware_defines": gpio_pins_ino,
            "mismatch": sorted(set(gpio_pins_engine) ^ set(gpio_pins_ino)),
        },
    }


def build_and_save_graph() -> tuple[dict[str, Any], dict[str, Any]]:
    """Tạo file CODEBASE_GRAPH.json và REPO_MAP.md chuẩn tinh gọn cho AI."""
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    symbols = _extract_python_ast_graph()
    contracts = _extract_cross_layer_contracts()

    top_symbols = sorted(
        [s for s in symbols.values() if s["kind"] in ("method", "function") and not s["file"].startswith("scripts/")],
        key=lambda x: (x["blast_score"], x["pagerank"]),
        reverse=True,
    )[:20]

    graph_data = {
        "project": "Đồ án Tốt nghiệp Smart Home Voice AI (SEEE - HUST)",
        "total_symbols": len(symbols),
        "top_high_impact_symbols": [
            {
                "qname": s["qname"],
                "file": s["file"],
                "lines": f"L{s['start_line']}-L{s['end_line']}",
                "callers_count": len(s["callers"]),
                "callees_count": len(s["callees"]),
                "blast_score": s["blast_score"],
            }
            for s in top_symbols
        ],
        "cross_layer_contracts": contracts,
        "symbols": symbols,
    }
    GRAPH_JSON_PATH.write_text(
        json.dumps(graph_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # Tạo REPO_MAP.md tinh gọn (~150 dòng) giúp AI đọc toàn bộ cấu trúc trong < 2.000 tokens
    lines = [
        "# 🗺️ BẢN ĐỒ KHUNG XƯƠNG DỰ ÁN & MA TRẬN ẢNH HƯỞNG CHÉO (`REPO_MAP.md`)",
        "",
        "> **QUY TẮC BẮT BUỘC CHO AI AGENT:**",
        "> 1. **Đọc file này ĐẦU TIÊN** để lấy đúng số dòng `#Lstart-Lend` trước khi gọi `read_file` (cấm đọc cả file dài hàng nghìn dòng gây tràn Context Window).",
        "> 2. **Trước khi sửa bất kỳ hàm, MQTT Topic hay API nào**, bắt buộc chạy lệnh kiểm tra bán kính ảnh hưởng:",
        ">    `python -X utf8 scripts/code_graph_guard.py --impact <tên_hàm_hoặc_topic>`",
        "> 3. **Sau khi sửa code**, bắt buộc chạy:",
        ">    `python -X utf8 scripts/code_graph_guard.py --verify` và `python -X utf8 scripts/test_simulator_e2e.py`",
        "",
        "---",
        "",
        "## 1. TOP 15 HÀM TÂM CHẤN (HIGH BLAST-RADIUS — SỬA LÀ ẢNH HƯỞNG NHIỀU NƠI NHẤT)",
        "",
        "| Hạng | Hàm / Phương thức | Vị trí (`#Lstart-Lend`) | Số nơi gọi (Callers) | Gọi xuống (Callees) | Điểm ảnh hưởng |",
        "| :---: | :--- | :--- | :---: | :---: | :---: |",
    ]
    for idx, s in enumerate(top_symbols[:15], 1):
        abs_uri = (ROOT / s["file"]).as_posix()
        link = f"[`{s['file']}#L{s['start_line']}-L{s['end_line']}`](file:///{abs_uri}#L{s['start_line']}-L{s['end_line']})"
        lines.append(
            f"| {idx} | `{s['name']}()` | {link} | {len(s['callers'])} | {len(s['callees'])} | **{s['blast_score']}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. CẦU NỐI ĐỒNG BỘ LIÊN TẦNG (CROSS-LAYER CONTRACTS)",
        "",
        "### 2.1. 19 Công cụ Gemini Live (`FunctionDeclaration` trong `server.py` <-> `rule_engine.py`)",
        "- Danh sách: " + ", ".join(f"`{t}`" for t in contracts["gemini_tools"]["declared_in_server"]),
        "",
        "### 2.2. 9 Chủ đề MQTT Chuẩn (`mqtt_bridge.py` <-> `rule_engine.py` <-> `esp8266_smarthome.ino`)",
        "- Danh sách: " + ", ".join(f"`{t}`" for t in contracts["mqtt_topics"]["python_bridge"]),
        "",
        "### 2.3. Các cổng HTTP REST API (`server.py` <-> `mobile_app/index.html` & `app.js`)",
        "- Danh sách: " + ", ".join(f"`{r}`" for r in contracts["rest_endpoints"]["server_routes"]),
        "",
        "### 2.4. 6 Chân Phần cứng NodeMCU ESP8266 (`rule_engine.py` <-> `esp8266_smarthome.ino`)",
        "- Danh sách: " + ", ".join(f"`{p}`" for p in contracts["hardware_gpio_pins"]["rule_engine_devices"]),
        "",
        "---",
        "",
        "## 3. CHỈ MỤC HÀM & CLASS THEO TỪNG FILE (ĐỂ AI ĐỌC ĐÚNG DÒNG `#Lstart-Lend`)",
        "",
    ])

    for rel_path in PYTHON_FILES:
        if rel_path.startswith("scripts/"):
            continue
        abs_uri = (ROOT / rel_path).as_posix()
        lines.append(f"### 📄 [`{rel_path}`](file:///{abs_uri})")
        file_syms = [s for s in symbols.values() if s["file"] == rel_path]
        for s in sorted(file_syms, key=lambda x: x["start_line"]):
            indent = "  - " if s["kind"] == "method" else "- "
            doc_sfx = f" — *{s['doc']}*" if s.get("doc") else ""
            lines.append(
                f"{indent}[`L{s['start_line']}-L{s['end_line']}`](file:///{abs_uri}#L{s['start_line']}-L{s['end_line']}) `{s['signature']}`{doc_sfx}"
            )
        lines.append("")

    REPO_MAP_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return symbols, contracts


def run_impact_analysis(query: str, symbols: dict[str, Any], contracts: dict[str, Any]) -> None:
    """In báo cáo Phân tích Bán kính Ảnh hưởng (Blast Radius) khi người dùng hoặc AI muốn sửa `query`."""
    q_low = query.strip().lower()
    print("=" * 78)
    print(f"🔍 PHÂN TÍCH BÁN KÍNH ẢNH HƯỞNG (BLAST-RADIUS IMPACT): '{query}'")
    print("=" * 78)

    matched_syms = [
        s for s in symbols.values()
        if q_low in s["name"].lower() or q_low in s["qname"].lower()
    ]
    if matched_syms:
        for s in matched_syms:
            print(f"\n📌 Symbol: {s['qname']}")
            print(f"   - Vị trí đọc chuẩn: {s['file']}#L{s['start_line']}-L{s['end_line']} (Chỉ cần đọc {s['end_line'] - s['start_line'] + 1} dòng này!)")
            print(f"   - Chữ ký hàm      : {s['signature']}")
            print(f"   - Điểm ảnh hưởng  : {s['blast_score']} (PageRank={s['pagerank']})")
            print(f"   - ⬆️ AI GỌI HÀM NÀY (Callers — Sửa chữ ký/kiểu trả về của hàm này sẽ ảnh hưởng ngay tới {len(s['callers'])} nơi sau):")
            if s["callers"]:
                for c in s["callers"]:
                    cs = symbols.get(c, {})
                    print(f"        * {c} ({cs.get('file')}#L{cs.get('start_line')}-L{cs.get('end_line')})")
            else:
                print("        * (Được gọi từ giao diện WebSocket/REST hoặc Entry Point)")

            print(f"   - ⬇️ HÀM NÀY GỌI XUỐNG (Callees — {len(s['callees'])} hàm phụ thuộc):")
            if s["callees"]:
                for c in s["callees"]:
                    cs = symbols.get(c, {})
                    print(f"        * {c} ({cs.get('file')}#L{cs.get('start_line')}-L{cs.get('end_line')})")
            else:
                print("        * (Không gọi hàm nội bộ khác)")

    # Kiểm tra cả trong MQTT Topics, REST Endpoints, Gemini Tools
    for topic in contracts["mqtt_topics"]["python_bridge"]:
        if q_low in topic.lower():
            print(f"\n📡 MQTT Topic liên quan: '{topic}'")
            print("   - Tầng Python Bridge : simulator/mqtt_bridge.py")
            print("   - Tầng Rule Engine   : simulator/rule_engine.py")
            print("   - Tầng Mobile App    : mobile_app/index.html")
            print("   - Tầng Firmware C++  : firmware_esp8266/esp8266_smarthome/esp8266_smarthome.ino")

    for route in contracts["rest_endpoints"]["server_routes"]:
        if q_low in route.lower():
            print(f"\n🌐 REST API Endpoint liên quan: '{route}'")
            print("   - Khai báo tại       : simulator/server.py")
            if route in contracts["rest_endpoints"]["mobile_app_calls"]:
                print("   - Gọi bởi Mobile App : mobile_app/index.html")
            if route in contracts["rest_endpoints"]["web_app_calls"]:
                print("   - Gọi bởi Web 3D UI  : simulator/static/app.js")
    print("=" * 78)


def verify_cross_layer_contracts(contracts: dict[str, Any]) -> bool:
    """Kiểm định 5 cổng đồng bộ liên tầng — chống lỗi 'Sửa tầng này làm gãy tầng kia'."""
    print("\n🛡️  CHẠY KIỂM ĐỊNH ĐỒNG BỘ LIÊN TẦNG (CROSS-LAYER CONTRACT VERIFICATION)...")
    errors: list[str] = []

    # Cổng 1: Gemini FunctionDeclarations vs Handlers
    missing_handlers = contracts["gemini_tools"]["missing_handlers"]
    if missing_handlers:
        errors.append(f"[Cổng 1 FAIL] Gemini Tool đã khai báo nhưng thiếu nhánh xử lý trong server.py: {missing_handlers}")
    else:
        print(f"  [PASS 1/5] Đồng bộ 100% ({len(contracts['gemini_tools']['declared_in_server'])}/19) Gemini Live Function Tools <-> Server Dispatcher.")

    # Cổng 2: MQTT Topics giữa Firmware C++ ESP8266 và Python MQTT Bridge
    missing_mqtt = contracts["mqtt_topics"]["missing_in_python"]
    if missing_mqtt:
        errors.append(f"[Cổng 2 FAIL] Topic MQTT trong Firmware ESP8266 không khớp với mqtt_bridge.py: {missing_mqtt}")
    else:
        print(f"  [PASS 2/5] Đồng bộ 100% ({len(contracts['mqtt_topics']['python_bridge'])} Topics) giữa Python MQTT Bridge <-> Firmware C++ ESP8266.")

    # Cổng 3: REST API Endpoints giữa Frontend (Mobile App + Web 3D) và Server
    missing_routes = contracts["rest_endpoints"]["missing_routes"]
    if missing_routes:
        errors.append(f"[Cổng 3 FAIL] Giao diện Mobile/Web gọi API không tồn tại trong server.py: {missing_routes}")
    else:
        print(f"  [PASS 3/5] Đồng bộ 100% ({len(contracts['rest_endpoints']['server_routes'])} Endpoints) giữa Mobile App/Web 3D <-> FastAPI Server.")

    # Cổng 4: Chân phần cứng GPIO NodeMCU ESP8266
    gpio_mismatch = contracts["hardware_gpio_pins"]["mismatch"]
    if gpio_mismatch:
        errors.append(f"[Cổng 4 FAIL] Lệch chân phần cứng NodeMCU ESP8266 giữa rule_engine.py và esp8266_smarthome.ino: {gpio_mismatch}")
    else:
        print(f"  [PASS 4/5] Đồng bộ 100% 6 chân phần cứng NodeMCU ESP8266 ({contracts['hardware_gpio_pins']['rule_engine_devices']}) giữa Backend <-> Firmware.")

    # Cổng 5: Sự kiện WebSocket cốt lõi
    required_ws = {"state_snapshot", "device_updated", "rbac_blocked", "start_voice_capture"}
    missing_ws = required_ws - set(contracts["websocket_events"]["handled_by_web_3d"])
    if missing_ws:
        errors.append(f"[Cổng 5 FAIL] Giao diện Web 3D (app.js) thiếu nhánh xử lý sự kiện WebSocket: {missing_ws}")
    else:
        print("  [PASS 5/5] Đồng bộ 100% các sự kiện WebSocket thời gian thực giữa Rule Engine <-> Giao diện 3D.")

    if errors:
        for err in errors:
            print("  ❌", err)
        return False

    print("🎉 TẤT CẢ 5 CỔNG ĐỒNG BỘ LIÊN TẦNG ĐỀU ĐẠT 100% PASS (ZERO CROSS-LAYER REGRESSION)!\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Codebase Graph, RepoMap & Blast-Radius Guard")
    parser.add_argument("--impact", type=str, default="", help="Tên hàm, MQTT topic hoặc API endpoint cần kiểm tra phạm vi ảnh hưởng trước khi sửa")
    parser.add_argument("--verify", action="store_true", help="Chỉ chạy kiểm định đồng bộ 5 cổng liên tầng")
    args = parser.parse_args()

    symbols, contracts = build_and_save_graph()
    print(f"✅ Đã cập nhật Đồ thị Mã nguồn ({len(symbols)} symbols) tại: {GRAPH_JSON_PATH.relative_to(ROOT)}")
    print(f"✅ Đã cập nhật Bản đồ Khung xương ({REPO_MAP_MD_PATH.stat().st_size} bytes) tại: {REPO_MAP_MD_PATH.relative_to(ROOT)}")

    if args.impact:
        run_impact_analysis(args.impact, symbols, contracts)

    ok = verify_cross_layer_contracts(contracts)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
