    (function installLogsAuthFetchInterceptor() {
      if (typeof window === 'undefined' || typeof window.fetch !== 'function' || window._shLogsAuthFetchWrapped) {
        return;
      }
      const originalFetch = window.fetch.bind(window);
      function resolveActiveSessionToken() {
        try {
          const ss = window.sessionStorage && window.sessionStorage.getItem('session_token');
          if (ss) return ss;
        } catch (_e) {}
        try {
          const ls = window.localStorage && window.localStorage.getItem('session_token');
          if (ls) return ls;
          const rawAuth = window.localStorage && window.localStorage.getItem('smarthome_auth_session');
          if (rawAuth) {
            const parsed = JSON.parse(rawAuth);
            if (parsed && typeof parsed === 'object') {
              const tok = parsed.session_token || parsed.session_id || (parsed.session && parsed.session.session_id);
              if (tok) return String(tok);
            }
          }
        } catch (_e2) {}
        return '';
      }
      const wrappedFetch = function (input, init) {
        const urlStr = typeof input === 'string' ? input : (input && input.url ? input.url : '');
        if (urlStr.startsWith('/api/') || urlStr.includes('/api/')) {
          const nextInit = Object.assign({ credentials: 'same-origin' }, init || {});
          const headersObj = Object.assign({}, nextInit.headers || {});
          const token = resolveActiveSessionToken();
          if (token && !headersObj['X-Session-Token'] && !headersObj['x-session-token']) {
            headersObj['X-Session-Token'] = token;
          }
          nextInit.headers = headersObj;
          return originalFetch(input, nextInit);
        }
        return originalFetch(input, init);
      };
      window.fetch = wrappedFetch;
      window._shLogsAuthFetchWrapped = true;
    })();

    let activeCategory = '';
    let lastLoadedLogs = [];
    let isLogsAdminAuthorized = false;

    function showLogsActionStatus(msg, isError = true) {
      const box = document.getElementById('logsActionStatus');
      if (!box) return;
      const safeText = maskSensitiveLogText(msg || '');
      if (!safeText) {
        box.textContent = '';
        box.hidden = true;
        if (box.style) box.style.display = 'none';
        return;
      }
      box.textContent = safeText;
      box.hidden = false;
      box.className = isError ? 'logs-status-banner' : 'logs-status-banner is-info';
      if (box.style) box.style.display = 'block';
    }

    function setLogsAdminUiState(isAdmin) {
      isLogsAdminAuthorized = Boolean(isAdmin);
      const adminMenu = document.getElementById('logsAdminMenu');
      const adminSummary = document.getElementById('logsAdminSummary');
      const adminPanel = document.getElementById('logsAdminPanel');
      const adminHint = document.getElementById('logsAdminHint');

      if (!isLogsAdminAuthorized) {
        if (adminMenu) {
          adminMenu.open = false;
          adminMenu.className = 'menu is-disabled';
          if (typeof adminMenu.removeAttribute === 'function') adminMenu.removeAttribute('open');
        }
        if (adminPanel) {
          adminPanel.hidden = true;
          if (adminPanel.style) adminPanel.style.display = 'none';
        }
        if (adminHint) {
          adminHint.hidden = false;
          adminHint.textContent = 'Chỉ Chủ nhà (Cấp 1)';
          if (adminHint.style) adminHint.style.display = 'inline-flex';
        }
        if (adminSummary && typeof adminSummary.setAttribute === 'function') {
          adminSummary.setAttribute('aria-disabled', 'true');
        }
      } else {
        if (adminMenu) adminMenu.className = 'menu';
        if (adminPanel) {
          adminPanel.hidden = false;
          if (adminPanel.style) adminPanel.style.display = '';
        }
        if (adminHint) {
          adminHint.hidden = true;
          if (adminHint.style) adminHint.style.display = 'none';
        }
        if (adminSummary && typeof adminSummary.setAttribute === 'function') {
          adminSummary.setAttribute('aria-disabled', 'false');
        }
      }
    }

    async function readSafeJson(res) {
      if (!res || typeof res.json !== 'function') return {};
      try {
        return await res.json();
      } catch (_e) {
        return {};
      }
    }

    function resolveLogsHttpError(res, data, fallbackMsg) {
      const serverErr = data && typeof data.error === 'string' ? data.error.trim() : '';
      if (res && (res.status === 401 || res.status === 403)) {
        return serverErr || fallbackMsg;
      }
      return serverErr || `${fallbackMsg} (HTTP ${res ? res.status : 'ERR'})`;
    }

    function copyTextValue(val) {
      if (!val) return;
      navigator.clipboard.writeText(val).catch(() => {});
    }

    function deriveResultStatus(item) {
      const text = `${item.event || ''} ${item.detail || ''} ${item.level || ''}`.toUpperCase();
      if (text.includes('BLOCK') || text.includes('DENIED') || text.includes('FAIL') || text.includes('ERR') || text.includes('TỪ CHỐI')) {
        return { label: 'Thất bại', cls: 'danger' };
      }
      if (text.includes('WARN') || text.includes('RETRY') || text.includes('THỬ LẠI')) {
        return { label: 'Cần kiểm tra', cls: 'warn' };
      }
      return { label: 'Thành công', cls: '' };
    }

    let currentPage = 1;
    const pageSize = 20;

    function maskSensitiveLogText(text) {
      if (!text) return '';
      return String(text)
        .replace(/\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/g, (_m, local, domain) => `${String(local).charAt(0)}***@${domain}`)
        .replace(/(Mã\s*OTP(?:\s*[^:\d\n]{0,30})?[:=]\s*)(\d{4,8})/gi, '$1******')
        .replace(/(\bOTP\s*[:=]\s*)(\d{4,8})/gi, '$1******')
        .replace(/(Bảng\s*Test\s*\()(\d{4,8})(\))/gi, '$1******$3')
        .replace(/(Mật khẩu gợi ý:\s*)([^\s\)]+)/gi, '$1******')
        .replace(/(Gợi ý mật khẩu:\s*)([^\s\)]+)/gi, '$1******')
        .replace(/(Mật khẩu:\s*)([^\s\)]+)/gi, '$1******')
        .replace(/((?:password|password_plain_hint|password_hint|hint|secret|token|otp|otp_code|mat_khau|mk)["']?\s*[:=]\s*["'])([^"']+)(["'])/gi, '$1******$3')
        .replace(/(\b(?:password|password_plain_hint|password_hint|hint|secret|token|otp|otp_code|mat_khau|mk)\b["']?\s*[:=]\s*)(?!["'])([^\s,;}\]\)"']+)/gi, '$1******');
    }

    function toggleLogDetailRow(idx) {
      const row = document.getElementById(`log-detail-${idx}`);
      if (row) row.classList.toggle('open');
    }

    function getFilteredLogs() {
      const dateRange = document.getElementById('logDateRange')?.value || 'all';
      if (dateRange === 'all') return lastLoadedLogs;
      const now = new Date();
      return lastLoadedLogs.filter(item => {
        if (!item.time) return true;
        const timeStr = String(item.time).replace(' ', 'T');
        const d = new Date(timeStr);
        if (isNaN(d.getTime())) return true;
        if (dateRange === 'today') {
          return d.toDateString() === now.toDateString();
        } else if (dateRange === '7d') {
          const diffMs = now.getTime() - d.getTime();
          return diffMs <= 7 * 24 * 3600 * 1000 && diffMs >= 0;
        }
        return true;
      });
    }

    function renderLogsPage() {
      const logTbody = document.getElementById('auditLogsTbody');
      const mobileCards = document.getElementById('mobileLogCards');
      if (!logTbody || !mobileCards) return;

      logTbody.innerHTML = '';
      mobileCards.innerHTML = '';

      const filtered = getFilteredLogs();
      const total = filtered.length;
      const visibleCount = Math.min(currentPage * pageSize, total);
      const visibleLogs = filtered.slice(0, visibleCount);

      const infoEl = document.getElementById('logsPaginationInfo');
      if (infoEl) {
        infoEl.textContent = `Hiển thị ${visibleLogs.length} / ${total} sự kiện`;
      }

      const btnMore = document.getElementById('btnLogsLoadMore');
      if (btnMore) {
        if (visibleLogs.length >= total) {
          btnMore.disabled = true;
          btnMore.textContent = 'Đã hiển thị tất cả';
          btnMore.style.opacity = '0.5';
        } else {
          btnMore.disabled = false;
          btnMore.textContent = `Xem thêm sự kiện (${total - visibleLogs.length} còn lại)`;
          btnMore.style.opacity = '1';
        }
      }

      if (visibleLogs.length === 0) {
        logTbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);">Chưa có sự kiện</td></tr>';
        mobileCards.innerHTML = '<div style="color:var(--muted);">Chưa có sự kiện</div>';
      } else {
        visibleLogs.forEach((item, idx) => {
          const status = deriveResultStatus(item);
          const evText = maskSensitiveLogText(item.event || 'Sự kiện');
          const actorText = maskSensitiveLogText(item.actor || 'Hệ thống');
          const detText = maskSensitiveLogText(item.detail || 'Không có mô tả bổ sung.');
          const tr = document.createElement('tr');
          tr.className = 'log-row';
          tr.onclick = () => toggleLogDetailRow(idx);
          tr.innerHTML = `
            <td>${item.time || '—'}</td>
            <td style="font-weight:500;">${evText}</td>
            <td>${actorText}</td>
            <td><span class="result-text ${status.cls}">${status.label}</span></td>
          `;
          const detailTr = document.createElement('tr');
          detailTr.className = 'log-detail-row';
          detailTr.id = `log-detail-${idx}`;
          detailTr.innerHTML = `
            <td colspan="4">
              <div>${detText}</div>
            </td>
          `;
          logTbody.appendChild(tr);
          logTbody.appendChild(detailTr);

          const mCard = document.createElement('div');
          mCard.className = 'mobile-log-card';
          mCard.innerHTML = `
            <div class="mobile-log-line1">
              <span>${evText}</span>
              <span class="result-text ${status.cls}">${status.label}</span>
            </div>
            <div class="mobile-log-line2">
              <span>${actorText}</span>
              <span>${item.time || '—'}</span>
            </div>
          `;
          mobileCards.appendChild(mCard);
        });
      }
    }

    function loadMoreLogs() {
      currentPage = 999999;
      renderLogsPage();
    }

    async function loadDashboard() {
      const qEl = document.getElementById('logSearchInput');
      const q = qEl && qEl.value ? qEl.value.trim() : '';
      const url = `/api/logs/dashboard?category=${encodeURIComponent(activeCategory)}&q=${encodeURIComponent(q)}`;
      const res = await fetch(url);
      const data = await readSafeJson(res);
      if (!res.ok || (data && data.ok === false)) {
        setLogsAdminUiState(false);
        lastLoadedLogs = [];
        const errMsg = maskSensitiveLogText((data && data.error) || `Yêu cầu đăng nhập quyền Chủ nhà (HTTP ${res.status})`);
        const logTbody = document.getElementById('auditLogsTbody');
        const mobileCards = document.getElementById('mobileLogCards');
        if (logTbody) {
          logTbody.innerHTML = `<tr><td colspan="4" style="color:var(--danger);">${errMsg}</td></tr>`;
        }
        if (mobileCards) {
          mobileCards.innerHTML = `<div style="color:var(--danger);">${errMsg}</div>`;
        }
        return false;
      }
      setLogsAdminUiState(true);

      document.getElementById('kpiServerClock').textContent = `${data.server_time_vn || '--:--:--'}`;
      document.getElementById('kpiServerState').textContent = data.hardware_database?.server_connected ? 'Đã kết nối' : 'Mất kết nối';
      document.getElementById('kpiTimerCount').textContent = data.automation_database?.active_timers_count ?? 0;

      const kpiTotalLogs = document.getElementById('kpiCardTotalLogs');
      if (kpiTotalLogs) kpiTotalLogs.textContent = data.total_logs ?? 0;

      const kpiDevices = document.getElementById('kpiCardDevices');
      if (kpiDevices) {
        const devs = data.hardware_database?.devices || {};
        const devList = Object.values(devs);
        const totalDevs = devList.length || 7;
        const activeDevs = devList.filter(d => d.state === 'ON' || d.state === 'OPEN').length;
        kpiDevices.textContent = `${activeDevs}/${totalDevs} Bật`;
      }

      const kpiSecurity = document.getElementById('kpiCardSecurity');
      if (kpiSecurity) {
        kpiSecurity.textContent = data.hardware_database?.server_connected ? 'An toàn' : 'Ngoại tuyến';
      }

      const kpiServerTime = document.getElementById('kpiCardServerTime');
      if (kpiServerTime) {
        kpiServerTime.textContent = data.server_time_vn || '--:--:--';
      }

      const rCounts = (data.automation_database?.word_mappings_count || 0)
        + (data.automation_database?.custom_aliases_count || 0)
        + (data.automation_database?.if_else_rules_count || 0)
        + (data.automation_database?.system_directives_count || 0);
      document.getElementById('kpiRuleCount').textContent = rCounts;
      document.getElementById('kpiKbCount').textContent = `${(data.knowledge_base || []).length} mục`;
      document.getElementById('kpiLogCount').textContent = data.total_logs ?? 0;

      if (data.sqlite_Wal) {
        const sq = data.sqlite_Wal;
        document.getElementById('kpiSqliteMode').textContent = `${(sq.journal_mode || 'wal').toUpperCase()} (${sq.size_kb || 0} KB)`;
        const sumDiv = document.getElementById('sqliteTablesSummary');
        sumDiv.innerHTML = '';
        Object.entries(sq.tables || {}).forEach(([tbl, cnt]) => {
          const span = document.createElement('code');
          span.textContent = `${tbl}: ${cnt}`;
          sumDiv.appendChild(span);
        });
      }

      lastLoadedLogs = data.audit_logs || [];
      currentPage = 1;
      renderLogsPage();

      const poolsDiv = document.getElementById('poolsContainer');
      poolsDiv.innerHTML = '';
      (data.connection_pools || []).forEach(p => {
        const div = document.createElement('div');
        div.className = 'tech-kv';
        div.innerHTML = `<span>${p.pool_name}</span><code>${p.status} · ${p.latency_ms} ms</code>`;
        poolsDiv.appendChild(div);
      });

      document.getElementById('hardwareDbPre').textContent = JSON.stringify({
        hardware_database: data.hardware_database,
        automation_database: data.automation_database
      }, null, 2);

      const kbTbody = document.getElementById('kbTbody');
      kbTbody.innerHTML = '';
      const tierLabelMap = { 1: 'Chủ nhà', 2: 'Gia đình', 3: 'Khách' };
      (data.knowledge_base || []).forEach(k => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><code>${k.id}</code></td>
          <td>${k.topic}</td>
          <td>${tierLabelMap[k.min_tier] || 'Khách'}</td>
          <td>${k.content}</td>
        `;
        kbTbody.appendChild(tr);
      });

      const filesTbody = document.getElementById('storageFilesTbody');
      filesTbody.innerHTML = '';
      (data.storage_files || []).forEach(f => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><code>${f.name}</code></td>
          <td>${f.purpose}</td>
          <td>${f.size_kb} KB</td>
          <td><code>${f.modified_vn}</code></td>
        `;
        filesTbody.appendChild(tr);
      });
      return true;
    }

    async function addKnowledgeEntry() {
      const topic = document.getElementById('kbTopic').value.trim();
      const keywords = document.getElementById('kbKeywords').value.trim();
      const content = document.getElementById('kbContent').value.trim();
      const min_tier = parseInt(document.getElementById('kbTier').value, 10);
      if (!topic || !content) {
        showLogsActionStatus('Vui lòng nhập đầy đủ chủ đề và nội dung hướng dẫn.', true);
        return false;
      }

      const res = await fetch('/api/logs/knowledge/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, keywords, content, min_tier })
      });
      const data = await readSafeJson(res);
      if (!res.ok || (data && data.ok === false)) {
        if (res.status === 401 || res.status === 403) {
          showLogsActionStatus('Bạn cần đăng nhập quyền Chủ nhà để cập nhật cấu hình trợ lý', true);
        } else {
          showLogsActionStatus(resolveLogsHttpError(res, data, 'Không lưu được cấu hình trợ lý'), true);
        }
        return false;
      }
      document.getElementById('kbTopic').value = '';
      document.getElementById('kbKeywords').value = '';
      document.getElementById('kbContent').value = '';
      showLogsActionStatus('Đã lưu mục cấu hình trợ lý.', false);
      await loadDashboard();
      return true;
    }

    async function seedDemoLog() {
      const res = await fetch('/api/logs/append', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: 'HARDWARE_QUERY',
          event: 'Bật đèn phòng khách',
          actor: 'Chủ nhà',
          detail: 'Thành công',
          level: 'INFO'
        })
      });
      const data = await readSafeJson(res);
      if (!res.ok || (data && data.ok === false)) {
        if (res.status === 401 || res.status === 403) {
          showLogsActionStatus('Bạn cần đăng nhập quyền Chủ nhà để ghi nhật ký', true);
        } else {
          showLogsActionStatus(resolveLogsHttpError(res, data, 'Không ghi được nhật ký mẫu'), true);
        }
        return false;
      }
      showLogsActionStatus('Đã ghi sự kiện mẫu vào nhật ký.', false);
      await loadDashboard();
      return true;
    }

    async function clearCustomLogs() {
      const res = await fetch('/api/logs/clear', { method: 'POST' });
      const data = await readSafeJson(res);
      if (!res.ok || (data && data.ok === false)) {
        if (res.status === 401 || res.status === 403) {
          showLogsActionStatus('Bạn cần đăng nhập quyền Chủ nhà để xóa nhật ký', true);
        } else {
          showLogsActionStatus(resolveLogsHttpError(res, data, 'Không xóa được nhật ký'), true);
        }
        return false;
      }
      showLogsActionStatus('Đã xóa nhật ký tùy chỉnh.', false);
      await loadDashboard();
      return true;
    }

    function confirmClearLogs() {
      if (!isLogsAdminAuthorized) {
        showLogsActionStatus('Bạn cần đăng nhập quyền Chủ nhà để xóa nhật ký', true);
        return;
      }
      if (window.confirm('Bạn có chắc muốn xóa nhật ký?')) {
        clearCustomLogs();
      }
    }

    function exportLogsCsv() {
      if (!isLogsAdminAuthorized) {
        showLogsActionStatus('Cần đăng nhập để xuất nhật ký', true);
        return false;
      }
      const rows = [['Thời gian', 'Danh mục', 'Sự kiện', 'Thiết bị / người dùng', 'Kết quả', 'Chi tiết']];
      (lastLoadedLogs || []).forEach(item => {
        const st = deriveResultStatus(item);
        rows.push([
          item.time || '',
          item.category || item.cat || '',
          maskSensitiveLogText(item.event || ''),
          maskSensitiveLogText(item.actor || ''),
          st.label,
          maskSensitiveLogText(item.detail || '')
        ]);
      });
      const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'nhat_ky_nha_thong_minh.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
    }

    function setLogCategoryFilter(cat) {
      activeCategory = cat || '';
      const sel = document.getElementById('logCategorySelect');
      if (sel) sel.value = activeCategory;
      const pills = document.querySelectorAll('.filter-pill');
      pills.forEach(p => {
        if ((!activeCategory && p.id === 'btnFilterAll') || (activeCategory && p.getAttribute('onclick')?.includes(`'${activeCategory}'`))) {
          p.classList.add('active');
          p.classList.remove('secondary');
        } else {
          p.classList.remove('active');
          p.classList.add('secondary');
        }
      });
      loadDashboard();
    }

    function setSqlQuery(sql) {
      document.getElementById('sqlQueryInput').value = sql;
      executeCustomSql();
    }

    async function executeCustomSql() {
      const sqlInput = document.getElementById('sqlQueryInput');
      const sql = sqlInput && sqlInput.value ? sqlInput.value.trim() : '';
      if (!sql) return;
      const res = await fetch('/api/logs/sql_query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql })
      });
      const data = await readSafeJson(res);
      const thead = document.getElementById('sqlResultThead');
      const tbody = document.getElementById('sqlResultTbody');
      thead.innerHTML = '';
      tbody.innerHTML = '';

      if (!res.ok || !data.ok) {
        const msg = res.status === 401 || res.status === 403
          ? ((data && data.error) || 'Bạn cần đăng nhập quyền Chủ nhà để truy vấn dữ liệu')
          : resolveLogsHttpError(res, data, 'Không thực thi được truy vấn SQL');
        tbody.innerHTML = `<tr><td style="color:var(--danger);">${maskSensitiveLogText(msg)}</td></tr>`;
        if (res.status === 401 || res.status === 403) {
          showLogsActionStatus('Bạn cần đăng nhập quyền Chủ nhà để truy vấn nhật ký', true);
        }
        return;
      }
      const rows = data.rows || [];
      if (rows.length === 0) {
        tbody.innerHTML = `<tr><td style="color:var(--muted);">Chưa có sự kiện</td></tr>`;
        return;
      }
      const cols = Object.keys(rows[0]);
      thead.innerHTML = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
      rows.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = cols.map(c => `<td><code>${r[c] !== null && r[c] !== undefined ? maskSensitiveLogText(String(r[c])) : '—'}</code></td>`).join('');
        tbody.appendChild(tr);
      });
    }

    let searchDebounceTimer = null;
    window.addEventListener('DOMContentLoaded', () => {
      setLogsAdminUiState(false);

      const adminMenu = document.getElementById('logsAdminMenu');
      const adminSummary = document.getElementById('logsAdminSummary');
      if (adminSummary && typeof adminSummary.addEventListener === 'function') {
        adminSummary.addEventListener('click', (e) => {
          if (!isLogsAdminAuthorized) {
            if (e && typeof e.preventDefault === 'function') e.preventDefault();
            if (adminMenu) adminMenu.open = false;
            showLogsActionStatus('Chỉ Chủ nhà (Cấp 1) mới sử dụng được menu Quản trị.', true);
          }
        });
      }
      if (adminMenu && typeof adminMenu.addEventListener === 'function') {
        adminMenu.addEventListener('toggle', () => {
          if (!isLogsAdminAuthorized && adminMenu.open) {
            adminMenu.open = false;
            showLogsActionStatus('Chỉ Chủ nhà (Cấp 1) mới sử dụng được menu Quản trị.', true);
          }
        });
      }

      const searchInput = document.getElementById('logSearchInput');
      if (searchInput) {
        searchInput.addEventListener('input', () => {
          clearTimeout(searchDebounceTimer);
          searchDebounceTimer = setTimeout(() => {
            loadDashboard();
          }, 250);
        });
      }
      const dateRangeSelect = document.getElementById('logDateRange');
      if (dateRangeSelect) {
        dateRangeSelect.addEventListener('change', () => {
          currentPage = 1;
          renderLogsPage();
        });
      }
      Promise.resolve(loadDashboard()).then((ok) => {
        if (ok) {
          executeCustomSql();
        }
      });
    });

// Window exports for inline event handlers
window.showLogsActionStatus = showLogsActionStatus;
window.setLogsAdminUiState = setLogsAdminUiState;
window.copyTextValue = copyTextValue;
window.deriveResultStatus = deriveResultStatus;
window.toggleLogDetailRow = toggleLogDetailRow;
window.loadDashboard = loadDashboard;
window.addKnowledgeEntry = addKnowledgeEntry;
window.seedDemoLog = seedDemoLog;
window.clearCustomLogs = clearCustomLogs;
window.confirmClearLogs = confirmClearLogs;
window.exportLogsCsv = exportLogsCsv;
window.setLogCategoryFilter = setLogCategoryFilter;
window.setSqlQuery = setSqlQuery;
window.executeCustomSql = executeCustomSql;
window.renderLogsPage = renderLogsPage;
window.loadMoreLogs = loadMoreLogs;
window.getFilteredLogs = getFilteredLogs;
window.maskSensitiveLogText = maskSensitiveLogText;
