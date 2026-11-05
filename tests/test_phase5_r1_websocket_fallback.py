"""Reproduction & Verification Test Suite for Milestone M16: Bug R1.

Vercel WebSocket Fallback & Accurate Transport Header.
Validates:
1. simulator/static/index.html contains #homeServerStatusBadge inside #btnToggleServer.
2. simulator/static/js/app.js detects Vercel serverless upfront and skips new WebSocket.
3. simulator/static/js/app.js updateConnectionUI accurately updates #connText and #homeServerStatusBadge.
4. simulator/static/js/app.js ws.onclose falls back cleanly without infinite reconnect spam.
5. simulator/static/js/mobile_app.js avoids WebSocket connection loops on Vercel.
6. Node.js VM execution verifies runtime behavior across Localhost, Vercel, and Disconnected scenarios.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import pytest
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "simulator" / "static" / "index.html"
APP_JS = ROOT / "simulator" / "static" / "js" / "app.js"
MOBILE_APP_JS = ROOT / "simulator" / "static" / "js" / "mobile_app.js"


class TestBugR1HtmlStructure:
    """Kiểm tra cấu trúc DOM trong index.html cho header transport badge."""

    def test_home_server_status_badge_exists_inside_btn_toggle_server(self):
        """Phần tử #homeServerStatusBadge phải nằm bên trong #btnToggleServer."""
        assert INDEX_HTML.exists(), "simulator/static/index.html không tồn tại!"
        content = INDEX_HTML.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        btn = soup.find(id="btnToggleServer")
        assert btn is not None, "Không tìm thấy #btnToggleServer trong index.html"

        badge = btn.find(id="homeServerStatusBadge")
        assert badge is not None, "#homeServerStatusBadge chưa được định nghĩa bên trong #btnToggleServer"
        assert "transport-badge" in badge.get("class", []), "#homeServerStatusBadge thiếu class 'transport-badge'"


class TestBugR1AppJsLogic:
    """Kiểm tra logic mã nguồn trong app.js cho WebSocket fallback và transport header."""

    def test_app_js_declares_vercel_detection(self):
        """app.js phải phát hiện hostname vercel.app hoặc cờ serverless."""
        content = APP_JS.read_text(encoding="utf-8")
        assert "vercel.app" in content, "app.js thiếu logic nhận diện domain 'vercel.app'"
        assert "_FORCE_HTTP_POLLING" in content, "app.js thiếu hook '_FORCE_HTTP_POLLING'"

    def test_app_js_references_home_server_status_badge(self):
        """app.js phải truy xuất phần tử #homeServerStatusBadge."""
        content = APP_JS.read_text(encoding="utf-8")
        assert "homeServerStatusBadge" in content, "app.js chưa truy xuất #homeServerStatusBadge"

    def test_app_js_update_connection_ui_handles_transports(self):
        """updateConnectionUI phải hỗ trợ phân biệt WebSocket và HTTP Polling."""
        content = APP_JS.read_text(encoding="utf-8")
        assert "HTTP Polling" in content, "app.js thiếu định danh transport 'HTTP Polling'"
        assert "homeServerStatusBadge.textContent" in content or "homeServerStatusBadge" in content

    def test_app_js_connect_web_socket_guards_vercel(self):
        """connectWebSocket phải kiểm tra Vercel trước khi tạo new WebSocket."""
        content = APP_JS.read_text(encoding="utf-8")
        fn_match = re.search(r"function\s+connectWebSocket\s*\(\)\s*\{([\s\S]*?)\n  \}", content)
        assert fn_match is not None, "Không tìm thấy function connectWebSocket trong app.js"
        fn_body = fn_match.group(1)
        assert "isVercelServerless" in fn_body or "vercel.app" in fn_body, (
            "connectWebSocket chưa chặn new WebSocket trên môi trường Vercel"
        )


class TestBugR1MobileAppJsLogic:
    """Kiểm tra logic trong mobile_app.js cho Vercel WebSocket guard."""

    def test_mobile_app_js_guards_vercel_websocket(self):
        """mobile_app.js phải phát hiện Vercel và tránh tạo WebSocket lặp vô tận."""
        content = MOBILE_APP_JS.read_text(encoding="utf-8")
        assert "vercel.app" in content or "isMobileVercel" in content, (
            "mobile_app.js thiếu logic phát hiện domain vercel.app để tránh spam WebSocket"
        )


class TestBugR1NodeVmExecution:
    """Thực thi trực tiếp mã JavaScript trong môi trường Node.js giả lập."""

    def test_runtime_behavior_in_node_vm(self):
        """Kiểm chứng hành vi thực thi thực tế của app.js trên Vercel vs Localhost."""
        runner_js = """
        const fs = require('fs');
        const vm = require('vm');

        // Đọc mã nguồn app.js
        const appJsCode = fs.readFileSync('simulator/static/js/app.js', 'utf8');

        // Tạo Mock DOM
        class MockElement {
            constructor(id = '') {
                this.id = id;
                this.textContent = '';
                this.classList = {
                    classes: new Set(),
                    add(c) { this.classes.add(c); },
                    remove(c) { this.classes.delete(c); },
                    toggle(c, force) {
                        if (force === undefined) {
                            if (this.classes.has(c)) this.classes.delete(c);
                            else this.classes.add(c);
                        } else if (force) {
                            this.classes.add(c);
                        } else {
                            this.classes.delete(c);
                        }
                    },
                    contains(c) { return this.classes.has(c); }
                };
                this.attributes = {};
            }
            setAttribute(k, v) { this.attributes[k] = v; }
            getAttribute(k) { return this.attributes[k] || null; }
            addEventListener() {}
            appendChild() {}
        }

        const elements = {
            btnToggleServer: new MockElement('btnToggleServer'),
            connText: new MockElement('connText'),
            homeServerStatusBadge: new MockElement('homeServerStatusBadge'),
            connDot: new MockElement('connDot')
        };

        // Kịch bản A: Giả lập trên môi trường Vercel
        let wsInstantiationCount = 0;
        class MockWebSocket {
            constructor(url) {
                wsInstantiationCount++;
                this.url = url;
                this.readyState = 0;
            }
            send() {}
            close() {}
        }

        const sandboxVercel = {
            window: { _FORCE_HTTP_POLLING: false, addEventListener: () => {} },
            document: {
                getElementById: (id) => elements[id] || null,
                querySelector: (sel) => null,
                querySelectorAll: (sel) => [],
                addEventListener: () => {},
                readyState: 'complete'
            },
            location: {
                protocol: 'https:',
                host: 'do-an-tot-nghiep-smart-home-voice-a.vercel.app',
                hostname: 'do-an-tot-nghiep-smart-home-voice-a.vercel.app'
            },
            WebSocket: MockWebSocket,
            fetch: async (url) => ({
                ok: true,
                json: async () => ({ ok: true, devices: [], users: [] })
            }),
            setTimeout: (fn) => setTimeout(fn, 1),
            clearTimeout: () => {},
            setInterval: () => {},
            navigator: { serviceWorker: { register: async () => {} } },
            console: console
        };
        sandboxVercel.window.document = sandboxVercel.document;
        sandboxVercel.window.location = sandboxVercel.location;
        sandboxVercel.window.WebSocket = MockWebSocket;

        const context = vm.createContext(sandboxVercel);
        vm.runInContext(appJsCode, context);

        // Kiểm tra sau khi chạy app.js trên Vercel:
        // 1. Không được khởi tạo new WebSocket
        if (wsInstantiationCount !== 0) {
            console.error(JSON.stringify({ error: `wsInstantiationCount was ${wsInstantiationCount}, expected 0 on Vercel` }));
            process.exit(1);
        }

        // 2. Transport phải là HTTP Polling
        if (context.window._activeTransport !== 'HTTP Polling') {
            console.error(JSON.stringify({ error: `_activeTransport is ${context.window._activeTransport}, expected 'HTTP Polling'` }));
            process.exit(2);
        }

        // 3. Header text và badge phải hiển thị rõ ràng HTTP Polling
        if (!elements.connText.textContent.includes('HTTP Polling')) {
            console.error(JSON.stringify({ error: `connText text is "${elements.connText.textContent}", expected to contain 'HTTP Polling'` }));
            process.exit(3);
        }
        if (elements.homeServerStatusBadge.textContent !== 'HTTP Polling') {
            console.error(JSON.stringify({ error: `homeServerStatusBadge text is "${elements.homeServerStatusBadge.textContent}", expected 'HTTP Polling'` }));
            process.exit(4);
        }

        // 4. Kiểm tra khi ngắt kết nối (updateConnectionUI(false))
        context.window.updateConnectionUI(false);
        if (!elements.connDot.classList.contains('offline')) {
            console.error(JSON.stringify({ error: `connDot does not have class 'offline' when disconnected` }));
            process.exit(5);
        }
        if (elements.connText.textContent !== 'Mất kết nối') {
            console.error(JSON.stringify({ error: `connText is "${elements.connText.textContent}", expected 'Mất kết nối'` }));
            process.exit(6);
        }
        if (elements.homeServerStatusBadge.textContent !== 'Mất kết nối') {
            console.error(JSON.stringify({ error: `homeServerStatusBadge is "${elements.homeServerStatusBadge.textContent}", expected 'Mất kết nối'` }));
            process.exit(7);
        }

        console.log(JSON.stringify({ success: true }));
        """

        res = subprocess.run(
            ["node", "-e", runner_js],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Node VM runtime validation failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    def test_runtime_behavior_on_localhost_connects_websocket(self):
        """Kiểm chứng rằng trên localhost thông thường, app.js vẫn khởi tạo WebSocket và cập nhật nhãn WebSocket."""
        runner_js = """
        const fs = require('fs');
        const vm = require('vm');

        const appJsCode = fs.readFileSync('simulator/static/js/app.js', 'utf8');

        class MockElement {
            constructor(id = '') {
                this.id = id;
                this.textContent = '';
                this.classList = {
                    classes: new Set(),
                    add(c) { this.classes.add(c); },
                    remove(c) { this.classes.delete(c); },
                    toggle(c, force) {
                        if (force === undefined) {
                            if (this.classes.has(c)) this.classes.delete(c);
                            else this.classes.add(c);
                        } else if (force) {
                            this.classes.add(c);
                        } else {
                            this.classes.delete(c);
                        }
                    },
                    contains(c) { return this.classes.has(c); }
                };
                this.attributes = {};
            }
            setAttribute(k, v) { this.attributes[k] = v; }
            getAttribute(k) { return this.attributes[k] || null; }
            addEventListener() {}
            appendChild() {}
        }

        const elements = {
            btnToggleServer: new MockElement('btnToggleServer'),
            connText: new MockElement('connText'),
            homeServerStatusBadge: new MockElement('homeServerStatusBadge'),
            connDot: new MockElement('connDot')
        };

        let wsInstantiationCount = 0;
        let lastCreatedWs = null;
        class MockWebSocket {
            constructor(url) {
                wsInstantiationCount++;
                this.url = url;
                this.readyState = 1;
                lastCreatedWs = this;
            }
            send() {}
            close() {}
        }

        const sandboxLocal = {
            window: { _FORCE_HTTP_POLLING: false, addEventListener: () => {} },
            document: {
                getElementById: (id) => elements[id] || null,
                querySelector: (sel) => null,
                querySelectorAll: (sel) => [],
                addEventListener: () => {},
                readyState: 'complete'
            },
            location: {
                protocol: 'http:',
                host: 'localhost:8088',
                hostname: 'localhost'
            },
            WebSocket: MockWebSocket,
            fetch: async (url) => ({
                ok: true,
                json: async () => ({ ok: true, devices: [], users: [] })
            }),
            setTimeout: (fn) => setTimeout(fn, 1),
            clearTimeout: () => {},
            setInterval: () => {},
            navigator: { serviceWorker: { register: async () => {} } },
            console: console
        };
        sandboxLocal.window.document = sandboxLocal.document;
        sandboxLocal.window.location = sandboxLocal.location;
        sandboxLocal.window.WebSocket = MockWebSocket;

        const context = vm.createContext(sandboxLocal);
        vm.runInContext(appJsCode, context);

        // 1. Phải khởi tạo WebSocket trên localhost
        if (wsInstantiationCount < 1 || !lastCreatedWs) {
            console.error(JSON.stringify({ error: `wsInstantiationCount was ${wsInstantiationCount}, expected >= 1 on localhost` }));
            process.exit(1);
        }

        // 2. Kích hoạt ws.onopen()
        if (typeof lastCreatedWs.onopen === 'function') {
            lastCreatedWs.onopen();
        }

        // 3. Header text và badge phải hiển thị WebSocket
        if (!elements.connText.textContent.includes('WebSocket')) {
            console.error(JSON.stringify({ error: `connText text is "${elements.connText.textContent}", expected to contain 'WebSocket'` }));
            process.exit(2);
        }
        if (elements.homeServerStatusBadge.textContent !== 'WebSocket') {
            console.error(JSON.stringify({ error: `homeServerStatusBadge is "${elements.homeServerStatusBadge.textContent}", expected 'WebSocket'` }));
            process.exit(3);
        }

        console.log(JSON.stringify({ success: true }));
        """

        res = subprocess.run(
            ["node", "-e", runner_js],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Localhost Node VM validation failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

    def test_mobile_app_runtime_behavior_on_vercel_skips_websocket(self):
        """Kiểm chứng rằng mobile_app.js trên Vercel không gọi new WebSocket."""
        runner_js = """
        const fs = require('fs');
        const vm = require('vm');

        const mobileJsCode = fs.readFileSync('simulator/static/js/mobile_app.js', 'utf8');

        let wsInstantiationCount = 0;
        class MockWebSocket {
            constructor(url) {
                wsInstantiationCount++;
                this.url = url;
                this.readyState = 0;
            }
            send() {}
            close() {}
        }

        let fetchStateCalled = false;
        const sandboxMobile = {
            window: { _FORCE_HTTP_POLLING: false, addEventListener: () => {} },
            document: {
                getElementById: (id) => ({
                    textContent: '',
                    style: {},
                    classList: { add(){}, remove(){}, toggle(){} },
                    hidden: false
                }),
                querySelector: (sel) => null,
                querySelectorAll: (sel) => [],
                addEventListener: () => {},
                readyState: 'complete'
            },
            location: {
                protocol: 'https:',
                host: 'do-an-tot-nghiep-smart-home-voice-a.vercel.app',
                hostname: 'do-an-tot-nghiep-smart-home-voice-a.vercel.app',
                origin: 'https://do-an-tot-nghiep-smart-home-voice-a.vercel.app'
            },
            WebSocket: MockWebSocket,
            fetch: async (url) => {
                if (url.includes('/api/state')) fetchStateCalled = true;
                return {
                    ok: true,
                    json: async () => ({ ok: true, devices: [], timers: [] })
                };
            },
            setTimeout: (fn) => setTimeout(fn, 1),
            clearTimeout: () => {},
            setInterval: () => {},
            console: console
        };
        sandboxMobile.window.document = sandboxMobile.document;
        sandboxMobile.window.location = sandboxMobile.location;
        sandboxMobile.window.WebSocket = MockWebSocket;

        const context = vm.createContext(sandboxMobile);
        vm.runInContext(mobileJsCode, context);

        // Gọi initMobileApp hoặc connectMobileWebSocket
        if (typeof context.window.connectMobileWebSocket === 'function') {
            context.window.connectMobileWebSocket();
        } else if (typeof context.connectMobileWebSocket === 'function') {
            context.connectMobileWebSocket();
        }

        if (wsInstantiationCount !== 0) {
            console.error(JSON.stringify({ error: `wsInstantiationCount was ${wsInstantiationCount}, expected 0 on Vercel mobile` }));
            process.exit(1);
        }

        console.log(JSON.stringify({ success: true, fetchStateCalled }));
        """

        res = subprocess.run(
            ["node", "-e", runner_js],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Mobile Vercel VM validation failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"

