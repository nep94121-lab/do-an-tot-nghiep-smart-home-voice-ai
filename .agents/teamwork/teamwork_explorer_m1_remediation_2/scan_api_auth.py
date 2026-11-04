import ast
import pathlib

for folder in ['simulator/api', 'simulator/auth']:
    for f in sorted(pathlib.Path(folder).glob('*.py')):
        text = f.read_text(encoding='utf-8')
        for word in ['write', 'dump', 'save', 'open', 'flush']:
            if word in text:
                # find matching lines
                lines = [(i+1, line.strip()) for i, line in enumerate(text.splitlines()) if word in line]
                for lno, line in lines:
                    # filter out comments
                    if not line.startswith('#'):
                        print(f"{f.as_posix()}:{lno} [{word}] -> {line}")
