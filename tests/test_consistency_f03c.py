import json
import os
import pathlib
import secrets
import time
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('SMARTHOME_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('SMARTHOME_SECURITY_BACKEND', 'sqlite')
    monkeypatch.setenv('SIMULATOR_OFFLINE_SANDBOX', '1')
    monkeypatch.setenv('SMARTHOME_STATE_FILE', str(tmp_path / 'shared_device_state.json'))
    from backend.auth.session_store import get_session_store
    from backend.auth.sqlite_security_repo import invalidate_accounts_sqlite_cache
    from backend.engine.state_store import set_default_state_backend
    set_default_state_backend(None)
    store = get_session_store()
    previous = store.db_path
    store.db_path = tmp_path / 'smarthome.db'
    invalidate_accounts_sqlite_cache()
    yield tmp_path
    store.db_path = previous
    set_default_state_backend(None)
    invalidate_accounts_sqlite_cache()


def pack(doc):
    return json.dumps(doc).encode()


def issue_login():
    from backend.auth_3layer import ThreeLayerAuthManager
    mgr = ThreeLayerAuthManager()
    acc = next(a for a in mgr.accounts if a['tier'] == 1)
    code = ''.join(str(secrets.randbelow(10)) for _ in range(6))
    salt, digest = mgr._hash_otp_code(code)
    issued = time.time()
    acc['pending_otp'] = dict(email=acc['email'], account_id=acc['account_id'], tier=1, purpose='layer2_login', otp_salt=salt, otp_hash=digest, created_at=issued, expires_at=issued+300, consumed=False)
    mgr.pending_otps[acc['email']] = acc['pending_otp']
    assert mgr._save_accounts()
    return mgr, acc, code


def verify_login(mgr, acc, code):
    with patch.object(mgr, '_log_event'), patch.object(mgr, '_clear_login_failures'):
        return mgr.layer2_verify_otp(acc['email'], code, expected_purpose='layer2_login')


@pytest.mark.parametrize('legacy', [False, True])
def test_owner_pin_used_snapshot_cannot_replay(isolated, legacy):
    from backend.auth import owner_pin as pin
    from backend.auth.sqlite_security_repo import load_owner_pin_sqlite, save_owner_pin_sqlite
    from backend.auth.security_state import StateConflict
    _, code = pin.issue_reset_otp()
    stale = json.loads(load_owner_pin_sqlite(isolated))
    if legacy:
        stale.pop('revision', None)
    target = ''.join(str(secrets.randbelow(10)) for _ in range(4))
    assert pin.reset_pin_with_otp(code, target, target)['ok']
    try:
        save_owner_pin_sqlite(pack(stale), isolated)
    except StateConflict:
        assert not legacy
    assert not pin.reset_pin_with_otp(code, target, target)['ok']
    assert pin.verify_pin(target)['ok']


@pytest.mark.parametrize('legacy', [False, True])
def test_owner_pin_new_code_survives_old_snapshot(isolated, legacy):
    from backend.auth import owner_pin as pin
    from backend.auth.sqlite_security_repo import load_owner_pin_sqlite, save_owner_pin_sqlite
    from backend.auth.security_state import StateConflict
    now = time.time()
    with patch.object(pin.time, 'time', return_value=now):
        _, old = pin.issue_reset_otp()
    stale = json.loads(load_owner_pin_sqlite(isolated))
    if legacy:
        stale.pop('revision', None)
    target = ''.join(str(secrets.randbelow(10)) for _ in range(4))
    assert pin.reset_pin_with_otp(old, target, target)['ok']
    with patch.object(pin.time, 'time', return_value=now+61):
        _, new = pin.issue_reset_otp()
    try:
        save_owner_pin_sqlite(pack(stale), isolated)
    except StateConflict:
        assert not legacy
    assert pin.reset_pin_with_otp(new, target, target)['ok']
    assert not pin.reset_pin_with_otp(old, target, target)['ok']


def test_login_consumed_snapshot_rejected_and_new_code_usable(isolated):
    from backend.auth.sqlite_security_repo import load_accounts_sqlite, save_accounts_sqlite
    mgr, acc, code = issue_login()
    stale = load_accounts_sqlite(isolated)
    assert verify_login(mgr, acc, code)['ok']
    save_accounts_sqlite(stale, isolated)
    assert not verify_login(mgr, acc, code)['ok']
    mgr, acc, new = issue_login()
    save_accounts_sqlite(stale, isolated)
    assert verify_login(mgr, acc, new)['ok']


def test_qr_used_snapshot_rejected_and_new_invite_usable(isolated):
    from backend.auth import guest_invites as guest
    from backend.auth.sqlite_security_repo import load_invites_sqlite, save_invites_sqlite
    old = guest.create_invite(owner_user_id='tuan_anh', tier=3, duration_code='1d')
    stale = load_invites_sqlite(isolated)
    assert guest._claim_invite_redemption(old['token'])['ok']
    new = guest.create_invite(owner_user_id='tuan_anh', tier=3, duration_code='1d')
    save_invites_sqlite(stale, isolated)
    assert not guest._claim_invite_redemption(old['token'])['ok']
    assert guest._claim_invite_redemption(new['token'])['ok']


def test_qr_empty_snapshot_does_not_delete_consumption_history(isolated):
    from backend.auth import guest_invites as guest
    from backend.auth.sqlite_security_repo import load_invites_sqlite, save_invites_sqlite
    old = guest.create_invite(owner_user_id='tuan_anh', tier=3, duration_code='1d')
    stale = load_invites_sqlite(isolated)
    assert guest.redeem_token(old['token'])['ok']
    save_invites_sqlite(pack({'invites': []}), isolated)
    save_invites_sqlite(stale, isolated)
    result = guest.redeem_token(old['token'])
    assert not result['ok'], 'Consumed QR became usable after empty snapshot followed by older populated snapshot'


def test_qr_empty_snapshot_between_non_empty_preserves_new_and_consumed(isolated):
    from backend.auth import guest_invites as guest
    from backend.auth.sqlite_security_repo import load_invites_sqlite, save_invites_sqlite
    qr1 = guest.create_invite(owner_user_id='tuan_anh', tier=3, duration_code='1d')
    stale_qr1_unconsumed = load_invites_sqlite(isolated)
    assert guest.redeem_token(qr1['token'])['ok']
    qr2 = guest.create_invite(owner_user_id='tuan_anh', tier=3, duration_code='1d')

    # Snapshot rỗng xen giữa
    save_invites_sqlite(pack({'invites': []}), isolated)

    # QR mới vẫn phải tồn tại và dùng được
    assert guest.redeem_token(qr2['token'])['ok'], 'Fresh QR was wiped by empty snapshot'

    # Snapshot cũ chứa QR1 chưa dùng được ghi lại
    save_invites_sqlite(stale_qr1_unconsumed, isolated)

    # QR1 đã dùng tuyệt đối không được sống lại
    assert not guest.redeem_token(qr1['token'])['ok'], 'Consumed QR became usable after empty snapshot interleaved with stale unconsumed snapshot'
    # QR2 đã dùng cũng không được dùng lại
    assert not guest.redeem_token(qr2['token'])['ok'], 'Consumed QR2 became usable again'


def test_login_stale_clear_does_not_consume_new_challenge(isolated):
    from backend.auth.sqlite_security_repo import load_accounts_sqlite, save_accounts_sqlite
    mgr, acc, old = issue_login()
    snapshot = json.loads(load_accounts_sqlite(isolated))
    prior = next(a for a in snapshot['accounts'] if a['account_id'] == acc['account_id'])
    prior.pop('pending_otp', None)
    stale_clear = dict(accounts=[prior], partial=True, cleared_otp_emails=[acc['email']], snapshot_loaded_at=time.time())
    assert verify_login(mgr, acc, old)['ok']
    mgr, acc, new = issue_login()
    save_accounts_sqlite(pack(stale_clear), isolated)
    assert verify_login(mgr, acc, new)['ok'], 'Stale per-email clear consumed freshly issued challenge'


def test_stale_manager_metadata_save_preserves_new_login(isolated):
    mgr, acc, old = issue_login()
    assert verify_login(mgr, acc, old)['ok']
    other, new_acc, new = issue_login()
    stale_account = next(a for a in mgr.accounts if a['account_id'] == acc['account_id'])
    stale_account['display_name'] = 'Metadata updated by previous consumer'
    assert mgr._save_accounts()
    assert verify_login(other, new_acc, new)['ok'], 'A normal manager save after consuming old OTP cleared the newer challenge'


def test_clear_undelivered_pin_code_allows_immediate_retry(isolated):
    from backend.auth import owner_pin as pin
    _, code = pin.issue_reset_otp()
    assert pin.clear_undelivered_reset_otp(code)
    status, new = pin.issue_reset_otp()
    assert status['ok'], 'Undelivered challenge remained active and blocked immediate retry'


def spawn_worker(kind, barrier, directory, payload=None):
    import subprocess
    import sys
    barrier.mkdir(parents=True, exist_ok=True)
    worker_script = str(pathlib.Path(__file__).with_name('worker_consistency.py'))
    proc = subprocess.Popen([sys.executable, worker_script, kind, str(barrier), str(directory)], cwd=str(pathlib.Path(__file__).resolve().parent.parent), env=os.environ.copy(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    if payload is not None:
        proc.stdin.write(json.dumps(payload))
        proc.stdin.close()
        proc.stdin = None
    deadline = time.monotonic()+30
    while not (barrier/'ready').exists():
        if proc.poll() is not None or time.monotonic() >= deadline:
            proc.kill()
            proc.communicate()
            raise AssertionError('Worker did not reach barrier')
        time.sleep(.01)
    return proc


def test_two_processes_stale_clear_preserves_fresh_login(isolated):
    mgr, acc, old = issue_login()
    barrier = isolated/'gate'
    child = spawn_worker('stale_clear', barrier, isolated)
    try:
        assert verify_login(mgr, acc, old)['ok']
        mgr, acc, new = issue_login()
        (barrier/'release').write_text('release')
        stdout, _ = child.communicate(timeout=40)
        assert child.returncode == 0 and stdout.strip() == 'WRITE_OK'
        assert verify_login(mgr, acc, new)['ok'], 'A different process cleared the fresh login challenge using stale data'
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()


@pytest.mark.parametrize('kind', ['verify_pin', 'issue_pin'])
def test_two_processes_pin_transition_same_record(isolated, kind):
    from backend.auth import owner_pin as pin
    from backend.auth.sqlite_security_repo import load_owner_pin_sqlite
    value = ''.join(str(secrets.randbelow(10)) for _ in range(4))
    assert pin.setup_or_replace_pin(value, value)['ok']
    wrong = str((int(value)+1)%10000).zfill(4)
    children = []
    try:
        for index in range(2):
            children.append(spawn_worker(kind, isolated/f'gate{index}', isolated, dict(wrong=wrong)))
        for index in range(2):
            (isolated/f'gate{index}'/'release').write_text('release')
        outputs = []
        for child in children:
            stdout, _ = child.communicate(timeout=40)
            assert child.returncode == 0
            outputs.append(stdout.strip())
        if kind == 'verify_pin':
            assert outputs == ['REJECT','REJECT']
            stored = json.loads(load_owner_pin_sqlite(isolated))
            assert stored['failed_attempts'] == 2
        else:
            assert outputs.count('ISSUED') == 1 and outputs.count('REJECT') == 1
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()


@pytest.mark.parametrize('tier,device,action,allowed', [(1,'main_door','open',False),(1,'alarm_siren','turn_on',False),(2,'main_door','open',False),(3,'garden_pump','turn_on',False),(2,'speaker_amp','turn_on',True),(3,'speaker_amp','turn_on',False),(2,'living_room_light','turn_on',True),(3,'living_room_light','turn_on',True)])
def test_rbac_and_offline_behavior(isolated, tier, device, action, allowed):
    import asyncio
    from backend.rule_engine import SmartHomeEngine
    engine = SmartHomeEngine()
    engine.server_connected = False
    before = engine.devices[device]['state']
    result = asyncio.run(engine.execute_device_action(device_id=device, action=action, request_tier=tier, request_role={1:'ADMIN',2:'MEMBER',3:'CHILD_GUEST'}[tier], request_user_name='Review actor'))
    assert bool(result['ok']) is allowed
    if not allowed:
        assert engine.devices[device]['state'] == before
