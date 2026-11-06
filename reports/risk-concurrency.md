# 高风险三查：并发

前置条件：真实PostgreSQL/pgvector、Redis、完整消费者与虚构资料。
用什么手段查：并发HTTP提交、同task_id重复消息、确认前杀worker及真实库约束测试。
查了什么：同键同内容复用任务；同键异内容409；切片(version_id,chunk_index)唯一；ready后重复执行不重写结果；恢复不抢活跃任务。
判据：一份有效结果、稳定摘要和出处；attempts可追踪；冲突没有额外副作用。不是要求broker物理消息恰好一次。
操作：apitest/cases/lesson08.md判据三；make test-async中的并发及消费者用例。
当前实际：已编写session锁、版本唯一约束及真实DB测试；31单元/入口测试通过；10个集成用例在setup因缺DATABASE_URL报错，原始记录evidence/integration-blocked.txt。真实Redis停启/崩溃尚未执行。
当前判定：阻塞/未测，不能填“并发安全已验收”。需补同任务响应、DB切片/审计行、摘要、attempts和故障时间线。

<!-- lesson08-local-evidence-v1 -->
更新时间：2026-11-06 14:45:17 +08:00
## 本机真实并发与重复投递更新

前置条件：真实API、PostgreSQL、Redis、publisher、worker及Embedding；虚构资料。
手段：两个HTTP线程通过Barrier同时提交同用户同键同内容；随后同键换内容；另对ready任务再次发送同task_id的真实Redis消息。
判据：同键同内容返回原task_id；异内容409；任务/资料版本/outbox/提交审计唯一；重复消费不改变切片和发布结果。
实际：两次202且同task_id，异内容409；四类记录各1。成功后重复投递attempts从3增至4，切片仍1份、摘要相同、ready审计仍1条。
结论：上述场景通过；处理中崩溃重投尚未执行，不能由此推断其通过。
证据：evidence/concurrent-submission.json、evidence/duplicate-delivery.json。
