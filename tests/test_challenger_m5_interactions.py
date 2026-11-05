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
    """Kiểm tra mở modal #firstPageVoiceModal và kích hoạt nút #btnHoldRecordVoice trong app.js."""
    node_script = """
const fs = require('fs');
const vm = require('vm');

const jsCode = fs.readFileSync('simulator/static/js/app.js', 'utf8');

class MockElement {
  constructor(tag, id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
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
    this.attrs = {};
    this._listeners = {};
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k] || null; }
  addEventListener(event, handler) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(handler);
  }
  trigger(event, e = {}) {
    if (this._listeners[event]) {
      this._listeners[event].forEach(fn => fn(e));
    }
  }
  click() {
    this.trigger('click', { preventDefault: () => {} });
  }
}

const elements = {};
function getEl(id) {
  if (!elements[id]) elements[id] = new MockElement('div', id);
  return elements[id];
}

// Pre-create modal elements
const modal = getEl('firstPageVoiceModal');
modal.classList.add('modal', 'hidden');

const btnOpen = getEl('btnOpenFirstVoiceModal');
const btnClose = getEl('btnCloseFirstVoiceModal');
const btnCancel = getEl('btnCancelFirstVoiceModal');
const btnRecord = getEl('btnHoldRecordVoice');
const resultBox = getEl('firstVoiceResultBox');
const emailInput = getEl('firstVoiceEmailInput');
emailInput.value = 'nep94121@gmail.com';

let fetchCalls = [];
const mockWindow = {
  location: { href: 'http://localhost:8088', search: '', protocol: 'http:', host: 'localhost:8088', pathname: '/' },
  document: {
    getElementById: (id) => getEl(id),
    querySelector: (sel) => getEl(sel.replace('#', '')),
    querySelectorAll: () => [],
    createElement: (tag) => new MockElement(tag),
    addEventListener: () => {}
  },
  addEventListener: () => {},
  fetch: async (url, opts) => {
    fetchCalls.push({ url, opts });
    if (url === '/api/auth3/enroll_voice_sample') {
      return {
        ok: true,
        json: async () => ({
          ok: true,
          status: 'DA_DAT',
          message: 'Đã lưu mẫu giọng thành công!'
        })
      };
    }
    return { ok: true, json: async () => ({ ok: true, devices: {}, voice_samples: [] }) };
  },
  WebSocket: class { constructor() {} addEventListener() {} send() {} close() {} },
  setTimeout: global.setTimeout,
  clearTimeout: global.clearTimeout,
  setInterval: () => 1,
  clearInterval: () => {},
  navigator: {
    mediaDevices: {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => {} }]
      })
    }
  },
  AudioContext: class {
    constructor() { this.state = 'running'; }
    createMediaStreamSource() { return { connect() {} }; }
    createScriptProcessor() {
      return {
        connect() {},
        disconnect() {},
        set onaudioprocess(fn) {}
      };
    }
    close() {}
  },
  btoa: (str) => Buffer.from(str, 'binary').toString('base64'),
  performance: { now: () => Date.now() }
};
mockWindow.window = mockWindow;
mockWindow.globalThis = mockWindow;

const ctx = vm.createContext(mockWindow);
vm.runInContext(jsCode, ctx);

setTimeout(async () => {
  try {
    // 1. Initial state: modal has 'hidden' class
    if (!modal.classList.contains('hidden')) throw new Error('Modal should initially be hidden');

    // 2. Click btnOpenFirstVoiceModal -> modal should NOT have 'hidden'
    btnOpen.click();
    if (modal.classList.contains('hidden')) throw new Error('Modal should be open after btnOpen click');

    // 3. Click btnCloseFirstVoiceModal -> modal should have 'hidden'
    btnClose.click();
    if (!modal.classList.contains('hidden')) throw new Error('Modal should be hidden after btnClose click');

    // 4. Reopen and click btnCancelFirstVoiceModal -> modal should have 'hidden'
    btnOpen.click();
    btnCancel.click();
    if (!modal.classList.contains('hidden')) throw new Error('Modal should be hidden after btnCancel click');

    // 5. Reopen and click btnHoldRecordVoice
    btnOpen.click();
    btnRecord.click(); // Start recording

    // Click again to finish recording and submit
    await new Promise(r => setTimeout(r, 50));
    btnRecord.click(); // Stop & submit

    await new Promise(r => setTimeout(r, 100));
    const enrollCalls = fetchCalls.filter(c => c.url === '/api/auth3/enroll_voice_sample');
    if (enrollCalls.length < 1) throw new Error('POST /api/auth3/enroll_voice_sample was not called');
    
    const reqBody = JSON.parse(enrollCalls[0].opts.body);
    if (!reqBody.email) throw new Error('Missing email in enroll payload');
    if (!reqBody.audio_pcm_b64) throw new Error('Missing audio_pcm_b64 in enroll payload');
    if (!reqBody.pcm16k_b64) throw new Error('Missing pcm16k_b64 in enroll payload');
    if (!resultBox.textContent.includes('Đã lưu mẫu giọng thành công')) {
      throw new Error('Result box was not updated with success message: ' + resultBox.textContent);
    }

    process.stdout.write(JSON.stringify({ ok: true, payload_keys: Object.keys(reqBody) }));
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
    assert res.get("ok") is True, f"Modal & record button test failed: {res.get('error')}"
