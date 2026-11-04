import os

exts = ('.py', '.js', '.kt', '.html', '.css', '.ino', '.cpp')
target_dirs = ['simulator', 'android_app', 'api', 'mobile_app', 'tests', 'scripts', 'firmware_esp8266']
ignore_dirs = {'.git', '.pytest_tmp', '.venv', 'node_modules', 'build', '.gradle', '.agents', '.idea', 'gradle'}

results = []
for td in target_dirs:
    if not os.path.exists(td):
        continue
    for root, dirs, files in os.walk(td):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ignore_dirs]
        for file in files:
            if any(file.endswith(ext) for ext in exts):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = sum(1 for _ in f)
                    size_kb = round(os.path.getsize(full_path) / 1024, 1)
                    rel_path = os.path.relpath(full_path, '.').replace('\\', '/')
                    results.append((lines, size_kb, rel_path))
                except Exception as e:
                    pass

results.sort(key=lambda x: x[0], reverse=True)

print(f"Total scanned source files: {len(results)}\n")
print(f"| Lines | Size (KB) | File Path |")
print(f"|-------|-----------|-----------|")
for lines, size_kb, rel_path in results:
    if lines >= 100:
        print(f"| {lines:5d} | {size_kb:7.1f} | {rel_path} |")

print("\n--- KOTLIN FILES ---")
for lines, size_kb, rel_path in results:
    if rel_path.endswith('.kt'):
        print(f"| {lines:5d} | {size_kb:7.1f} | {rel_path} |")
