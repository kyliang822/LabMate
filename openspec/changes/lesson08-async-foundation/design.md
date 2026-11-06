# 设计

FastAPI → PostgreSQL 同一事务写资料版本、任务、outbox、审计 → 独立 publisher → Redis AOF → 队友 Celery worker。

持久化任务是事实来源。请求不依赖 Redis 在线；publisher 用 SELECT FOR UPDATE SKIP LOCKED 竞争发送，发送成功后标记。发送成功但事务未提交可能重复投递，队友必须幂等消费，不宣称 exactly-once。

仅上传 UTF-8 TXT/Markdown 或 PDF（<=20 MiB）。当前入口只做格式/编码/文件头预检，PDF 损坏/无文本由消费者解析时判失败，扫描件不做 OCR。随机存储名，非公开目录；客户端文件名不作路径。失败请求清理新文件。相同用户、操作、幂等键同摘要返回旧任务，异摘要 409。旧任务重放不新建记录。

身份采用数据库维护的短期 opaque Bearer Token SHA256 摘要，检查有效期/用户启用状态；不接受客户端 user_id/lab_id/role。此为独立开发入口，尚未实现完整密码登录；管理员通过 CLI 发放令牌，服务中不保存明文。管理员仅上传本实验室资料。不存在设备与跨实验室设备均为 404。

任务 queued/processing/ready/failed；阶段 queued/parse/chunk/embed/store；结果切换与重试由队友实现。Celery task 名 labmate.process_material，参数只有 task_id，worker 从 DB 读取版本与存储键并重验资料状态。attempts 是消费者领取次数，重复消息也应记录，成功结果必须按版本唯一。

Compose 本次仅 postgres/redis/migrate/api/publisher，不伪造其他未实现服务；仅 API 绑定 127.0.0.1。正式部署仍须补全 OPS-01 的 web、worker、AI、MCP。
