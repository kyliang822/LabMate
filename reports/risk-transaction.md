# 高风险三查：事务

前置条件：独立真实库、Redis、publisher/worker，虚构资料。
用什么手段查：SQL事务边界阅读、故障注入、停止代理/消费者、恢复后核对数据库和文件引用。
查了什么：提交资料版本/任务/outbox/审计同事务；发布切片/ready/版本指针同事务；broker异常不标已发送；失败无可检索半成品。
判据：数据库变更整体提交或回滚；恢复后持久任务可被处理，无孤儿任务。发送成功但outbox事务未提交可能重复投递，结果幂等；不宣称exactly-once。
操作：apitest/cases/lesson08.md与test_outbox_rollback、test_store_audit_failure_rolls_back_publication。
当前实际：代码事务边界及测试已补；真实DB不可用，停代理/停worker实验未运行，不能报告成功。
已知边界：数据库提交结果不明的连接断开保留文件，可能出现不可检索孤立文件；文件系统不属于PostgreSQL事务，清理须备份并核对storage_key引用。
当前判定：阻塞/未测。待补每种故障下的资料/任务/outbox/审计数量、文件引用及恢复结果。

<!-- lesson08-local-evidence-v1 -->
更新时间：2026-11-06 14:45:17 +08:00
## 本机事务相关验证更新

手段：真实独立PostgreSQL集成测试；停止worker期间真实提交，恢复同一worker后核对同task_id。
实际：修正依赖后41项测试通过，含相关约束/事务用例。停止worker时202、queued、attempts=0；恢复后原task_id达到ready、attempts=1、error_code=null，无需重传。
证据：evidence/integration-after-dependency-fix.txt、evidence/worker-stop-before.json、evidence/worker-stop-after.json。
结论：测试及停启场景通过；尚须保留完整SQL/数据库关系核对来支持“无孤儿任务”的结论，不能只凭ready证明所有原始文件引用及所有事务故障场景无问题。至少一次消息投递不等于broker保证恰好一次投递。
