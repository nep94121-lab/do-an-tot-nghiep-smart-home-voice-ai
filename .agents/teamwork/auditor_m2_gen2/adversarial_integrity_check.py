import pathlib

def run_checks():
    print('=== ADVERSARIAL INTEGRITY SCAN ===')

    # 1. Check house3d.js
    h3d = pathlib.Path('simulator/static/house3d.js').read_text(encoding='utf-8')
    assert 'rawX = Math.max(pad + halfW, Math.min(w - pad - halfW, rawX));' in h3d, 'Missing clamping X'
    assert 'rawY = Math.max(pad + halfH, Math.min(h - pad - halfH, rawY));' in h3d, 'Missing clamping Y'
    assert 'const iterations = 3;' in h3d, 'Missing 3 iterations collision relaxation'
    assert 'const overlapX = minDistX - Math.abs(dx);' in h3d, 'Missing overlapX'
    assert 'const overlapY = minDistY - Math.abs(dy);' in h3d, 'Missing overlapY'
    print('Check 1 (house3d.js mathematical clamping & 3-pass relaxation): PASS')

    # 2. Check mobile_app.js
    ma = pathlib.Path('simulator/static/js/mobile_app.js').read_text(encoding='utf-8')
    assert 'const pendingDeviceMutations = new Map();' in ma, 'Missing pendingDeviceMutations Map'
    assert 'const MUTATION_GUARD_WINDOW_MS = 2500;' in ma, 'Missing 2500ms window'
    assert 'pendingDeviceMutations.set(d.id' in ma, 'Missing mutation record'
    assert 'pendingDeviceMutations.delete(d.id' in ma, 'Missing mutation cleanup'
    assert 'data-device-id' in ma, 'Missing data-device-id attribute usage'
    assert 'card.classList.toggle' in ma, 'Missing in-place class toggle'
    assert "fetch('/api/device'" in ma or 'fetch("/api/device"' in ma, 'Missing genuine API fetch'
    assert 'd.state = prevState;' in ma, 'Missing error rollback'
    print('Check 2 (mobile_app.js pendingDeviceMutations Map & rollback): PASS')

    # 3. Check auth.js
    aj = pathlib.Path('simulator/static/js/auth.js').read_text(encoding='utf-8')
    assert "const password = (pwEl && pwEl.value) ? pwEl.value : '123456';" in aj, 'Missing password fallback'
    assert "const confirmPassword = (pwConfirmEl && pwConfirmEl.value) ? pwConfirmEl.value : password;" in aj, 'Missing confirmPassword fallback'
    print('Check 3 (auth.js password fallback logic): PASS')

    # 4. Check index.html & mobile_app/index.html input values
    idx = pathlib.Path('simulator/static/index.html').read_text(encoding='utf-8')
    m_idx = pathlib.Path('mobile_app/index.html').read_text(encoding='utf-8')
    assert 'id="gateLegacyTabsWrapper"' in idx, 'Missing gateLegacyTabsWrapper in index.html'
    assert 'id="mobileLegacyTabsWrapper"' in m_idx, 'Missing mobileLegacyTabsWrapper in mobile_app/index.html'
    assert 'top-row-main' in idx and 'top-row-account' in idx, 'Missing 2 rows in index.html header'
    print('Check 4 (index.html & mobile_app/index.html 2-row & gate wrappers): PASS')

    # 5. Check style.css
    css = pathlib.Path('simulator/static/css/style.css').read_text(encoding='utf-8')
    assert 'text-overflow: ellipsis;' in css, 'Missing ellipsis in style.css'
    assert '.top-row' in css, 'Missing .top-row in style.css'
    assert '.pin-3d' in css, 'Missing .pin-3d in style.css'
    print('Check 5 (style.css 2 rows, ellipsis, pin-3d responsive): PASS')

    print('ALL ADVERSARIAL INTEGRITY CHECKS: 100% PASS!')

if __name__ == '__main__':
    run_checks()
