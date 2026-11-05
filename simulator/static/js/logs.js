    let activeCategory = '';
    let lastLoadedLogs = [];

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
        .replace(/(Mật khẩu gợi ý:\s*)([^\s\)]+)/gi, '$1******')
        .replace(/(Gợi ý mật khẩu:\s*)([^\s\)]+)/gi, '$1******')
        .replace(/(Mật khẩu:\s*)([^\s\)]+)/gi, '$1******')
        .replace(/((?:password|password_plain_hint|mat_khau|mk)["']?\s*[:=]\s*["'])([^"']+)(["'])/gi, '$1******$3');
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
          const detText = maskSensitiveLogText(item.detail || 'Không có mô tả bổ sung.');
          const tr = document.createElement('tr');
          tr.className = 'log-row';
          tr.onclick = () => toggleLogDetailRow(idx);
          tr.innerHTML = `
            <td>${item.time || '—'}</td>
            <td style="font-weight:500;">${evText}</td>
            <td>${item.actor || 'Hệ thống'}</td>
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
              <span>${item.actor || 'Hệ thống'}</span>
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
      const q = document.getElementById('logSearchInput').value.trim();
      const url = `/api/logs/dashboard?category=${encodeURIComponent(activeCategory)}&q=${encodeURIComponent(q)}`;
      const res = await fetch(url);
      const data = await res.json();

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
    }

    async function addKnowledgeEntry() {
      const topic = document.getElementById('kbTopic').value.trim();
      const keywords = document.getElementById('kbKeywords').value.trim();
      const content = document.getElementById('kbContent').value.trim();
      const min_tier = parseInt(document.getElementById('kbTier').value, 10);
      if (!topic || !content) return;

      await fetch('/api/logs/knowledge/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, keywords, content, min_tier })
      });
      document.getElementById('kbTopic').value = '';
      document.getElementById('kbKeywords').value = '';
      document.getElementById('kbContent').value = '';
      loadDashboard();
    }

    async function seedDemoLog() {
      await fetch('/api/logs/append', {
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
      loadDashboard();
    }

    async function clearCustomLogs() {
      await fetch('/api/logs/clear', { method: 'POST' });
      loadDashboard();
    }

    function confirmClearLogs() {
      if (window.confirm('Bạn có chắc muốn xóa nhật ký?')) {
        clearCustomLogs();
      }
    }

    function exportLogsCsv() {
      const rows = [['Thời gian', 'Danh mục', 'Sự kiện', 'Thiết bị / người dùng', 'Kết quả', 'Chi tiết']];
      (lastLoadedLogs || []).forEach(item => {
        const st = deriveResultStatus(item);
        rows.push([
          item.time || '',
          item.category || item.cat || '',
          item.event || '',
          item.actor || '',
          st.label,
          item.detail || ''
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
      const sql = document.getElementById('sqlQueryInput').value.trim();
      if (!sql) return;
      const res = await fetch('/api/logs/sql_query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql })
      });
      const data = await res.json();
      const thead = document.getElementById('sqlResultThead');
      const tbody = document.getElementById('sqlResultTbody');
      thead.innerHTML = '';
      tbody.innerHTML = '';

      if (!data.ok) {
        tbody.innerHTML = `<tr><td style="color:var(--danger);">${data.error}</td></tr>`;
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
        tr.innerHTML = cols.map(c => `<td><code>${r[c] !== null && r[c] !== undefined ? String(r[c]) : '—'}</code></td>`).join('');
        tbody.appendChild(tr);
      });
    }

    let searchDebounceTimer = null;
    window.addEventListener('DOMContentLoaded', () => {
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
      loadDashboard();
      executeCustomSql();
    });

// Window exports for inline event handlers
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
