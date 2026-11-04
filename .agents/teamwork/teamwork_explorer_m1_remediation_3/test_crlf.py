import pathlib
import tempfile

with tempfile.NamedTemporaryFile(delete=False) as tf:
    p = pathlib.Path(tf.name)

# 1. Test write_text without newline on Windows
p.write_text('{\n  "test": 1\n}\n', encoding='utf-8')
data1 = p.read_bytes()
print('Without newline: CRLF count =', data1.count(b'\r\n'))

# 2. Test write_text with newline="\n" on Windows
p.write_text('{\n  "test": 1\n}\n', encoding='utf-8', newline='\n')
data2 = p.read_bytes()
print('With newline="\\n": CRLF count =', data2.count(b'\r\n'), 'LF count =', data2.count(b'\n'))
assert b'\r\n' not in data2
print('CONFIRMED: newline="\\n" forces 0 CRLF on Windows!')
