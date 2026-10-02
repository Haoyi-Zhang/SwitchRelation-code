#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import ast, json, re, sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
FORBIDDEN_CALLS = {'eval', 'exec'}
FORBIDDEN_MODULES = {'pickle', 'marshal', 'dill'}
issues: list[str] = []
warnings: list[str] = []
parsed = 0
for path in sorted(ROOT.rglob('*.py')):
    if any(part in {'__pycache__', '.git'} for part in path.parts):
        continue
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except Exception as exc:
        issues.append(f'{path.relative_to(ROOT)}: parse failure: {exc}')
        continue
    parsed += 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import) else [(node.module or '').split('.')[0]]
            for name in names:
                if name in FORBIDDEN_MODULES:
                    issues.append(f'{path.relative_to(ROOT)}:{node.lineno}: forbidden deserializer import {name}')
        if isinstance(node, ast.Call):
            fn = node.func.id if isinstance(node.func, ast.Name) else None
            if fn in FORBIDDEN_CALLS:
                issues.append(f'{path.relative_to(ROOT)}:{node.lineno}: dynamic execution call {fn}')
        if isinstance(node, ast.Assert) and ('test' not in {p.lower() for p in path.parts}):
            warnings.append(f'{path.relative_to(ROOT)}:{node.lineno}: production assert can disappear under -O')

# Certificates must be parseable by the strict, producer-independent preflight.
sys.path.insert(0, str(SRC))
from strict_json import load_strict, StrictJSONError
certs = sorted(
    p for p in (ROOT / 'certificates').rglob('*.json')
    if p.is_file()
)
if len(certs) != 166:
    issues.append(f'expected 166 retained certificate JSON files, found {len(certs)}')
strict_ok = 0
for p in certs:
    try:
        load_strict(p)
        strict_ok += 1
    except StrictJSONError as exc:
        issues.append(f'{p.relative_to(ROOT)}: strict JSON rejection: {exc}')

result = {'status': 'PASS' if not issues else 'FAIL', 'python_files_parsed': parsed,
          'certificate_json_files_strictly_parsed': strict_ok,
          'issues': issues, 'warnings': warnings}
out = ROOT / 'results' / 'structural_audit.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if not issues else 1)
