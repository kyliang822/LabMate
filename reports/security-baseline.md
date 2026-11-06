# 安全资产基线：课程SEC-05/06

本课只观察并登记处置，不提前升级修复。无真实密钥命中；若发现真实密钥，立即由所有者轮换并协调清理历史，不在本报告展示明文。

## 可重复入口

make check-security PYTHON=.venv/bin/python（需npm与开发依赖，先npm ci --prefix web及npm run build）。脚本以UTC时间戳生成reports/evidence/security-*-{secrets,pip-audit,npm-audit,summary}.json，不覆盖上一轮。非零退出保留；不以文件生成成功代替安全通过。

密钥检测器：detect-secrets 1.5.0，离线--no-verify，不向任何提供者发送候选值；扫描所有可达Git提交的完整文件快照、工作树、web/dist及reports/runtime-logs。工作树排除生成的reports/evidence以避免反馈，Git历史没有路径排除；二进制按扫描器规则处理。扫描能力有限，不声称0命中等于绝对无泄漏。

首轮security-20261106T033610Z：原始4提交+工作树候选0；当时构建/日志尚未齐，partial=true，exit=2。原始报告保留。最终补扫evidence/security-20261106T034904Z-secrets.json覆盖功能提交e358435的全部5个可达提交、工作树、web/dist和本次真实匿名API日志；候选0、partial=false、脚本exit=0。其他不存在的服务日志不宣称已覆盖。

完整make check-security实际运行：evidence/security-20261106T034522Z-summary.json，脚本exit=1，make返回2，原因是Python/npm依赖发现，原始命令输出见evidence/security-final-command.txt。最后只补扫秘密，不重复改写依赖基线。

## Python依赖基线（含开发工具）

pip-audit 2.10.1，扫描requirements-dev.txt及递归运行依赖。原始报告：evidence/security-20261106T033610Z-pip-audit.json；exit=1，28条原始记录/3个包。工具每条公告重复输出2次，按包/版本/公告ID去重后为14条；原始结果不删改。
严重性来源：GitHub Advisory官方API，逐条URL、CVSS和修复版本保存在evidence/python-advisory-severity.json，未知不会计成0。

| 包/版本 | 记录数 | 当前处置 |
| --- | --- | --- |
| python-multipart 0.0.20 | 6（原始12） | 本课保留原版本及基线；后续按每条修复版本升级，复测上传大小、格式、幂等及并发；不靠单一旧CVE补丁号宣称全修 |
| starlette 0.41.3（FastAPI传递依赖） | 7（原始14） | 后续联合升级兼容FastAPI/Starlette，不单改成不兼容范围；复测鉴权、multipart、错误契约和响应；当前禁止当正式发布依据 |
| pytest 8.3.4（开发依赖） | 1（原始2） | 后续升级开发测试工具并重跑；与运行依赖分开记录，但不从基线删掉以降低数量 |

去重后：高危6、严重0、中危5、低危3、未知0；原始输出对应12/0/10/6/0。计数为公告条数，不代表14个已确认可利用的应用漏洞；适用条件和修复版本逐条保留。本课红项为真实发现，书面登记不改变存在高危的事实。

## 前端依赖

原始：evidence/security-20261106T033610Z-npm-audit.json。npm audit：高危0、严重0、中危3、低危0；exit=1。固定web/package-lock.json。当前为Vue/Vite模块构建，不是完整产品前端。
处置：本课保留；后续逐项核对npm建议版本和工具链兼容，更新锁文件并重跑类型/生产构建及审计；不能运行npm audit fix --force后覆盖本次红项。

## 当前结论

SEC-06红项已保留，扫描门禁非零。密钥扫描按实际资产分范围陈述；真实数据库、worker、模型日志尚不存在，后续启动后继续归档并复扫。真人复核未完成，不能宣布本课安全自查全部完成。

交付前再次核查：reports/evidence/security-20261106T035022Z-secrets.json，包含自查记录在内的全部6个可达提交及当前工作树/构建/API日志，候选0、partial=false；额外检查工具修正了中文路径枚举，未改变依赖版本。

## 本机资产基线更新：2026-11-06 15:25:33 +08:00

### SEC-05 密钥扫描
本轮扫描4个可达历史提交及工作树、前端构建产物和运行日志。
候选0，未复核0，partial=False，脚本退出码0。
证据：evidence/security-20261106T071104Z-secrets.json。
本机修改尚未提交，最终提交后需再次扫描。

### SEC-06 依赖审计
Python原始28条记录，按包和公告ID去重14条。
已确认：严重@{critical=0; high=5; moderate=4; low=2; unknown=3}.critical、高危@{critical=0; high=5; moderate=4; low=2; unknown=3}.high、中危@{critical=0; high=5; moderate=4; low=2; unknown=3}.moderate、低危@{critical=0; high=5; moderate=4; low=2; unknown=3}.low；
严重性未知：3条。未知不计为低风险，尚不能证明其不含高危或严重公告。

前端：严重0、高危0、中危3、低危0。

原始证据：
- evidence/pip-audit-local.json
- evidence/npm-audit-local.json
- evidence/python-severity-20261106-151834.json

处置登记：
1. 本课保留真实红项，不提前自动升级修复。
2. 未知公告后续按报告中的公告ID核实官方严重性，保留当前未知记录。
3. 后续分别处理multipart、FastAPI/Starlette兼容升级、pytest及前端工具链问题，并执行回归。
4. 当前不作为安全发布通过依据；具体修复负责人和时间由小组认领。

## 功能提交后的密钥复扫

- 被验证源码提交：65c0c0e39012eef88949e3ca692eaa37ac5d6096。
- 扫描时间：2026-11-06 07:42:55 UTC。
- 扫描脚本退出码：0。
- 详细结果：evidence/security-20261106T074255Z-secrets.json。
- 扫描时工作树非干净，具体范围以详细结果为准。
- 本记录仅证明本轮密钥扫描完成，不代表依赖无漏洞或整课验收通过。
