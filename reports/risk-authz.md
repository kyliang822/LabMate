# 高风险三查：权限（课程SEC-02）

当前：阻塞/未测；不作红绿结论。无真实数据库及可用身份，完整混合检索尚未实现。

前置条件：按runbook启动，scripts.seed_security创建A/B、adminA、A1/A2、B1；分别用管理员上传demo-material-A/B.txt并等待ready。记录返回task_id及任务查询返回的逻辑material_id/version_id。凭据仅在私密JSON，不写本报告。

用什么手段查：HTTP访问+真实SQL副作用/数据范围核对；规约为SEC-02、BE-02、AI-01。
查了什么：
1. A1/B1分别访问adminA任务；跨所有者均404。adminA换lab_id不来自客户端可控字段；adminB访问adminA任务也404。
2. B1请求A原文路径/api/v1/materials/{A_material_id}/versions/1/original，与随机不存在UUID比较：除request_id外响应一致404。
3. B1调用GET /materials，只含B的ready资料；未ready资料不在列表。
4. 完整检索实现后B身份检索A特有词，结果0；核对候选召回、模型上下文、出处均无A来源，不能仅在模型输出时过滤。

可复测的基础自动测试：make test-async，含test_scope_and_manual_retry_are_real_db。实际HTTP复测用scripts.permission_probe和私密身份文件；该脚本仅自动化匿名/直调上传，跨原文和检索需按上述具体路径补场景，不宣称脚本已覆盖全部权限。

判据：统一404、列表无禁用来源、跨范围召回为空、业务数据不改变。
结果：只有6个匿名入口401已实际执行（见permission-probe.json），不能据此判本项通过。待真人环境补具体ID、命令、原始响应、返回条数、数据库结果与判定。

<!-- lesson08-local-evidence-v1 -->
更新时间：2026-11-06 14:45:17 +08:00
## 本机权限复测更新

前置条件：Docker真实API/PostgreSQL；虚构实验室A/B，adminA/adminB、userA1/userA2/userB1；CLI短期令牌（不是正式密码登录）。
手段：真实HTTP请求与SQL核对；命令按原实验脚本复现，具体身份、路径、资源ID及原始响应保存在下列证据。
查了什么：任务所有者范围、实验室范围、原文权限及404存在性一致性。
判据：本人任务200；非所有者/跨实验室任务404；本实验室就绪原文可访问，跨实验室原文404；不存在与越权响应除request_id外一致。
结果：上述已测场景全部符合；跨实验室检索未完成，不能将整个SEC-02标为通过。
证据：evidence/task-scope-probe.json、evidence/task-404-comparison.json、evidence/original-access-probe.json。
