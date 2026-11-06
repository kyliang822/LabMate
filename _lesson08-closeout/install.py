"""Incremental installer: no secrets, requirements, old migrations or existing reports replaced."""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

root = Path.cwd()
payload = Path(__file__).resolve().parent
if not (root / 'compose.yaml').exists():
    raise SystemExit('Run from the LabMate root.')
# Ensure predictable integration points before modifying files.
main_path = root / 'backend/app/main.py'
service_path = root / 'backend/app/async_tasks/service.py'
main = main_path.read_text(encoding='utf-8-sig')
service = service_path.read_text(encoding='utf-8-sig')
if 'def authenticated(' not in main or 'def administrator(' not in main:
    raise SystemExit('Unsupported main.py; no files changed.')
if 'def identity(token):\n' not in service:
    raise SystemExit('Unsupported identity function; no files changed.')
git_dir = subprocess.check_output(['git', 'rev-parse', '--git-dir'], text=True).strip()
backup = root / git_dir / 'lesson08-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
backup.mkdir(parents=True)
files = [p for p in (payload / 'files').rglob('*') if p.is_file()]
for p in files:
    relative = p.relative_to(payload / 'files')
    target = root / relative
    if target.exists():
        previous = backup / relative
        previous.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, previous)
for target in [main_path, service_path, root / 'README.md']:
    previous = backup / target.relative_to(root)
    previous.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, previous)
for p in files:
    target = root / p.relative_to(payload / 'files')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, target)
if 'from backend.app.lesson08_api import create_router' not in main:
    main += '\n\nfrom backend.app.lesson08_api import create_router  # noqa: E402\napp.include_router(create_router(authenticated, administrator))\n'
main_path.write_text(main, encoding='utf-8')
if 'verify_signature_if_present(token)' not in service:
    service = service.replace('def identity(token):\n', 'def identity(token):\n    from backend.app.lesson08_service import verify_signature_if_present\n    verify_signature_if_present(token)\n', 1)
service_path.write_text(service, encoding='utf-8')
readme = root / 'README.md'
text = readme.read_text(encoding='utf-8-sig')
if '<!-- lesson08-closeout -->' not in text:
    text += '''\n\n<!-- lesson08-closeout -->
## 第八课最小闭环新增入口

运行与真人复核说明：docs/closeout/lesson08-fast.md。
Windows统一安全命令：`.\\.venv\\Scripts\\python.exe -m scripts.check_security`，同时覆盖SEC-05秘密扫描和SEC-06 Python/npm依赖审计；新结果按时间戳保存reports/evidence/，发现和阻塞保留非零退出码。
一键安装/真实验收：`powershell -NoProfile -ExecutionPolicy Bypass -File .\\Complete-Lesson08.ps1`。
新增关键词检索、受保护的实际配置写入口、密码登录和资料查询子技能；旧安全红项不提前修复。真实LLM问答/完整三技能仍属后续范围，真人复核不代签。
'''
    readme.write_text(text, encoding='utf-8')
print('Incremental source installation complete; backups:', backup)
print('No .env, requirements, existing reports or old migrations replaced.')
