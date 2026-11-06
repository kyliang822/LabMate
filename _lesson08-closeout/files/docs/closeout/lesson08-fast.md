# 第八课最短闭环

本补丁只补新增功能前置，不修复已留存的安全红项，不执行SEC-08，不代签真人。

## 一条命令

在Windows PowerShell、项目根目录执行：

`powershell -NoProfile -ExecutionPolicy Bypass -File .\Complete-Lesson08.ps1`

脚本会备份被替换源码到Git元数据目录，增量安装后构建api/migrate/web/tests，迁移并启动API/Web，创建虚构登录账号，运行真实HTTP/DB验收，将脱敏结果归档到reports/evidence/。旧.env、requirements、既有reports均不覆盖；所有旧迁移不改，只添加0004。worker沿用已有Embedding配置和队列，须可用。

初始化会重设固定虚构测试账号adminA/adminB/userA1/userA2/userB1密码并撤销其旧CLI令牌，新密码仅保存在api容器/tmp/lesson08-login.json（0600）。原有业务任务/切片不删除。不要上传、提交或发送该密码文件。

检查包括5个账号真实登录、错误密码401、A资料对A召回且对B空结果、真实配置写接口普通用户403且无副作用、管理员配置幂等、真实资料查询技能及日志/用量/耗时、跨实验室技能日志404。技能是有用的“授权设备资料查询”，直接返回原文与定位，没有LLM调用，0 tokens明确代表未调用LLM；不伪造DeepSeek用量。

最小检索为字面关键词，不冒充完整混合向量RAG；输入实验室身份不作为参数，SQL按已认证实验室和设备/通用资料以及current/ready/deleted范围过滤。项目完整问答/三技能/MCP仍未完成。本补丁不宣称已完成完整项目。

## 登录演示

访问http://localhost:8080，用初始化账号登录，选择虚构资料上传，界面显示202后对应任务的queued/processing/ready。短任务可能轮询跳过processing，可由started_at与finished_at核验，不伪造界面状态。
在本人私密终端用`docker compose exec api python -c "import json; from pathlib import Path; a=json.loads(Path('/tmp/lesson08-login.json').read_text())['actors']['adminA']; print(a['username']); print(a['password'])"`读取演示密码；不要在录屏、共享终端或报告显示密码。浏览器密码框输入后清空；令牌只存内存。

## 统一安全入口

先准备前端产物、真实运行日志及开发依赖，然后一条命令：

`.\.venv\Scripts\python.exe -m scripts.check_security`

Windows可直接运行，不要求make；同时覆盖SEC-05/06。新脚本修复UTF-8和npm.cmd定位；发现依赖红项非零正常，不吞掉失败。保留所有旧基线；运行新增功能后再归档这次扫描，不要求本课修到全绿。

## 真人最短复核

另一位组员必须独立执行下列至少两项，不得使用AI代签：
1. 登录自己的实验室B演示账号，调用GET /api/v1/search?q=<A验收资料的唯一词>，核对0条；其唯一词只在私密验收凭据文件外的结果中记录，可从验收证据task_id关联查询演示原文获得。
2. 以userA1调用PUT /api/v1/ai-config，核对403且配置及审计无变化。
3. 调用POST /api/v1/skills/material-guide，再GET /api/v1/skill-runs/{run_id}，核对操作人/技能/状态/耗时/用量；B身份读取该日志404。

更便捷：另一成员在独立环境运行同一验收命令，逐条保留输出，并在reports/review-01.md写清真实姓名、时间、提交号、环境、两条具体命令及结果。上面的“一键全部通过”不能自动充当另一人的签名。

## 状态边界

本环境可以验证静态、单元与Vue构建；真实数据库与用户机器实跑由脚本产生结果，未运行不能写成通过。若教师要求完整LLM技能而非资料检索子技能，需按要求继续集成真实LLM并记录实际tokens，本补丁不伪称已满足该额外口径。
