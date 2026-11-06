"""Append only actual live results to fixed course reports; never sign peer review."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    data = json.loads(args.evidence.read_text(encoding='utf-8-sig'))
    results = data.get('results', [])
    names = {r['check'] for r in results if r.get('result') == 'green'}
    required = {'login-adminA', 'login-userA1', 'login-userB1', 'SEC-02-search-userA1',
                'SEC-02-search-userB1', 'SEC-03-userA1', 'SEC-03-no-side-effect',
                'SEC-07-skill-call', 'SEC-07-log', 'SEC-02-skill-context-isolation'}
    if not data.get('all_checks_green') or not required <= names:
        raise SystemExit('Incomplete/red live evidence: no reports modified.')
    digest = hashlib.sha256(args.evidence.read_bytes()).hexdigest()
    stamp = datetime.now().astimezone().isoformat(timespec='seconds')
    marker = '<!-- closeout-evidence:' + digest + ' -->'
    relative = args.evidence.as_posix()
    summary = f'''\n\n{marker}
## 第八课新增功能真实验收：{stamp}

手段：scripts.verify_lesson08_closeout，真实HTTP+PostgreSQL；具体身份、状态码、条数、run_id和日志字段见{relative}。源码指纹亦在原始报告。
查了什么：密码登录、授权关键词召回、实际AI配置写入口、资料查询子技能和日志回查。
判据/实际：A身份召回自身唯一标记资料，B使用者/管理员召回0；普通使用者修改真实配置403且配置/审计无变化；管理员配置幂等；技能调用及本人日志可查、跨实验室日志404。
用量口径：本技能直接检索授权原文，无LLM调用，日志显式记录llm_called=false、0tokens与真实召回数，不冒充DeepSeek调用用量。
结果：本次报告中{len(results)}项全部green。原文访问等原有实验继续引用旧证据，不覆盖。此为最小关键词检索与资料查询子技能，不是完整混合RAG/全部三技能。
真人交叉评审、换机复现及安全统一命令的执行结果独立记录，不能从自动验收推断完成。旧红项原样保留。
'''
    for name in ('security-precheck.md', 'risk-authz.md', 'lesson08-foundation.md'):
        path = Path('reports') / name
        text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
        if marker not in text:
            path.write_text(text + summary, encoding='utf-8-sig')
        print('Updated:', path)
    print('No peer-review signature, prior evidence or vulnerability baseline overwritten.')


if __name__ == '__main__':
    main()
