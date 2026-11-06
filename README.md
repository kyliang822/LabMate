# LabMate

基于知识库与 MCP 工具调用的实验室设备预约与故障报修助手。

## 当前状态

已编写第 8 课前半（五步中的第 1～3 步）的 Redis/PostgreSQL 配置、版本化迁移、鉴权资料提交 API 和事务发件箱转发器。消费者、状态查询与重试留给下一成员；其余业务仍是框架占位。当前环境缺 Docker，未验证容器或真实数据库链路，不能视为已部署或已验收。

启动、分工和消费者接入见 [第 8 课交接说明](docs/runbooks/lesson08-foundation.md)，规约见 [本次变更](openspec/changes/lesson08-async-foundation/proposal.md)，验证结果见 [检查记录](reports/lesson08-foundation.md)。

## 项目目标与范围

面向设备使用者和实验室管理员，计划提供登录与权限管理、设备及资料管理、带出处的流式问答、设备预约、故障排查、确认后报修、工单跟踪、资料处理异步任务与操作审计。

初期限定一个实验室和少量典型设备，使用演示数据与允许使用的设备资料。不涉及真实硬件控制、自动维修或学校正式业务系统接入。

## 计划技术方案

- 前端：Vue 3、TypeScript、Element Plus，使用 SSE 展示流式回答。
- 业务后端：Python、FastAPI，统一校验身份、权限及业务约束。
- 数据与检索：PostgreSQL、pgvector，结合关键词和向量检索；原始文件持久化保存。
- AI 与工具：兼容模型接口、三项可配置技能、独立 MCP Server。
- 异步与部署：Redis、Celery、Docker Compose；使用 OpenSpec 管理需求与验收规约。

以上是选题方案，并非已安装或实现的依赖清单。现有前端 `.tsx` 占位文件与 Vue 3 方案不一致，正式实现前须在规约中确定技术栈，再统一文件格式与构建配置。

## 目录导航

| 路径 | 用途与现状 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 仓库级开发规则与规范索引 |
| [docs/standards/](docs/standards/) | 八份开发规范，含检查判据 |
| [openspec/project.md](openspec/project.md) | 项目规约入口、范围与功能规约编写约定 |
| `frontend/` | 前端页面、组件与 API 调用占位 |
| `backend/` | 本次资料提交实现及其余业务占位 |
| `ai_service/` | 智能体、检索、提示词及技能占位 |
| `mcp_server/`、`worker/` | MCP 工具及异步任务占位 |
| `migrations/` | 0001 为历史占位，0002 为异步基础迁移 |
| `tests/` | 单元、集成、端到端及 AI 评测占位 |
| `docs/runbooks/`、`docs/evaluations/`、`reports/` | 部署说明、评测说明及验收报告占位 |
| `compose.yaml`、`Makefile`、`.env.example` | 异步基础配置与局部检查，完整部署待补齐 |

## 开发流程与验证

1. 先阅读 [AGENTS.md](AGENTS.md) 与本次任务涉及的开发规范。
2. 在 `openspec/` 中补充功能场景、接口、权限、数据约束及验收标准，随后实现。
3. 同步补充对应测试、配置说明及验证证据，由另一成员交叉复核。
4. 按测试规范，后续须实现 `make check` 和 `make eval-live`。本次提供 `make check-async` 模块检查；`make check` 在模块检查后仍明确报出全项目门禁未实现并失败，`make eval-live` 尚未实现。启动步骤须在实际依赖与部署配置落地后补充。

真实密钥仅放在本地环境变量或被忽略的 `.env` 文件中；`.env.example` 只保存配置名称与占位值。

## 本次仓库基础检查

| 老师提出的检查项 | 修正前状态 | 本次处理 |
| --- | --- | --- |
| `.gitignore` | 已存在，包含基础忽略规则 | 保留并补充构建、测试和本地运行产物规则 |
| 根目录 README | 缺失 | 新增本文件 |
| 规范落入规则文件 | `AGENTS.md` 为空 | 写入常驻约束、开发流程和八份规范的适用索引 |
| 规约目录 | `openspec/` 已存在，但入口仅为占位 | 补充项目规约入口；具体功能规约仍需在实现前逐项编写 |

当前目录已有 Git 元数据；本次不创建提交、验收标签或合并。
