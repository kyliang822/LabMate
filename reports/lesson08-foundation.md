# Lesson08 本轮检查记录

原始基线c1a456f23d6a4e4875ab5bd5c54c96de2a4cf31c；功能提交号及文件指纹见evidence/version-manifest.json。当前实现仍在开发分支，未推送、合并或发布。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| Python静态检查 | 通过（最终输出见证据） | evidence/check-local.txt |
| 单元/接口入口 | 31 passed，1条已知Starlette/AnyIO弃用警告 | evidence/check-local.txt |
| Vue TypeScript/生产构建 | 通过 | evidence/check-local.txt |
| 临时Uvicorn匿名HTTP | 6个真实路由均401 | evidence/permission-probe.json及runtime-logs日志 |
| 真实PostgreSQL/pgvector集成 | 10 errors，均在setup因缺独立DATABASE_URL | evidence/integration-blocked.txt；没有跳过或替身冒充数据库 |
| 安全扫描/依赖审计 | 实际运行，依赖红项，门禁非零 | security-baseline.md及evidence/security-* |
| Compose、Redis停启/崩溃、P95、真实嵌入 | 未运行，环境/服务阻塞 | runbook与apitest复现步骤 |
| 真人交叉复核 | 未完成 | review-01.md |
| 完整make check / make eval-live | 完整业务/AI缺失，不能宣布通过；eval-live尚未实现 | 保留Makefile全项目阻塞 |

## 已编写交付

0003迁移、Celery消费者及处理模块、范围查询、失败重试/恢复、Vue任务页面、Compose接线；真实库测试和故障复现步骤；七类规则、七维模板、AI自审；六份固定报告、安全入口、问题集及仅备料的SEC-08素材。

## 真人接续顺序

1. 有Docker的机器按runbook启动，填真实嵌入配置；已有数据先备份并在副本迁移。
2. 跑独立真实库测试，执行停启/崩溃/P95实验并保存原始结果；出现失败先定位，不替换为单元通过。
3. 完成身份/数据初始化和权限副作用检查；对未实现的配置/技能/混合检索如实登记场景缺口。
4. 另一成员独立复现至少2项，填review-01；后续安全课再修复已保留的依赖红项。未满足全项目门禁不得合并为正式完成。

## 本机回归更新（2026-11-06）

本节更新此前“数据库集成测试因缺环境阻塞”的状态。

- 修正运行依赖：Celery 5.4.0、Kombu 5.4.2、redis-py 5.3.1、packaging 26.3。
- 重新构建测试镜像后，使用独立测试库执行单元与集成测试。
- 实际结果：41 passed，1 warning，耗时2.70秒。
- 警告为Starlette/AnyIO弃用提示，不影响此次测试通过。
- 原始输出：evidence/integration-after-dependency-fix.txt。
- 本结果不代替尚未完成的崩溃重投、完整安全自查和真人交叉评审。


<!-- closeout-evidence:4efb1502746524bdef9f14227fb52beb8e1b4e8414d08f55ffc7987cd4c09c4c -->
## 第八课新增功能真实验收：2026-11-06T16:08:21+08:00

手段：scripts.verify_lesson08_closeout，真实HTTP+PostgreSQL；具体身份、状态码、条数、run_id和日志字段见reports/evidence/lesson08-closeout-20261106-160723.json。源码指纹亦在原始报告。
查了什么：密码登录、授权关键词召回、实际AI配置写入口、资料查询子技能和日志回查。
判据/实际：A身份召回自身唯一标记资料，B使用者/管理员召回0；普通使用者修改真实配置403且配置/审计无变化；管理员配置幂等；技能调用及本人日志可查、跨实验室日志404。
用量口径：本技能直接检索授权原文，无LLM调用，日志显式记录llm_called=false、0tokens与真实召回数，不冒充DeepSeek调用用量。
结果：本次报告中19项全部green。原文访问等原有实验继续引用旧证据，不覆盖。此为最小关键词检索与资料查询子技能，不是完整混合RAG/全部三技能。
真人交叉评审、换机复现及安全统一命令的执行结果独立记录，不能从自动验收推断完成。旧红项原样保留。
