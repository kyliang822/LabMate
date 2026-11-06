# Lesson08 实现自审（AI自审，不是另一成员交叉评审）

基线：c1a456f23d6a4e4875ab5bd5c54c96de2a4cf31c。工作分支：work/lesson08-consumer-review。生成范围：新增消费者、查询/重试、版本迁移、Vue任务页、脚本、测试、规则及文档。真人复核人：未提供。

| 维度 | 方法/依据 | 结论 |
| --- | --- | --- |
| 需求覆盖 | 对照C01～C10、交接五步及课程七项 | 第四/五步代码已编写；31单元/入口测试通过；真实库、worker故障、真实嵌入未验收；配置写接口/技能日志仍缺 |
| 一致性 | 对照DATA-01/02/03、BE-02 | 保留queued/processing/ready/failed与task_id响应；旧async_tasks.material_id继续引用版本，不悄改旧字段意义 |
| 失败路径 | 测试解析、向量维度/数量/有限值、HTTP错误及无配置 | 单元测试已通过；DB失败/发布回滚测试已写，因缺库未运行；API只作文件预检 |
| 性能 | 检查有界读取、分批嵌入、列表上限与索引 | 嵌入批量32，读取20MiB+1，列表最多100；向量尚无ANN索引，当前不是完整检索服务；PDF解压在检查前可能消耗较大资源，保留风险 |
| 重复代码 | 检查认证/业务入口与消费者状态写入 | 身份在service.identity；查询/重试在queries；worker复用纯解析模块；未伪造另一套预约规则 |
| 漏洞风险 | 密钥/依赖扫描及未登录真实HTTP探测 | 六个入口均401；依赖红项未修复；跨范围授权需真实库；未测试注入素材 |
| 并发/事务/一致性 | 逐行看锁、事务、outbox和版本指针 | session lock限制同task并发；恢复争用同锁；新旧版本按版本号发布；真实数据库与崩溃实验仍阻塞 |

## 高风险四件事

| 用什么手段查 | 查了什么 | 规约判据 | 当前结果 |
| --- | --- | --- | --- |
| SQL与控制流逐行阅读 | 任务身份和资源归属 | SEC-02：按实验室+本人SQL过滤 | 实现存在；未登录入口实测401，跨实验室实测待DB |
| 控制流/真实DB测试设计 | 重复消费与卡住恢复 | DATA-02：结果唯一，不能覆盖活跃执行者 | 同一session锁，连接丢失不重连写回；丢失执行者同样消耗重试预算，避免崩溃循环；测试已写未运行 |
| 事务边界阅读 | 切片、ready与current_version发布 | DATA-02、BE-05：整体可见或整体回滚 | 同事务提交；注入审计失败的真实DB测试待运行 |
| 幂等摘要兼容核对 | 0002阶段同键重放 | BE-05：旧请求应返回原task_id | 新实现兼容旧摘要计算，不要求修改旧迁移 |

## 逐文件结论

“待修改”包含缺验收证据的阻塞，不能误读为允许合并；不以局部测试代替真实数据库与真人复核。

| 文件/同类文件 | 结论 | 依据及下一步 |
| --- | --- | --- |
| backend/app/main.py、async_tasks/queries.py、service.py、publisher.py | 待修改 | C03/C05真实DB证据未齐；接口入口6条401已通过 |
| migrations/0003_material_processing.sql | 待修改 | 需要新库/旧库实际迁移和恢复核验 |
| worker/tasks.py、processing.py、scripts/recover_tasks.py | 待修改 | 纯处理测试通过；并发/重投/真实provider和资源上限待验证 |
| scripts/seed_security.py、permission_probe.py、measure_submission.py | 待修改 | 匿名探测已运行；身份初始化/授权/P95需真实环境 |
| scripts/check_security.py、classify_advisories.py | 可用 | 已运行且记录非零失败；全历史/构建产物/本次API日志扫描与Python原始28条/去重14条依赖公告明细已留存；需真人复核范围 |
| tests/unit/test_material_processing.py、test_auth_boundaries.py | 可用 | 正常/失败/边界行为已执行；不宣称覆盖生产并发 |
| tests/integration/conftest.py、test_consumer_db.py、test_async_foundation.py | 待修改 | 缺真实PostgreSQL/pgvector环境，10项setup错误真实留存 |
| web/src/App.vue、main.ts、web构建与代理配置 | 待修改 | 类型/构建已过；未浏览器手动核查，不是完整产品UI |
| compose.yaml、Dockerfile、Dockerfile.test、Makefile、CI | 待修改 | 局部门禁已运行，Compose/CI尚未实际执行；全项目check保留阻塞 |
| AGENTS.md、模板、规约、README、runbook、课程报告和fixtures | 可用 | 内容与路径已核对；报告明确区分实际/计划/阻塞；真人复核未代签 |

## 仍需关注

- 当前task列表按时间过滤分页，同时间戳边界可能略过记录；接口仅作为最近任务列表，不声称完整游标遍历。后续应改用时间+ID复合游标。
- 正式密码登录、混合检索、技能、MCP、预约/工单及完整AI评测均未实现，不能据此发版。
- PostgreSQL旧数据卷跨镜像切换须先备份并验证，不直接以新镜像覆盖唯一生产副本。
- 依赖高危和日志字段不足按本课保留现象与书面处置，未提前修改。
