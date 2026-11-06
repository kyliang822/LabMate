# 第八课安全自查（部分已运行，其余阻塞）

日期：2026-11-06。基线提交：c1a456f23d6a4e4875ab5bd5c54c96de2a4cf31c；检测对象为本工作分支，最终功能提交号见evidence/version-manifest.json。执行者：Codex（自动化执行）；真人负责人/复核人：待组员填写，未代签。

## 环境与身份

Python 3.12.14；原依赖保持，新增PDF解析/扫描依赖；npm锁文件固定本次前端依赖。Docker、PostgreSQL、Redis服务不具备，真实嵌入配置未提供。已在本机临时Uvicorn服务执行匿名HTTP探测，未从零启动完整Compose。

scripts.seed_security提供实验室A/B、adminA/adminB、userA1/userA2/userB1和虚构设备初始化；令牌2小时、写私密0600文件不进报告。该脚本未在本环境实际执行；正式密码登录仍未实现，不能写“账号均已能登录”。身份文件不归档。

## 受保护接口（真实已注册）

| 方法 | 路径 | 授权边界 | 写入 |
| --- | --- | --- | --- |
| POST | /api/v1/materials | 本实验室管理员；上传/新增版本 | 是 |
| GET | /api/v1/materials | 当前实验室ready资料 | 否 |
| GET | /api/v1/tasks | 本实验室且本人 | 否 |
| GET | /api/v1/tasks/{task_id} | 本实验室且本人 | 否 |
| POST | /api/v1/tasks/{task_id}/retry | 本实验室管理员且本人失败任务 | 是 |
| GET | /api/v1/materials/{material_id}/versions/{version}/original | 当前实验室、ready版本，历史/停用标记 | 否 |

写入类清单为上述上传、重试；CLI种子/恢复为受信任运维操作，另行审计。预约/报修/技能配置接口仍未实现，未列为可测接口。

## SEC-01 未登录访问受保护接口

前置条件：启动临时Uvicorn API，无DB配置；不带Token。
操作/手段：python -m scripts.permission_probe --base-url http://127.0.0.1:18009；逐个HTTP请求上表六个接口。
判据/可观测结果：全部401，返回统一错误体，不进入数据库业务。
当前实际：6/6返回401，code均为unauthorized；request_id可关联。原始响应见evidence/permission-probe.json，服务日志在runtime-logs/api-anonymous-probe.log。
当前判定：绿（限已测匿名入口；无DB环境不能替代数据库副作用检查）。

## SEC-02 跨实验室访问与检索

前置条件：虚构A/B资料、A1/B1身份、真实DB；完整检索接口。
操作/手段：按risk-authz.md复现任务跨所有者、原文跨实验室和检索隔离；核对响应和DB。
判据：单项统一404，跨范围检索空结果，模型上下文不含禁用来源。
当前实际：SQL范围已静态核对，未运行真实库；原文/任务实现新增但未集成验收；完整混合检索仍占位。
当前判定：阻塞/未测（本项未完成，不能计作绿或真实红）。

## SEC-03 使用者修改技能与提示词

前置条件：实际存在的配置写接口、普通使用者。
操作/手段：先检查OpenAPI和代码入口；接口存在后携使用者令牌调用并核对被修改记录。
判据：403，无配置写入。
当前实际：本项目无技能/提示词/助手配置HTTP接口；不能用404冒充权限检查通过。
当前判定：阻塞（需按本项目产品范围明确场景适用性，未为凑数新增假接口）。

## SEC-04 绕过技能直接写入

前置条件：普通使用者令牌、真实DB、管理员上传接口；确认绕过另需预约/报修/MCP。
操作/手段：permission_probe加--identities /tmp/labmate-security-identities.json，直接POST /materials；执行前后核对该用户任务/资料/审计数量。
判据：403且无新增业务行；业务确认绕过必须无未确认记录。
当前实际：探测脚本已写；因无DB身份无法执行带身份调用。预约/报修确认链路尚未实现。
当前判定：阻塞/未测，不能拿SEC-01匿名401替代本项。

## SEC-05 密钥明文扫描

前置条件：完整Git历史、本次web构建产物、本次实际API运行日志。
操作：make check-security（detect-secrets离线扫描，不向服务验证候选值）；详见security-baseline.md。
判据：已覆盖资产内无真实密钥；命中立即由所有者轮换并协调清理历史，报告不能抄密钥。
当前实际：首轮扫描4个原始提交及工作树，候选0；当时构建/日志尚未齐备，报告明确partial。最终补扫见security-baseline.md。当前无真实技能/worker日志资产，不宣称扫描过不存在的运行数据。
当前判定：绿（已可用资产：全部5个可达提交、工作树、实际构建产物及本次API日志，最终候选0）；未运行服务没有日志资产，不能声称已覆盖其未来日志。

## SEC-06 依赖漏洞基线

前置条件：requirements-dev.txt与web/package-lock.json、可用审计源。
操作：make check-security，另用scripts.classify_advisories查询官方GitHub Advisory严重性。
判据：高危清零或逐条书面登记处置。
当前实际：Python3个包原始28条记录含重复，去重14条公告：高危6、严重0、中危5、低危3、未知0；前端3条中危，高危0、严重0。完整明细与处置见security-baseline.md。
当前判定：红（存在真实高危基线，已登记后续升级/兼容验证方案；本课未提前修复）。非零退出码保留，不将登记处置伪装为无漏洞。

## SEC-07 技能日志追溯

前置条件：至少一次真实技能调用。
操作：核对ai_service/agent/assistant.py、skills及现有task_audit字段，运行技能后按关联ID回查。
判据：操作人、技能标识、结果、耗时、用量可定位。
当前实际：技能仍占位，没有可运行的真实技能调用；task_audit只有actor_id/action/task_id/request_id/created_at等，不是技能日志。
当前判定：阻塞（未执行调用，不能编造技能日志）。
字段缺口/后续层次：AI技能执行层补skill_id/version、result、duration_ms、token_usage，关联可信actor_id和trace_id；API/MCP传播关联ID；本课仅记录缺口。

## SEC-08 选做备料

fixtures/security/sec08-materials/内有1份虚构恶意文档及3条诱导问题。仅写文件，未上传、检索或发送模型测试。

## 提交与真人复核

本次自查独立提交；真实成员需按照reports/review-01.md至少复现2条并填署名与判定，当前不能宣称整课完成。

<!-- lesson08-local-evidence-v1 -->
更新时间：2026-11-06 14:45:17 +08:00
## 本机实测补充（以对应原始证据为准）

SEC-01：绿。匿名请求6个真实接口均401。依据：evidence/permission-probe-deployed.json。
SEC-02：部分完成。任务所有者可查，其他所有者与跨实验室身份404，且与不存在资源响应一致；同实验室原文访问200、跨实验室使用者及管理员404。跨实验室检索仍未实现/未测，整项不能标绿。
SEC-03：未完成。缺真实配置写入口，不能把不存在接口404当作403权限通过。
SEC-04：资料上传场景绿。普通使用者直调上传403，materials/material_versions/async_tasks/task_audit四项计数均0。工具及预约/报修确认绕过未覆盖。
SEC-05/06：旧扫描与依赖基线保留；本机最新Git历史、构建、日志及修正后的依赖仍待重新扫描，不沿用旧计数声称当前全通过。
SEC-07：未完成。技能调用未实现，尚无真实技能日志回查；字段缺口仍按原报告登记，不用worker日志替代。

证据：evidence/permission-probe-deployed.json、permission-db-side-effects.txt、task-scope-probe.json、task-404-comparison.json、original-access-probe.json。


<!-- closeout-evidence:4efb1502746524bdef9f14227fb52beb8e1b4e8414d08f55ffc7987cd4c09c4c -->
## 第八课新增功能真实验收：2026-11-06T16:08:21+08:00

手段：scripts.verify_lesson08_closeout，真实HTTP+PostgreSQL；具体身份、状态码、条数、run_id和日志字段见reports/evidence/lesson08-closeout-20261106-160723.json。源码指纹亦在原始报告。
查了什么：密码登录、授权关键词召回、实际AI配置写入口、资料查询子技能和日志回查。
判据/实际：A身份召回自身唯一标记资料，B使用者/管理员召回0；普通使用者修改真实配置403且配置/审计无变化；管理员配置幂等；技能调用及本人日志可查、跨实验室日志404。
用量口径：本技能直接检索授权原文，无LLM调用，日志显式记录llm_called=false、0tokens与真实召回数，不冒充DeepSeek调用用量。
结果：本次报告中19项全部green。原文访问等原有实验继续引用旧证据，不覆盖。此为最小关键词检索与资料查询子技能，不是完整混合RAG/全部三技能。
真人交叉评审、换机复现及安全统一命令的执行结果独立记录，不能从自动验收推断完成。旧红项原样保留。
