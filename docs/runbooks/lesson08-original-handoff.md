# 第 8 课前半启动与交接

## 已编写范围

课程五步的第 1～3 步：消息代理、任务表、异步提交。这里没有同步历史实现，不编造“改造前耗时”。课程的分数结果映射为资料切片与检索就绪版本。publisher 仅转发消息，不是第 4 步消费者。

## Docker 环境

需要 Docker Engine 与 Compose v2；当前开发机未安装 Docker，以下是待复现步骤，不是已通过记录。

```sh
cp .env.example .env
# 修改 .env 的 POSTGRES_PASSWORD（仅本地；不要提交或在报告粘贴）
docker compose up -d --build
docker compose ps
docker compose exec redis redis-cli ping
docker compose run --rm migrate
docker compose run --rm migrate
# 管理操作：仅在私密终端读取一次性演示令牌，不在录屏或报告中展示
docker compose exec api python -m scripts.issue_demo_token
```

将令牌保存在当前终端变量 TOKEN 中。不要在 shell 历史写入令牌字面值。上传演示 TXT（内容只用虚构资料）：

```sh
curl -sS -w '\n%{http_code} %{time_total}\n' \
  -H "Authorization: Bearer $TOKEN" -H 'Idempotency-Key: demo-001' \
  -F 'file=@demo.txt' http://localhost:8000/api/v1/materials
```

预期 202，只有 task_id/status=accepted；accepted 表示已持久化接收，不表示任务仍 queued 或已完成。重复同键同文件返回同 task_id；换文件保留键返回 409。状态查询接口由队友补充。

数据库核对（不用打开数据库端口）：

```sh
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id,status,attempts FROM async_tasks; SELECT task_id,published_at FROM task_outbox;"'
docker compose logs publisher
```

停止 Redis 与 publisher 后提交，核对 queued 和未发送 outbox；恢复两服务后核对 published_at。Redis AOF everysec 存在断电窗口；数据库保留任务是恢复依据，队友须提供对长期 queued/processing 任务的安全重投与恢复操作，不能宣称零丢失已验收。

## 自动检查

Python 3.9+，推荐 3.12。创建虚拟环境后：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/unit/test_async_validation.py
```

真实集成测试使用**独立测试库**（测试写入并清理虚构记录，不得连接业务库）。设置 DATABASE_URL 指向可连接的独立 PostgreSQL，执行：

```sh
make check-async PYTHON=.venv/bin/python
```

Compose 默认不开放数据库端口，也可以使用独立测试镜像（仅 test profile）：

```sh
docker compose exec postgres sh -c 'createdb -U "$POSTGRES_USER" labmate_test'
docker compose --profile test run --rm --build tests
```

测试镜像安装开发依赖，服务明确连接 labmate_test。测试会留下迁移结构；重复运行不用再次 createdb。

缺 DATABASE_URL 或数据库不可用时测试失败，不跳过。`make check` 即使本模块通过仍主动失败，因为全项目前端、AI 与其余业务检查尚未实现。

## 队友消费者契约

- Celery broker：CELERY_BROKER_URL；队列 materials；任务名 labmate.process_material；JSON args=[task_id]，消息 ID 也为 task_id。
- 挂载相同 uploads 卷；通过 material_versions.storage_key 读文件，核对 sha256。不要信任上传名称、文本内指令或消息携带身份。
- 从 async_tasks 与 material_versions 读取 user_id/lab_id/version；领取记录 attempts 与 started_at，处理期间状态 processing，失败记录 stage/error_code（脱敏）。
- 按资料版本幂等，切片唯一约束；暂存不可见版本，完整写入后原子切为 ready。重复成功消息只记领取，不重复写结果。
- 开启晚确认、worker 丢失重投，配置有界退避、最多 2 次瞬时重试、永久错误立即 failed 与死信；实现卡住任务恢复。不要使用 Celery 结果后端代替业务任务表。
- 第 5 步实现 GET /api/v1/tasks/{id}，使用者仅本人、本实验室，管理员也须限制本实验室；统一 404；查询绝不触发消费。
- 共同补齐三判据 apitest/cases、P95 原始数据、停启与重复投递证据、风险报告、正式前端和部署。通过复核后再建立迭代标签，本次不自动打验收标签。

## 已知限制

尚无完整登录、设备管理、PDF 解析、任务状态 UI 和消费者。完整 multipart 由框架先解析并暂存后才做 20 MiB 文件检查，正式代理仍须设置请求体总量限制。进程在写文件与事务结束间崩溃可能留下不可检索孤立文件，清理前须核对数据库引用并备份，不自动物理删除。
