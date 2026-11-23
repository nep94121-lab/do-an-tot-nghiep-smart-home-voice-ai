import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

kind, directory, data_dir = sys.argv[1:]
barrier = pathlib.Path(directory)
data_dir = pathlib.Path(data_dir)
from backend.auth import sqlite_security_repo as repo

if kind == 'stale_clear':
    snapshot = json.loads(repo.load_accounts_sqlite(data_dir))
    account = next(a for a in snapshot['accounts'] if a.get('pending_otp'))
    account.pop('pending_otp')
    stale = json.dumps(dict(accounts=[account], partial=True, cleared_otp_emails=[account['email']], snapshot_loaded_at=time.time())).encode()

(barrier / 'ready').write_text('ready')
deadline = time.monotonic() + 30
while not (barrier / 'release').exists():
    if time.monotonic() >= deadline:
        raise TimeoutError('Review barrier did not release')
    time.sleep(.01)

if kind == 'stale_clear':
    repo.save_accounts_sqlite(stale, data_dir)
    print('WRITE_OK')
elif kind == 'verify_pin':
    from backend.auth.owner_pin import verify_pin
    incoming = json.loads(sys.stdin.read())
    result = verify_pin(incoming['wrong'])
    print('REJECT' if not result['ok'] else 'UNEXPECTED_SUCCESS')
elif kind == 'issue_pin':
    from backend.auth.owner_pin import issue_reset_otp
    result, _ = issue_reset_otp()
    print('ISSUED' if result['ok'] else 'REJECT')
