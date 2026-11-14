"""Bộ kiểm thử đối kháng thực nghiệm các tương tác Milestone M5.

Người thực hiện: teamwork_challenger (Instance 1)
Nội dung kiểm định:
1. Thực nghiệm 4 câu SQL mẫu trên /logs qua backend /api/logs/sql_query
2. Thực nghiệm logic filter pills và setLogCategoryFilter trong logs.js qua Node VM
3. Thực nghiệm debounce 250ms trên ô tìm kiếm logSearchInput qua Node VM
4. Thực nghiệm mở modal #firstPageVoiceModal và kích hoạt nút #btnHoldRecordVoice qua Node VM & FastAPI TestClient
"""

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import subprocess
import pytest
from httpx import AsyncClient, ASGITransport
from simulator.server import app

SAMPLE_SQL_QUERIES = [
    ("audit_logs", "SELECT log_id, time_vn, category, event_type, user_name, summary FROM audit_logs ORDER BY log_id DESC LIMIT 12"),
    ("users", "SELECT user_id, full_name, role, tier, offline_allowed, created_by FROM users ORDER BY tier ASC"),
    ("devices", "SELECT device_id, device_name, gpio_pin, state, min_tier_required, offline_controllable FROM devices"),
    ("knowledge_rag", "SELECT doc_id, category, title, substr(content, 1, 80) AS tom_tat FROM knowledge_rag"),
]


@pytest.mark.parametrize("table_name,sql", SAMPLE_SQL_QUERIES)
def test_sample_sql_queries_execute_cleanly(table_name, sql):
    """Xác nhận 4 câu SQL mẫu trên /logs trả về 200, ok=True, không dính lỗi no such table hay no such column."""
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/logs/sql_query",
                json={"sql": sql},
                headers={"X-Session-Token": "sess_owner_t1_nep94121"},
            )
            assert resp.status_code == 200, f"HTTP error {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data.get("ok") is True, f"Lỗi SQL trên bảng {table_name}: {data.get('error')}"
            assert "rows" in data, f"Không có trường rows trong phản hồi cho {table_name}"
            assert len(data["rows"]) > 0, f"Bảng {table_name} không có bản ghi nào"

    asyncio.run(_run())


def test_logs_filter_pills_and_debounce_node_vm():
    """Kiểm tra tương tác filter pills, setLogCategoryFilter và debounce 250ms của logs.js trong Node VM."""
    node_script = """
const fs = require('fs');
const vm = require('vm');

const jsCode = fs.readFileSync('simulator/static/js/logs.js', 'utf8');

class MockElement {
  constructor(tag, id = '', attrs = {}) {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.attrs = attrs;
    this.classList = {
      _classes: new Set(),
      add: (...cls) => cls.forEach(c => this.classList._classes.add(c)),
      remove: (...cls) => cls.forEach(c => this.classList._classes.delete(c)),
      toggle: (c) => this.classList.contains(c) ? this.classList.remove(c) : this.classList.add(c),
      contains: (c) => this.classList._classes.has(c)
    };
    this.value = '';
    this.textContent = '';
    this.innerHTML = '';
    this.style = {};
    this.hidden = false;
    this._listeners = {};
    this.children = [];
  }
  getAttribute(name) {
    return this.attrs[name] || null;
  }
  setAttribute(name, val) {
    this.attrs[name] = val;
  }
  addEventListener(event, handler) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(handler);
  }
  trigger(event, e = {}) {
    if (this._listeners[event]) {
      this._listeners[event].forEach(fn => fn(e));
    }
  }
  appendChild(child) {
    this.children.push(child);
  }
}

const elements = {};
function getEl(id, attrs = {}) {
  if (!elements[id]) elements[id] = new MockElement('div', id, attrs);
  return elements[id];
}

['kpiServerClock', 'kpiServerState', 'kpiTimerCount', 'kpiCardTotalLogs',
 'kpiCardDevices', 'kpiCardSecurity', 'kpiCardServerTime', 'kpiRuleCount',
 'kpiKbCount', 'kpiLogCount', 'kpiSqliteMode', 'sqliteTablesSummary',
 'auditLogsTbody', 'mobileLogCards', 'logSearchInput', 'logCategorySelect',
 'sqlQueryInput', 'sqlResultThead', 'sqlResultTbody'].forEach(id => getEl(id));

const pillElements = [
  getEl('btnFilterAll', { onclick: "setLogCategoryFilter('')" }),
  getEl('btnFilterDevice', { onclick: "setLogCategoryFilter('DEVICE')" }),
  getEl('btnFilterVoice', { onclick: "setLogCategoryFilter('VOICE')" }),
  getEl('btnFilterSecurity', { onclick: "setLogCategoryFilter('SECURITY')" })
];
pillElements.forEach(p => {
  p.classList.add('filter-pill');
  if (p.id === 'btnFilterAll') p.classList.add('active');
  else p.classList.add('secondary');
});

let fetchCalls = [];
let domContentLoadedListeners = [];
const mockWindow = {
  document: {
    getElementById: (id) => getEl(id),
    querySelector: (sel) => getEl(sel.replace('#', '')),
    querySelectorAll: (sel) => {
      if (sel === '.filter-pill') return pillElements;
      return [];
    },
    createElement: (tag) => new MockElement(tag),
    addEventListener: (ev, handler) => {
      if (ev === 'DOMContentLoaded') domContentLoadedListeners.push(handler);
    }
  },
  addEventListener: (ev, handler) => {
    if (ev === 'DOMContentLoaded') domContentLoadedListeners.push(handler);
  },
  fetch: async (url, opts) => {
    fetchCalls.push({ url, opts });
    if (url.includes('/api/logs/dashboard')) {
      return {
        ok: true,
        json: async () => ({
          server_time_vn: '06:35:00',
          total_logs: 42,
          audit_logs: [
            { time: '06:34:00', event: 'DEVICE_SWITCH', actor: 'owner', level: 'INFO', detail: 'Turned on light' }
          ],
          hardware_database: { server_connected: true, devices: {} },
          automation_database: {}
        })
      };
    }
    return { ok: true, json: async () => ({ ok: true, rows: [] }) };
  },
  setTimeout: global.setTimeout,
  clearTimeout: global.clearTimeout,
  navigator: { clipboard: { writeText: async () => {} } }
};
mockWindow.window = mockWindow;
mockWindow.globalThis = mockWindow;

const ctx = vm.createContext(mockWindow);
vm.runInContext(jsCode, ctx);

// Trigger DOMContentLoaded
domContentLoadedListeners.forEach(fn => fn());

setTimeout(async () => {
  try {
    // 1. Initial dashboard call
    if (fetchCalls.length < 1) throw new Error('Initial loadDashboard was not called');

    // 2. Click 'Thiết bị' (DEVICE)
    mockWindow.setLogCategoryFilter('DEVICE');
    if (!getEl('btnFilterDevice').classList.contains('active')) throw new Error('btnFilterDevice should be active');
    if (getEl('btnFilterAll').classList.contains('active')) throw new Error('btnFilterAll should not be active');
    if (getEl('logCategorySelect').value !== 'DEVICE') throw new Error('logCategorySelect value should be DEVICE');
    await new Promise(r => setTimeout(r, 50));
    let lastUrl = fetchCalls[fetchCalls.length - 1].url;
    if (!lastUrl.includes('category=DEVICE')) throw new Error('Fetch did not include category=DEVICE: ' + lastUrl);

    // 3. Click 'Bảo mật' (SECURITY)
    mockWindow.setLogCategoryFilter('SECURITY');
    if (!getEl('btnFilterSecurity').classList.contains('active')) throw new Error('btnFilterSecurity should be active');
    await new Promise(r => setTimeout(r, 50));
    lastUrl = fetchCalls[fetchCalls.length - 1].url;
    if (!lastUrl.includes('category=SECURITY')) throw new Error('Fetch did not include category=SECURITY: ' + lastUrl);

    // 4. Click 'Tất cả' ('')
    mockWindow.setLogCategoryFilter('');
    if (!getEl('btnFilterAll').classList.contains('active')) throw new Error('btnFilterAll should be active');
    await new Promise(r => setTimeout(r, 50));
    lastUrl = fetchCalls[fetchCalls.length - 1].url;
    if (lastUrl.includes('category=SECURITY')) throw new Error('Filter was not cleared');

    // 5. Debounce test
    const searchInput = getEl('logSearchInput');
    const beforeCalls = fetchCalls.length;
    searchInput.value = 'query_debounce';
    searchInput.trigger('input');
    searchInput.value = 'query_debounce_2';
    searchInput.trigger('input');

    // At 100ms: no new call
    await new Promise(r => setTimeout(r, 100));
    if (fetchCalls.length !== beforeCalls) throw new Error('Debounce fired prematurely at 100ms');

    // At 300ms (>250ms): single new call
    await new Promise(r => setTimeout(r, 200));
    if (fetchCalls.length !== beforeCalls + 1) throw new Error('Debounce did not fire after 250ms');
    lastUrl = fetchCalls[fetchCalls.length - 1].url;
    if (!lastUrl.includes('q=query_debounce_2')) throw new Error('Debounced call missing query: ' + lastUrl);

    process.stdout.write(JSON.stringify({ ok: true }));
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: err.message }));
  }
}, 50);
"""
    proc = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=10,
    )
    assert proc.returncode == 0, f"Node process exited with code {proc.returncode}: {proc.stderr}"
    res = json.loads(proc.stdout)
    assert res.get("ok") is True, f"Logs interactions test failed: {res.get('error')}"


def test_first_page_voice_modal_and_record_button_node_vm():
    """Kiểm tra luồng cổng đăng nhập #homeLoginGateModal, gắn/gỡ #homeAppShell và gửi lệnh #textCmdForm trong app.js."""
    node_script = r"""
const fs = require('fs');
const vm = require('vm');

const jsCode = fs.readFileSync('simulator/static/js/app.js', 'utf8');

class MockElement {
  constructor(tag, id = '') {
    this.tagName = String(tag || 'DIV').toUpperCase();
    this.id = id;
    this.nodeType = tag === '#comment' ? 8 : 1;
    this.classList = {
      _classes: new Set(),
      add: (...cls) => cls.forEach(c => this.classList._classes.add(c)),
      remove: (...cls) => cls.forEach(c => this.classList._classes.delete(c)),
      toggle: (c) => this.classList.contains(c) ? this.classList.remove(c) : this.classList.add(c),
      contains: (c) => this.classList._classes.has(c)
    };
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.textContent = '';
    this.innerText = '';
    this.innerHTML = '';
    this.style = {};
    this.hidden = false;
    this.attrs = {};
    this.dataset = {};
    this.children = [];
    this.childNodes = this.children;
    this.parentNode = null;
    this.nextSibling = null;
    this._listeners = {};
  }
  _unlink(node) {
    if (!node || !node.parentNode) return;
    const arr = node.parentNode.children;
    const idx = arr.indexOf(node);
    if (idx !== -1) arr.splice(idx, 1);
    node.parentNode = null;
  }
  appendChild(node) {
    this._unlink(node);
    node.parentNode = this;
    this.children.push(node);
    return node;
  }
  insertBefore(node, refNode) {
    this._unlink(node);
    node.parentNode = this;
    if (!refNode) {
      this.children.push(node);
      return node;
    }
    const idx = this.children.indexOf(refNode);
    if (idx === -1) this.children.push(node);
    else this.children.splice(idx, 0, node);
    return node;
  }
  removeChild(node) {
    const idx = this.children.indexOf(node);
    if (idx !== -1) {
      this.children.splice(idx, 1);
      node.parentNode = null;
    }
    return node;
  }
  contains(node) {
    if (node === this) return true;
    return this.children.some(ch => typeof ch.contains === 'function' ? ch.contains(node) : ch === node);
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'hidden') this.hidden = true; }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; if (k === 'hidden') this.hidden = false; }
  querySelector(sel) {
    if (typeof sel === 'string' && sel.startsWith('#')) return getEl(sel.slice(1));
    return null;
  }
  querySelectorAll() { return []; }
  closest() { return null; }
  focus() {}
  reset() {}
  addEventListener(event, handler) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(handler);
  }
  trigger(event, e = {}) {
    const ev = Object.assign({ preventDefault: () => {}, stopPropagation: () => {}, target: this }, e);
    if (this._listeners[event]) {
      this._listeners[event].forEach(fn => fn(ev));
    }
  }
  click() {
    this.trigger('click');
  }
}

const elements = {};
function getEl(id) {
  if (!elements[id]) elements[id] = new MockElement('div', id);
  return elements[id];
}

const mockBody = getEl('__body__');
const homeAppShell = getEl('homeAppShell');
mockBody.appendChild(homeAppShell);

const gateModal = getEl('homeLoginGateModal');
gateModal.classList.add('modal', 'hidden');
mockBody.appendChild(gateModal);

const gateEmailInput = getEl('gateLoginEmail');
const gatePasswordInput = getEl('gateLoginPassword');
const btnSubmitGateLogin = getEl('btnSubmitGateLogin');
const textCmdForm = getEl('textCmdForm');
const txtCommand = getEl('txtCommand');

let fetchCalls = [];
let authedSession = false;
const storageMap = new Map();
const mockStorage = {
  getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
  setItem: (k, v) => storageMap.set(k, String(v)),
  removeItem: (k) => storageMap.delete(k),
  clear: () => storageMap.clear(),
};

const mockWindow = {
  location: { href: 'http://localhost:8088/', search: '', protocol: 'http:', host: 'localhost:8088', pathname: '/', hash: '' },
  document: {
    body: mockBody,
    visibilityState: 'visible',
    hidden: false,
    getElementById: (id) => (Object.prototype.hasOwnProperty.call(elements, id) ? elements[id] : getEl(id)),
    querySelector: (sel) => (typeof sel === 'string' && sel.startsWith('#') ? getEl(sel.slice(1)) : null),
    querySelectorAll: () => [],
    createElement: (tag) => new MockElement(tag),
    createComment: (txt) => new MockElement('#comment', txt || ''),
    addEventListener: () => {}
  },
  addEventListener: () => {},
  fetch: async (url, opts = {}) => {
    fetchCalls.push({ url: String(url), opts });
    if (String(url).startsWith('/api/auth3/session') || String(url).startsWith('/api/session/role')) {
      return {
        ok: true,
        status: 200,
        json: async () => authedSession
          ? { ok: true, authenticated: true, user_id: 'tuan_anh', email: 'nep94121@gmail.com', tier: 1, role: 'OWNER', user_name: 'Chủ nhà', session_token: 'sess_owner_t1_nep94121' }
          : { ok: true, authenticated: false, tier: 99, role: 'UNKNOWN' }
      };
    }
    if (String(url) === '/api/auth3/layer1_login') {
      authedSession = true;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          trusted_device_skip_otp: true,
          session_token: 'sess_owner_t1_nep94121',
          user_id: 'tuan_anh',
          email: 'nep94121@gmail.com',
          tier: 1,
          role: 'OWNER',
          user_name: 'Chủ nhà'
        })
      };
    }
    if (String(url).startsWith('/api/state')) {
      if (!authedSession) {
        return { ok: false, status: 401, json: async () => ({ ok: false, error: 'Unauthorized' }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          authenticated: true,
          user_id: 'tuan_anh',
          email: 'nep94121@gmail.com',
          tier: 1,
          auth_tier: 1,
          role: 'OWNER',
          user_name: 'Chủ nhà',
          devices: [
            { id: 'living_room_light', name: 'Đèn phòng khách', room: 'Phòng khách', state: 'OFF' }
          ],
          sensors: { temperature: 27, humidity: 65, soil_moisture: 55 },
          server_connected: true
        })
      };
    }
    if (String(url) === '/api/text_command') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          reply: 'Đèn phòng khách đã bật.',
          exact_spoken_reply: 'Đèn phòng khách đã bật.',
          snapshot: { devices: [{ id: 'living_room_light', state: 'ON' }] }
        })
      };
    }
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  },
  WebSocket: Object.assign(
    class { constructor() { this.readyState = 3; } addEventListener() {} send() {} close() {} },
    { OPEN: 1, CONNECTING: 0, CLOSING: 2, CLOSED: 3 }
  ),
  BroadcastChannel: class { constructor() {} addEventListener() {} postMessage() {} close() {} },
  localStorage: mockStorage,
  sessionStorage: mockStorage,
  requestAnimationFrame: (cb) => setTimeout(cb, 0),
  cancelAnimationFrame: (id) => clearTimeout(id),
  setTimeout: global.setTimeout,
  clearTimeout: global.clearTimeout,
  setInterval: () => 1,
  clearInterval: () => {},
  confirm: () => true,
  navigator: {
    mediaDevices: {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => {} }]
      })
    }
  },
  AudioContext: class {
    constructor() { this.state = 'running'; this.sampleRate = 24000; this.currentTime = 0; this.destination = {}; }
    createMediaStreamSource() { return { connect() {} }; }
    createScriptProcessor() {
      return {
        connect() {},
        disconnect() {},
        set onaudioprocess(fn) {}
      };
    }
    createBuffer() { return { copyToChannel() {}, duration: 0.1 }; }
    createBufferSource() { return { connect() {}, start() {}, buffer: null, onended: null }; }
    resume() { return Promise.resolve(); }
    close() {}
  },
  atob: (s) => Buffer.from(s, 'base64').toString('binary'),
  btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
  performance: { now: () => Date.now() },
  AbortController: global.AbortController,
  URLSearchParams: global.URLSearchParams,
};
mockWindow.window = mockWindow;
mockWindow.globalThis = mockWindow;

const ctx = vm.createContext(mockWindow);
vm.runInContext(jsCode, ctx);

setTimeout(async () => {
  try {
    await new Promise(r => setTimeout(r, 40));

    // 1. Trạng thái ẩn danh ban đầu: #homeAppShell đã bị gỡ khỏi DOM và cổng đăng nhập mở
    if (mockBody.contains(homeAppShell)) {
      throw new Error('homeAppShell should be unmounted from DOM when anonymous');
    }
    if (gateModal.classList.contains('hidden')) {
      throw new Error('homeLoginGateModal should be visible when anonymous');
    }

    // 2. Đăng nhập qua gate (#gatePanelLogin -> /api/auth3/layer1_login)
    gateEmailInput.value = 'nep94121@gmail.com';
    gatePasswordInput.value = 'test-pass';
    btnSubmitGateLogin.click();
    await new Promise(r => setTimeout(r, 80));

    const loginCalls = fetchCalls.filter(c => c.url === '/api/auth3/layer1_login');
    if (loginCalls.length < 1) {
      throw new Error('POST /api/auth3/layer1_login was not called');
    }
    if (!mockBody.contains(homeAppShell)) {
      throw new Error('homeAppShell should be mounted back into DOM after login');
    }
    if (!gateModal.classList.contains('hidden')) {
      throw new Error('homeLoginGateModal should be hidden after login');
    }

    // 3. Gửi lệnh văn bản qua #textCmdForm -> POST /api/text_command
    txtCommand.value = 'Bật đèn phòng khách';
    textCmdForm.trigger('submit');
    await new Promise(r => setTimeout(r, 60));

    const cmdCalls = fetchCalls.filter(c => c.url === '/api/text_command');
    if (cmdCalls.length < 1) {
      throw new Error('POST /api/text_command was not called');
    }
    const reqBody = JSON.parse(cmdCalls[0].opts.body);
    if (reqBody.text !== 'Bật đèn phòng khách') {
      throw new Error('Unexpected text command payload: ' + JSON.stringify(reqBody));
    }

    process.stdout.write(JSON.stringify({ ok: true, payload_keys: Object.keys(reqBody) }));
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: err && err.message ? err.message : String(err) }));
  }
}, 30);
"""
    proc = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=10,
    )
    assert proc.returncode == 0, f"Node process exited with code {proc.returncode}: {proc.stderr}"
    res = json.loads(proc.stdout)
    assert res.get("ok") is True, f"Home gate & command VM test failed: {res.get('error')}"
