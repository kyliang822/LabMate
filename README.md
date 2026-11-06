# LabMate

基于知识库与 MCP 工具调用的实验室设备预约与故障报修助手。

## 当前状态

已编写Lesson08异步提交及消费者接续：版本化迁移、资料解析/切分/外部嵌入、原子发布、任务查询与重试、恢复命令和Vue任务演示页。已有31项单元/接口入口测试通过，前端类型与生产构建通过；真实PostgreSQL/pgvector、Redis故障、Compose、真实嵌入和真人交叉验收尚未完成，不能视为可发布。

七项安全自查按正式课程要求只记录现象，不提前修复（明文密钥例外）。当前依赖存在真实红项，原始报告保留。正式登录、预约、工单、完整检索/问答、技能/MCP仍未实现。

- [启动与消费者运行手册](docs/runbooks/lesson08-consumer.md)
- [原Lesson08交接](docs/runbooks/lesson08-foundation.md)
- [模块检查记录](reports/lesson08-foundation.md)
- [七项安全自查](reports/security-precheck.md)、[资产基线](reports/security-baseline.md)
- [自审](docs/reviews/lesson08-self-review.md)、[真人交叉评审待办](reports/review-01.md)

### 本模块快速开始

安装Docker/Compose，复制.env.example到.env并仅在本机填数据库密码和真实嵌入配置，运行`docker compose up -d --build`，访问http://localhost:8080。一次性演示令牌按runbook在私密终端签发；令牌只存页面内存。旧数据卷先备份，在副本核验0003迁移，不直接覆盖唯一数据。

本地开发检查：安装requirements-dev.txt与web锁定依赖后，`make check-local`运行静态、单元、前端类型/构建；`make test-async`明确要求真实独立PostgreSQL/pgvector测试库。`make check-security`至少覆盖全Git历史/实际构建产物/实际日志的密钥检测及Python/npm依赖审计，原始输出到reports/evidence/；发现与阻塞均返回非零。不要把局部通过写成完整make check通过。

## 项目目标与范围

面向设备使用者和实验室管理员，计划提供登录与权限管理、设备及资料管理、带出处的流式问答、设备预约、故障排查、确认后报修、工单跟踪、资料处理异步任务与操作审计。

初期限定一个实验室和少量典型设备，使用演示数据与允许使用的设备资料。不涉及真实硬件控制、自动维修或学校正式业务系统接入。

## 计划技术方案

- 前端：Vue 3、TypeScript、Element Plus，使用 SSE 展示流式回答。
- 业务后端：Python、FastAPI，统一校验身份、权限及业务约束。
- 数据与检索：PostgreSQL、pgvector，结合关键词和向量检索；原始文件持久化保存。
- AI 与工具：兼容模型接口、三项可配置技能、独立 MCP Server。
- 异步与部署：Redis、Celery、Docker Compose；使用 OpenSpec 管理需求与验收规约。

以上是选题方案，并非已安装或实现的依赖清单。本次正式异步演示页位于 `web/`，采用 Vue 3 + TypeScript；原 `frontend/` 的 TSX 文件仍为历史占位，不参与构建。完整业务前端后续统一迁入 Vue 实现。

## 目录导航

| 路径 | 用途与现状 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 仓库级开发规则与规范索引 |
| [docs/standards/](docs/standards/) | 八份开发规范，含检查判据 |
| [openspec/project.md](openspec/project.md) | 项目规约入口、范围与功能规约编写约定 |
| `web/`、`frontend/` | Vue任务页及构建；旧TSX仅历史占位 |
| `backend/` | 本次资料提交实现及其余业务占位 |
| `ai_service/` | 智能体、检索、提示词及技能占位 |
| `mcp_server/`、`worker/` | MCP仍占位；worker接续实现待真实链路验证 |
| `migrations/` | 0001历史占位、0002提交基础、0003版本/向量/重试模型 |
| `tests/` | 异步单元与真实库测试已编写；业务/E2E/AI多数仍占位 |
| `docs/runbooks/`、`docs/evaluations/`、`reports/` | 异步手册、自查/风险证据；完整部署和AI评测仍待补 |
| `compose.yaml`、`Makefile`、`.env.example` | 异步基础配置与局部检查，完整部署待补齐 |

## 开发流程与验证

1. 先阅读 [AGENTS.md](AGENTS.md) 与本次任务涉及的开发规范。
2. 在 `openspec/` 中补充功能场景、接口、权限、数据约束及验收标准，随后实现。
3. 同步补充对应测试、配置说明及验证证据，由另一成员交叉复核。
4. 按测试规范，后续须实现 `make check` 和 `make eval-live`。本次提供 `make check-async` 模块检查；`make check` 在模块检查后仍明确报出全项目门禁未实现并失败，`make eval-live` 尚未实现。启动步骤须在实际依赖与部署配置落地后补充。

真实密钥仅放在本地环境变量或被忽略的 `.env` 文件中；`.env.example` 只保存配置名称与占位值。

## 初始仓库基础检查（历史记录）

| 老师提出的检查项 | 修正前状态 | 本次处理 |
| --- | --- | --- |
| `.gitignore` | 已存在，包含基础忽略规则 | 保留并补充构建、测试和本地运行产物规则 |
| 根目录 README | 缺失 | 新增本文件 |
| 规范落入规则文件 | `AGENTS.md` 为空 | 写入常驻约束、开发流程和八份规范的适用索引 |
| 规约目录 | `openspec/` 已存在，但入口仅为占位 | 补充项目规约入口；具体功能规约仍需在实现前逐项编写 |

本轮在工作分支分别记录功能实现与安全自查本地提交，未推送、未合并、未创建验收标签。
