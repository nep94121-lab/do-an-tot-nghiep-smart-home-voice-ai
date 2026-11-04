import pathlib

root = pathlib.Path('simulator')
for p in sorted(root.rglob('*.py')):
    try:
        lines = p.read_text(encoding='utf-8', errors='ignore').splitlines()
        for i, line in enumerate(lines, 1):
            if any(k in line for k in ['write_text', 'write_bytes', 'open(', 'Path.write']):
                print(f'{p}:{i}: {line.strip()}')
    except Exception as e:
        pass
