# 第八课真实环境复现步骤（尚未执行）

前置：独立演示环境、虚构身份/资料、真实PostgreSQL/pgvector和Redis、真实嵌入配置；另一成员复核。以下命令从仓库根执行；只在私密终端处理令牌，不记录明文。身份文件由scripts.seed_security创建，可在api容器内/tmp保存。

## 判据一：快速提交

1. 正常启动worker和publisher。确保嵌入提供者可用，上传无敏感资料。
2. 在具有curl和项目Python环境的本机，以私密身份文件运行：

```sh
python -m scripts.measure_submission --identities /tmp/labmate-security-identities.json --file fixtures/security/demo-material-A.txt
```

3. 原始20次time_total与task_id保存在reports/evidence/submission-timings.json；排序第19个作为P95。查询这些task_id的started_at/finished_at，记录处理时间并比较。没有20次202不计算P95。不编造同步改造前耗时。

## 判据二：停worker仍能持久提交，恢复自动完成

1. `docker compose stop worker`，publisher保持运行。提交资料保存返回202/task_id，不要二次上传。
2. GET tasks/{id}查queued；核对DB任务、资料版本、outbox、审计及原始文件引用。
3. `docker compose start worker`；同task_id最终ready，记录每次查询及切片摘要。
4. 另测停Redis/publisher时提交：应仍202和未发布outbox；恢复后可处理。停止消费者与停止代理是两种故障，不能混写证据。

## 判据三：并发和重投只有一份有效结果

1. 同一用户、同键同文件同时发两次提交。两次202且task_id相同；同键不同内容409。核对只有一任务、资料版本与提交审计。
2. 处理期间在完成确认前杀worker进程，例如`docker compose kill -s SIGKILL worker`，恢复worker。记录杀死时stage、重投等待和attempts；Redis visibility_timeout设为1200s，强杀后可能需要等待或执行经核对的DB恢复，不可宣称立即重投。
3. 重投同一个Celery task_id：`docker compose exec api python -m scripts.redeliver_task <task_id>`（仅独立测试环境）。重复成功消息应只增加领取审计，不重新生成结果。
4. 按版本核对chunk_index唯一、切片总数、内容摘要、current_version和ready状态，不只检查返回码。

## 事务与恢复

- 跑真实库test_store_audit_failure_rolls_back_publication，核对注入审计失败时无切片、无ready指针。
- 重复迁移两次；测试test_concurrent_submission_and_constraints，验证数据库唯一约束本身生效。
- 恢复先dry-run：`docker compose exec api python -m scripts.recover_tasks`；确认后加--apply。活跃worker必须显示active_skipped。
- 保存原始响应与数据库查询输出到reports/evidence/，链接到risk-concurrency.md、risk-transaction.md。上述尚未执行的结果不得预填。
