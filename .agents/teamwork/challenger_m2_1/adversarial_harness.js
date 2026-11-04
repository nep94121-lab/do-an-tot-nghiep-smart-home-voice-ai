/**
 * Adversarial Test Harness for Milestone 2:
 * Login Gate Lockdown, Password UX & Mobile SVG Fix
 *
 * Author: empirical_challenger (Challenger 1)
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..', '..');

// Test tracking
let passed = 0;
let failed = 0;
const results = [];

function assert(condition, description) {
  if (condition) {
    passed++;
    results.push({ test: description, status: 'PASS' });
    console.log(`  [PASS] ${description}`);
  } else {
    failed++;
    results.push({ test: description, status: 'FAIL' });
    console.error(`  [FAIL] ${description}`);
  }
}

// Minimal DOM Element Simulator
class MockElement {
  constructor(tagName = 'div', id = '') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.classList = new Set();
    this.attributes = {};
    this.style = {};
    this.value = '';
    this.type = 'text';
    this.readOnly = false;
    this.disabled = false;
    this.hidden = false;
    this.textContent = '';
    this.innerHTML = '';
    this.listeners = {};
    this.parent = null;
    this.children = [];
  }

  getAttribute(attr) { return this.attributes[attr] || null; }
  setAttribute(attr, val) { this.attributes[attr] = String(val); }
  removeAttribute(attr) { delete this.attributes[attr]; }
  hasAttribute(attr) { return attr in this.attributes; }

  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }

  dispatchEvent(event) {
    const list = this.listeners[event.type] || [];
    for (const fn of list) {
      fn.call(this, event);
    }
  }

  click() {
    this.dispatchEvent({ type: 'click', target: this, preventDefault() {}, stopPropagation() {} });
  }

  scrollIntoView() {}
  focus() {}
  blur() {}
}

MockElement.prototype.classList = {
  // set-like proxy created per instance
};

function createElement(tagName = 'div', id = '') {
  const el = new MockElement(tagName, id);
  const classes = new Set();
  el.classList = {
    add: (...cls) => cls.forEach(c => classes.add(c)),
    remove: (...cls) => cls.forEach(c => classes.delete(c)),
    toggle: (c) => classes.has(c) ? (classes.delete(c), false) : (classes.add(c), true),
    contains: (c) => classes.has(c),
  };
  return el;
}

// ============================================================================
// TEST SUITE 1: Web Login Gate Lockdown & Bypass Prevention
// ============================================================================
console.log('\n=== SUITE 1: Web Login Gate Bypass Stress Tests ===');

function setupWebEnvironment(initialSession = null) {
  const elements = {};
  function getEl(id, tag = 'div') {
    if (!elements[id]) {
      elements[id] = createElement(tag, id);
    }
    return elements[id];
  }

  // Pre-populate known elements
  getEl('homeLoginGateModal');
  getEl('btnCloseLoginGateModal', 'button');
  getEl('gateStatusBox');
  getEl('btnTabGateLogin', 'button');
  getEl('btnTabGateRegister', 'button');
  getEl('btnTabGateForgot', 'button');
  getEl('gatePanelLogin', 'form');
  getEl('gatePanelRegister', 'form');
  getEl('gatePanelForgot', 'form');
  getEl('gateLoginEmail', 'input');
  getEl('gateLoginPassword', 'input');
  getEl('gateRegTier', 'select');
  getEl('gateRegName', 'input');
  getEl('gateRegEmail', 'input');
  getEl('gateRegPassword', 'input');
  getEl('gateRegConfirmPassword', 'input');
  getEl('gateForgotEmail', 'input');
  getEl('gateForgotOtpInput', 'input');
  getEl('gateForgotNewPassword', 'input');
  getEl('gateForgotConfirmPassword', 'input');
  getEl('btnSubmitGateLogin', 'button');
  getEl('btnSubmitGateRegister', 'button');
  getEl('btnSendForgotOtp', 'button');
  getEl('btnSubmitForgotReset', 'button');
  getEl('btnLogoutHome', 'button');
  getEl('currentUserBadge');

  let storage = {};
  if (initialSession) {
    storage['smarthome_auth_session'] = JSON.stringify(initialSession);
  }

  const docListeners = {};
  const mockWindow = {
    document: {
      getElementById: (id) => getEl(id),
      querySelector: (sel) => {
        if (sel.startsWith('#')) return getEl(sel.slice(1));
        return createElement();
      },
      querySelectorAll: () => [],
      createElement: (tag) => createElement(tag),
      addEventListener: (evt, fn) => {
        if (!docListeners[evt]) docListeners[evt] = [];
        docListeners[evt].push(fn);
      },
    },
    localStorage: {
      getItem: (k) => (k in storage ? storage[k] : null),
      setItem: (k, v) => { storage[k] = String(v); },
      removeItem: (k) => { delete storage[k]; }
    },
    fetch: async (url, opts) => ({
      ok: true,
      json: async () => ({ ok: false, error: 'Mock response' })
    }),
    location: { href: 'http://localhost:8088/', search: '', protocol: 'http:', host: 'localhost:8088', pathname: '/' },
    setTimeout: (fn) => fn(),
    clearTimeout: () => {},
    setInterval: () => {},
    clearInterval: () => {},
    WebSocket: class { constructor() {} addEventListener() {} send() {} close() {} },
    AudioContext: class { createMediaStreamSource() { return { connect() {} }; } },
    webkitAudioContext: class {},
    navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) }, clipboard: { writeText: async () => {} } },
  };
  mockWindow.window = mockWindow;
  mockWindow.globalThis = mockWindow;

  const appJsCode = fs.readFileSync(path.join(ROOT, 'simulator', 'static', 'js', 'app.js'), 'utf8');
  const ctx = vm.createContext(mockWindow);
  vm.runInContext(appJsCode, ctx);

  return { mockWindow, elements, docListeners, getEl, storage };
}

// Test 1.1: Escape key attack without session
{
  const env = setupWebEnvironment(null);
  const modal = env.elements['homeLoginGateModal'];
  modal.classList.remove('hidden'); // Modal is currently visible

  let defaultPrevented = false;
  let propagationStopped = false;
  const escEvent = {
    key: 'Escape',
    preventDefault: () => { defaultPrevented = true; },
    stopPropagation: () => { propagationStopped = true; }
  };

  const keyListeners = env.docListeners['keydown'] || [];
  for (const fn of keyListeners) fn(escEvent);

  assert(
    !modal.classList.contains('hidden'),
    'Attack 1.1: Escape key pressed without session must NOT hide homeLoginGateModal'
  );
  assert(
    defaultPrevented === true,
    'Attack 1.1b: Escape key pressed without session must invoke preventDefault()'
  );
  assert(
    env.elements['gateStatusBox'].textContent.includes('⚠️ Bạn bắt buộc phải đăng nhập'),
    'Attack 1.1c: Warning banner displayed when Escape is pressed without session'
  );
}

// Test 1.2: Backdrop click attack without session
{
  const env = setupWebEnvironment(null);
  const modal = env.elements['homeLoginGateModal'];
  modal.classList.remove('hidden');

  // Click on the backdrop (e.target === homeLoginGateModal)
  modal.dispatchEvent({
    type: 'click',
    target: modal,
    preventDefault: () => {},
    stopPropagation: () => {}
  });

  assert(
    !modal.classList.contains('hidden'),
    'Attack 1.2: Backdrop click without session must NOT hide homeLoginGateModal'
  );
  assert(
    env.elements['gateStatusBox'].textContent.includes('⚠️ Bạn bắt buộc phải đăng nhập'),
    'Attack 1.2b: Warning banner displayed when backdrop is clicked without session'
  );
}

// Test 1.3: Direct close button click without session
{
  const env = setupWebEnvironment(null);
  const modal = env.elements['homeLoginGateModal'];
  const btnClose = env.elements['btnCloseLoginGateModal'];
  modal.classList.remove('hidden');

  btnClose.click();

  assert(
    !modal.classList.contains('hidden'),
    'Attack 1.3: Direct close button click without session must NOT hide homeLoginGateModal'
  );
  assert(
    env.elements['gateStatusBox'].textContent.includes('⚠️ Bạn bắt buộc phải đăng nhập'),
    'Attack 1.3b: Warning banner displayed when close button clicked without session'
  );
}

// Test 1.4: Tampered / Empty / Invalid JSON session in localStorage
{
  const env = setupWebEnvironment(null);
  const modal = env.elements['homeLoginGateModal'];
  modal.classList.remove('hidden');

  // Subtest a: empty object
  env.mockWindow.localStorage.setItem('smarthome_auth_session', '{}');
  env.elements['btnCloseLoginGateModal'].click();
  assert(!modal.classList.contains('hidden'), 'Attack 1.4a: Empty session object {} does not bypass modal');

  // Subtest b: corrupted JSON
  env.mockWindow.localStorage.setItem('smarthome_auth_session', '{not valid json');
  env.elements['btnCloseLoginGateModal'].click();
  assert(!modal.classList.contains('hidden'), 'Attack 1.4b: Corrupted JSON does not crash or bypass modal');

  // Subtest c: session with no email
  env.mockWindow.localStorage.setItem('smarthome_auth_session', JSON.stringify({ tier: 1 }));
  env.elements['btnCloseLoginGateModal'].click();
  assert(!modal.classList.contains('hidden'), 'Attack 1.4c: Session without email does not bypass modal');
}

// Test 1.5: Valid authenticated session allows closing
{
  const env = setupWebEnvironment({ email: 'nep94121@gmail.com', display_name: 'Nguyễn Tuấn Anh', tier: 1 });
  const modal = env.elements['homeLoginGateModal'];
  modal.classList.remove('hidden');

  env.elements['btnCloseLoginGateModal'].click();
  assert(
    modal.classList.contains('hidden'),
    'Test 1.5: Valid session allows closeLoginGateModal() to close homeLoginGateModal'
  );
}

// ============================================================================
// TEST SUITE 2: Password Mismatch Prevention (Web & Mobile)
// ============================================================================
console.log('\n=== SUITE 2: Password Mismatch Prevention Stress Tests ===');

// Test 2.1: Web Register Mismatched Passwords
{
  const env = setupWebEnvironment(null);
  let networkFetchCalled = false;
  env.mockWindow.fetch = async () => {
    networkFetchCalled = true;
    return { ok: true, json: async () => ({ ok: true }) };
  };

  env.elements['gateRegEmail'].value = 'test@example.com';
  env.elements['gateRegPassword'].value = 'PasswordA123';
  env.elements['gateRegConfirmPassword'].value = 'PasswordB999';

  env.elements['btnSubmitGateRegister'].click();

  assert(
    networkFetchCalled === false,
    'Attack 2.1a: Web register with mismatched passwords must ABORT before network fetch'
  );
  assert(
    env.elements['gateStatusBox'].textContent.includes('không khớp nhau'),
    'Attack 2.1b: Web register displays mismatched password warning'
  );
}

// Test 2.2: Web Forgot Password Reset Mismatched Passwords
{
  const env = setupWebEnvironment(null);
  let networkFetchCalled = false;
  env.mockWindow.fetch = async () => {
    networkFetchCalled = true;
    return { ok: true, json: async () => ({ ok: true }) };
  };

  env.elements['gateForgotEmail'].value = 'nep94121@gmail.com';
  env.elements['gateForgotOtpInput'].value = '123456';
  env.elements['gateForgotNewPassword'].value = 'NewPassword1';
  env.elements['gateForgotConfirmPassword'].value = 'NewPassword2';

  env.elements['btnSubmitForgotReset'].click();

  assert(
    networkFetchCalled === false,
    'Attack 2.2a: Web reset password with mismatched passwords must ABORT before network fetch'
  );
  assert(
    env.elements['gateStatusBox'].textContent.includes('không khớp nhau'),
    'Attack 2.2b: Web reset password displays mismatched password warning'
  );
}

// Mobile Setup
function setupMobileEnvironment() {
  const elements = {};
  function getEl(id, tag = 'div') {
    if (!elements[id]) {
      elements[id] = createElement(tag, id);
    }
    return elements[id];
  }

  getEl('mobileLoginGate');
  getEl('mobileMainContent');
  getEl('mobileBottomNav');
  getEl('mobileLoginForm', 'form');
  getEl('mobileRegisterForm', 'form');
  getEl('mobileLoginEmail', 'input');
  getEl('mobileLoginPassword', 'input');
  getEl('mobileLoginMsg');
  getEl('mobileLoginBtn', 'button');
  getEl('btnMobileTabLogin', 'button');
  getEl('btnMobileTabRegister', 'button');
  getEl('mobileRegTier', 'select');
  getEl('mobileRegName', 'input');
  getEl('mobileRegEmail', 'input');
  getEl('mobileRegPassword', 'input');
  getEl('mobileRegConfirmPassword', 'input');
  getEl('mobileRegMsg');
  getEl('mobileRegisterBtn', 'button');
  getEl('mobileChangeEmail', 'input');
  getEl('mobileChangeNewPassword', 'input');
  getEl('mobileChangeConfirmPassword', 'input');
  getEl('mobileChangePasswordMsg');
  getEl('mobileChangePasswordBtn', 'button');

  let sessionStore = {};
  const mockWindow = {
    document: {
      getElementById: (id) => getEl(id),
      querySelector: (sel) => {
        if (sel.startsWith('#')) return getEl(sel.slice(1));
        return createElement();
      },
      querySelectorAll: () => [],
      createElement: (tag) => createElement(tag),
      addEventListener: () => {},
    },
    sessionStorage: {
      getItem: (k) => (k in sessionStore ? sessionStore[k] : null),
      setItem: (k, v) => { sessionStore[k] = String(v); },
      removeItem: (k) => { delete sessionStore[k]; }
    },
    fetch: async () => ({ ok: true, json: async () => ({ ok: false }) }),
    setTimeout: (fn) => fn(),
    AudioContext: class {},
    webkitAudioContext: class {},
    btoa: (s) => Buffer.from(s).toString('base64'),
    location: { href: 'http://localhost:8088/app' },
  };
  mockWindow.window = mockWindow;
  mockWindow.globalThis = mockWindow;

  const mobJsCode = fs.readFileSync(path.join(ROOT, 'simulator', 'static', 'js', 'mobile_app.js'), 'utf8');
  const ctx = vm.createContext(mockWindow);
  vm.runInContext(mobJsCode, ctx);

  return { mockWindow, elements, getEl, sessionStore };
}

// Test 2.3: Mobile Register Mismatched Passwords
{
  const env = setupMobileEnvironment();
  let networkFetchCalled = false;
  env.mockWindow.fetch = async () => {
    networkFetchCalled = true;
    return { ok: true, json: async () => ({ ok: true }) };
  };

  env.elements['mobileRegEmail'].value = 'test_mob@example.com';
  env.elements['mobileRegPassword'].value = 'PassMob1';
  env.elements['mobileRegConfirmPassword'].value = 'PassMob2';

  // Invoke mobile register handler
  env.mockWindow.submitMobileRegister({ preventDefault() {} });

  assert(
    networkFetchCalled === false,
    'Attack 2.3a: Mobile register with mismatched passwords must ABORT before network fetch'
  );
  assert(
    env.elements['mobileRegMsg'].textContent.includes('không khớp nhau'),
    'Attack 2.3b: Mobile register displays mismatched password warning'
  );
}

// Test 2.4: Mobile Change Password Mismatched Passwords
{
  const env = setupMobileEnvironment();
  let networkFetchCalled = false;
  env.mockWindow.fetch = async () => {
    networkFetchCalled = true;
    return { ok: true, json: async () => ({ ok: true }) };
  };

  env.elements['mobileChangeEmail'].value = 'nep94121@gmail.com';
  env.elements['mobileChangeNewPassword'].value = 'Change1';
  env.elements['mobileChangeConfirmPassword'].value = 'Change2';

  env.mockWindow.submitMobileChangePassword({ preventDefault() {} });

  assert(
    networkFetchCalled === false,
    'Attack 2.4a: Mobile change password with mismatched passwords must ABORT before network fetch'
  );
  assert(
    env.elements['mobileChangePasswordMsg'].textContent.includes('không khớp nhau'),
    'Attack 2.4b: Mobile change password displays mismatched password warning'
  );
}

// ============================================================================
// TEST SUITE 3: Password Toggle Visibility (👁️ <-> 🙈)
// ============================================================================
console.log('\n=== SUITE 3: Password Toggle Visibility (👁️ <-> 🙈) ===');

// Test 3.1: Web Toggle Password
{
  const env = setupWebEnvironment(null);
  const pwFields = [
    'gateLoginPassword',
    'gateRegPassword',
    'gateRegConfirmPassword',
    'gateForgotNewPassword',
    'gateForgotConfirmPassword'
  ];

  for (const fieldId of pwFields) {
    const input = env.elements[fieldId];
    input.type = 'password';
    const btn = createElement('button');
    btn.textContent = '👁️';

    // First toggle: password -> text
    env.mockWindow.togglePasswordVisibility(fieldId, btn);
    assert(
      input.type === 'text' && btn.textContent === '🙈',
      `Test 3.1: Web field #${fieldId} toggled password -> text (icon: 🙈)`
    );

    // Second toggle: text -> password
    env.mockWindow.togglePasswordVisibility(fieldId, btn);
    assert(
      input.type === 'password' && btn.textContent === '👁️',
      `Test 3.1b: Web field #${fieldId} toggled text -> password (icon: 👁️)`
    );
  }
}

// Test 3.2: Mobile Toggle Password
{
  const env = setupMobileEnvironment();
  const mobPwFields = [
    'mobileLoginPassword',
    'mobileRegPassword',
    'mobileRegConfirmPassword',
    'mobileChangeNewPassword',
    'mobileChangeConfirmPassword'
  ];

  for (const fieldId of mobPwFields) {
    const input = env.elements[fieldId];
    input.type = 'password';
    const btn = createElement('button');
    btn.textContent = '👁️';

    // First toggle: password -> text
    env.mockWindow.togglePasswordVisibility(fieldId, btn);
    assert(
      input.type === 'text' && btn.textContent === '🙈',
      `Test 3.2: Mobile field #${fieldId} toggled password -> text (icon: 🙈)`
    );

    // Second toggle: text -> password
    env.mockWindow.togglePasswordVisibility(fieldId, btn);
    assert(
      input.type === 'password' && btn.textContent === '👁️',
      `Test 3.2b: Mobile field #${fieldId} toggled text -> password (icon: 👁️)`
    );
  }
}

// ============================================================================
// TEST SUITE 4: Editable Inputs in simulator/static/js/auth.js
// ============================================================================
console.log('\n=== SUITE 4: Editable Inputs in auth.js Stress Tests ===');

{
  const elements = {};
  function getEl(id, tag = 'div') {
    if (!elements[id]) {
      elements[id] = createElement(tag, id);
    }
    return elements[id];
  }

  getEl('firstPageAccountSelect', 'select');
  getEl('firstPageTierSelect', 'select');
  getEl('enrollSpeakerNameInput', 'input');
  getEl('step2SpeakerNameInput', 'input');
  getEl('loginEmail', 'input');
  getEl('step2SpeakerSummaryBadge');
  getEl('auth3TierBadge');
  getEl('enrollPromptText');
  getEl('firstPageReadingPrompt');

  const mockWindow = {
    document: {
      getElementById: (id) => getEl(id),
      querySelector: (sel) => {
        if (sel.startsWith('#')) return getEl(sel.slice(1));
        return createElement();
      },
      querySelectorAll: () => [],
      createElement: (tag) => createElement(tag),
      addEventListener: () => {},
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    location: { href: 'http://localhost:8088/auth.html' },
    setTimeout: (fn) => fn(),
    AudioContext: class {},
    webkitAudioContext: class {},
    navigator: { mediaDevices: { getUserMedia: async () => ({}) } },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true }) }),
  };
  mockWindow.window = mockWindow;
  mockWindow.globalThis = mockWindow;

  const authJsCode = fs.readFileSync(path.join(ROOT, 'simulator', 'static', 'js', 'auth.js'), 'utf8');
  const ctx = vm.createContext(mockWindow);
  vm.runInContext(authJsCode, ctx);

  const nameInput = elements['enrollSpeakerNameInput'];
  const emailInput = elements['loginEmail'];
  const step2NameInput = elements['step2SpeakerNameInput'];

  // Test Tier 1: Chủ nhà
  mockWindow.onEnrollTierSelectChange(1);
  assert(
    nameInput.readOnly === false,
    'Test 4.1a: Tier 1 (Chủ nhà) enrollSpeakerNameInput.readOnly is strictly false'
  );
  assert(
    emailInput.readOnly === false,
    'Test 4.1b: Tier 1 (Chủ nhà) loginEmail.readOnly is strictly false'
  );

  // Test User editing name directly in Step 1
  nameInput.value = 'Nguyễn Tuấn Anh (Tự sửa)';
  assert(
    nameInput.readOnly === false && nameInput.value === 'Nguyễn Tuấn Anh (Tự sửa)',
    'Test 4.2a: User can freely edit enrollSpeakerNameInput without being blocked by readOnly'
  );

  // Test Step 2 reverse synchronization
  mockWindow.onStep2SpeakerNameInput('Nguyễn Tuấn Anh (Từ Bước 2)');
  assert(
    nameInput.value === 'Nguyễn Tuấn Anh (Từ Bước 2)',
    'Test 4.2b: Step 2 input successfully reverse synchronizes to step 1 enrollSpeakerNameInput'
  );

  // Test User editing email directly
  emailInput.value = 'tuananh.personal@gmail.com';
  assert(
    emailInput.value === 'tuananh.personal@gmail.com' && emailInput.readOnly === false,
    'Test 4.3: Custom email is editable and not locked by readonly'
  );

  // Test Tier 2: Thành viên gia đình
  mockWindow.onEnrollTierSelectChange(2);
  assert(
    nameInput.readOnly === false && emailInput.readOnly === false,
    'Test 4.4a: Tier 2 (Gia đình) inputs are strictly readOnly === false'
  );

  // Test Tier 3: Khách
  mockWindow.onEnrollTierSelectChange(3);
  assert(
    nameInput.readOnly === false && emailInput.readOnly === false,
    'Test 4.4b: Tier 3 (Khách) inputs are strictly readOnly === false'
  );
}

// ============================================================================
// TEST SUITE 5: Mobile SVG Sprite Scope & Login Gate Icon Visibility
// ============================================================================
console.log('\n=== SUITE 5: Mobile SVG Sprite Scope Stress Tests ===');
{
  const mobileHtml = fs.readFileSync(path.join(ROOT, 'mobile_app', 'index.html'), 'utf8');

  // Verify symbol id="i-home" is present
  const symbolHomeIdx = mobileHtml.indexOf('<symbol id="i-home"');
  assert(symbolHomeIdx !== -1, 'Test 5.1: <symbol id="i-home"> exists in mobile_app/index.html');

  // Verify mobileMainContent has hidden attribute
  const mainContentIdx = mobileHtml.indexOf('<div id="mobileMainContent" hidden>');
  assert(mainContentIdx !== -1, 'Test 5.2: <div id="mobileMainContent" hidden> exists with hidden attribute');

  // Verify symbol id="i-home" is located BEFORE mobileMainContent
  assert(
    symbolHomeIdx < mainContentIdx,
    'Test 5.3: <symbol id="i-home"> is placed OUTSIDE and BEFORE <div id="mobileMainContent" hidden>'
  );

  // Verify mobileLoginGate is located OUTSIDE and BEFORE mobileMainContent
  const loginGateIdx = mobileHtml.indexOf('<div id="mobileLoginGate"');
  assert(
    loginGateIdx !== -1 && loginGateIdx < mainContentIdx,
    'Test 5.4: #mobileLoginGate is placed OUTSIDE and BEFORE <div id="mobileMainContent" hidden>'
  );

  // Verify mobileLoginGate uses #i-home icon
  const loginGateContent = mobileHtml.substring(loginGateIdx, mainContentIdx);
  assert(
    loginGateContent.includes('href="#i-home"'),
    'Test 5.5: #mobileLoginGate references href="#i-home" while outside the hidden content'
  );

  // Verify no duplicate/nested symbol inside mobileMainContent
  const mainContentEndIdx = mobileHtml.indexOf('</body>');
  const mainContentSubstr = mobileHtml.substring(mainContentIdx, mainContentEndIdx);
  assert(
    !mainContentSubstr.includes('<symbol id="i-home"'),
    'Test 5.6: No trapped <symbol id="i-home"> inside <div id="mobileMainContent">'
  );
}

// ============================================================================
// SUMMARY
// ============================================================================
console.log('\n========================================================');
console.log(`TOTAL ADVERSARIAL TESTS: ${passed + failed}`);
console.log(`PASSED: ${passed}`);
console.log(`FAILED: ${failed}`);
console.log('========================================================\n');

if (failed > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
