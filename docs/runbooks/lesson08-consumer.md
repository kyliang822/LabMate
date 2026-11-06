# Lesson08 运行与接续手册

当前环境只验证了局部代码和前端构建。以下Docker/真实库步骤供具有环境的成员执行，尚未在本次环境通过。

## 启动

1. 安装Docker Engine/Desktop及Compose v2，复制.env.example到.env，在本机填密码和真实嵌入配置（不上传密钥）。EMBEDDING_BASE_URL是HTTPS的/v1地址；服务须支持POST /embeddings，配置实际模型及维度。无配置会明确failed，不生成假向量。使用本地服务时先提供HTTPS入口。
2. 新空环境执行`docker compose up -d --build`；Web为http://localhost:8080，API仅绑定localhost:8000。当前ai-service/mcp仍未实现，不属于本次Compose服务。
3. 对已有PostgreSQL数据卷先备份，再在副本验证pgvector镜像与0003迁移兼容；不要直接切换唯一生产副本。执行两次`docker compose run --rm migrate`验证幂等。
4. `docker compose ps`，`docker compose exec redis redis-cli ping`。`/health/ready`仅检查API数据库，不表示worker/嵌入服务可用。
5. 一次性管理员演示令牌：`docker compose exec api python -m scripts.issue_demo_token`，仅在私密终端读取，不录屏/粘贴进报告。令牌只进页面内存，清除/刷新后消失；尚无完整密码登录。

## 身份与接口检测

```sh
# 在api容器私密路径创建2小时令牌；不把JSON拷进仓库或报告
docker compose exec api python -m scripts.seed_security
# 文件默认 /tmp/labmate-security-identities.json，权限0600；重跑须另选--output或清理已过期私密文件
# 容器内发起探测，--identities文件不会打印令牌
docker compose exec api python -m scripts.permission_probe --identities /tmp/labmate-security-identities.json --output /tmp/permission-probe.json
# 拷出结果JSON前先确认无凭据；不要拷出identities文件
```

probe使用Python标准库，可直接在api容器中执行；只输出状态与脱敏响应，不输出令牌。

六个受保护方法/路径见reports/security-precheck.md。只有匿名入口探测已在本次实际HTTP服务验证；其他权限与副作用必须用真实DB补证据。

## 单元、真实库与门禁

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix web
make check-local PYTHON=.venv/bin/python
# 必须指定独立labmate_test库；无数据库时明确失败，不跳过
make test-async PYTHON=.venv/bin/python
make check-security PYTHON=.venv/bin/python
```

Compose独立库测试：先以postgres管理员创建labmate_test，再`docker compose --profile test run --rm --build tests`。真实DB集成测试以可控provider替身验证事务规则，不能替代真实嵌入与Redis故障实验。make check保留剩余业务/AI未实现的阻塞，check-local不等于全项目通过。

## 失败、手动重试与恢复

- tasks/{id}按本人+实验室查询，列表最多100；管理员也不能跨实验室查看任务。
- POST tasks/{id}/retry：管理员本人任务、失败状态、Idempotency-Key必填；同键同任务重放不增加cycle，异任务冲突409。
- 应用死信在task_dead_letters，只含task_id/cycle/stage/error_code/时间；不是Redis原生DLQ。不将Celery结果后端当业务事实来源。
- 自动重试最多2次，由数据库outbox available_at控制2s/4s退避；永久错误直接failed。
- 操作员先`docker compose exec api python -m scripts.recover_tasks`看dry-run，再经核对执行同命令加`--apply`。默认只查看超过1200s的queued/processing；与worker争同一session锁，活跃执行者跳过。异常断开后不得用旧连接自动重连写结果。
- file+DB提交失败可能留下不可检索孤立文件；不自动删。清理先备份、查storage_key引用，保留审计与保留期决策。

## 三判据

见apitest/cases/lesson08.md。P95脚本为scripts.measure_submission，凭据从私密JSON读取，curl令牌走stdin，不进命令参数和证据。故障实验必须使用虚构资料与独立环境。
