$ErrorActionPreference = 'Stop'
if (-not (Test-Path 'compose.yaml')) { throw 'Run this script from the LabMate repository root.' }
$root = 'reports/evidence'
function Read-Evidence($name) {
    $path = Join-Path $root $name
    if (-not (Test-Path $path)) { throw "Missing evidence: $path. Restore the real output; do not invent results." }
    $parsed = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
    # Explicitly emit each array element for Windows PowerShell 5.1 compatibility.
    foreach ($item in $parsed) {
        Write-Output $item
    }
}
# Validate all evidence before changing any report.
$permission = @(Read-Evidence 'permission-probe-deployed.json')
$scope = @(Read-Evidence 'task-scope-probe.json')
$comparison = @(Read-Evidence 'task-404-comparison.json')
$original = @(Read-Evidence 'original-access-probe.json')
$concurrent = Read-Evidence 'concurrent-submission.json'
$duplicate = Read-Evidence 'duplicate-delivery.json'
$before = Read-Evidence 'worker-stop-before.json'
$after = Read-Evidence 'worker-stop-after.json'
$timing = Read-Evidence 'submission-p95.json'
$processing = Read-Evidence 'submission-processing-comparison.json'
$testPath = Join-Path $root 'integration-after-dependency-fix.txt'
if (-not (Test-Path $testPath)) { throw "Missing evidence: $testPath" }
if ((Get-Content -Raw $testPath) -notmatch '41 passed') { throw 'Expected regression result not found; inspect actual test output.' }
if ($permission.Count -ne 7 -or @($permission | Where-Object { $_.result -ne 'green' }).Count) { throw 'Permission evidence is incomplete or not green.' }
if ($scope.Count -ne 6 -or @($scope | Select-Object -Skip 1 | Where-Object { $_.result -ne 'green' }).Count) { throw 'Task scope evidence needs inspection.' }
if ($comparison.Count -ne 2 -or @($comparison | Where-Object { $_.result -ne 'green' }).Count) { throw '404 comparison needs inspection.' }
if ($original.Count -ne 3 -or @($original | Where-Object { $_.result -ne 'green' }).Count) { throw 'Original access evidence needs inspection.' }
if ($concurrent.result -ne 'green' -or $duplicate.result -ne 'green') { throw 'Concurrency evidence is not green.' }
if ($before.task.status -ne 'queued' -or $before.task.attempts -ne 0 -or $after.status -ne 'ready' -or $before.task.task_id -ne $after.task_id) { throw 'Worker restart evidence needs inspection.' }
if (-not $timing.all_20_accepted -or -not $processing.summary.all_20_ready) { throw 'Performance experiment is incomplete.' }
$sidePath = Join-Path $root 'permission-db-side-effects.txt'
if (-not (Test-Path $sidePath)) { throw "Missing evidence: $sidePath" }
$side = Get-Content -Raw $sidePath
foreach ($table in @('materials','material_versions','async_tasks','task_audit')) {
    if ($side -notmatch "(?m)^${table}:\s*0\s*$") { throw "Database side-effect evidence missing zero count: $table" }
}
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
$marker = '<!-- lesson08-local-evidence-v1 -->'
$updates = @{}
$updates['reports/security-precheck.md'] = @'
## 本机实测补充（以对应原始证据为准）

SEC-01：绿。匿名请求6个真实接口均401。依据：evidence/permission-probe-deployed.json。
SEC-02：部分完成。任务所有者可查，其他所有者与跨实验室身份404，且与不存在资源响应一致；同实验室原文访问200、跨实验室使用者及管理员404。跨实验室检索仍未实现/未测，整项不能标绿。
SEC-03：未完成。缺真实配置写入口，不能把不存在接口404当作403权限通过。
SEC-04：资料上传场景绿。普通使用者直调上传403，materials/material_versions/async_tasks/task_audit四项计数均0。工具及预约/报修确认绕过未覆盖。
SEC-05/06：旧扫描与依赖基线保留；本机最新Git历史、构建、日志及修正后的依赖仍待重新扫描，不沿用旧计数声称当前全通过。
SEC-07：未完成。技能调用未实现，尚无真实技能日志回查；字段缺口仍按原报告登记，不用worker日志替代。

证据：evidence/permission-probe-deployed.json、permission-db-side-effects.txt、task-scope-probe.json、task-404-comparison.json、original-access-probe.json。
'@
$updates['reports/risk-authz.md'] = @'
## 本机权限复测更新

前置条件：Docker真实API/PostgreSQL；虚构实验室A/B，adminA/adminB、userA1/userA2/userB1；CLI短期令牌（不是正式密码登录）。
手段：真实HTTP请求与SQL核对；命令按原实验脚本复现，具体身份、路径、资源ID及原始响应保存在下列证据。
查了什么：任务所有者范围、实验室范围、原文权限及404存在性一致性。
判据：本人任务200；非所有者/跨实验室任务404；本实验室就绪原文可访问，跨实验室原文404；不存在与越权响应除request_id外一致。
结果：上述已测场景全部符合；跨实验室检索未完成，不能将整个SEC-02标为通过。
证据：evidence/task-scope-probe.json、evidence/task-404-comparison.json、evidence/original-access-probe.json。
'@
$updates['reports/risk-concurrency.md'] = @'
## 本机真实并发与重复投递更新

前置条件：真实API、PostgreSQL、Redis、publisher、worker及Embedding；虚构资料。
手段：两个HTTP线程通过Barrier同时提交同用户同键同内容；随后同键换内容；另对ready任务再次发送同task_id的真实Redis消息。
判据：同键同内容返回原task_id；异内容409；任务/资料版本/outbox/提交审计唯一；重复消费不改变切片和发布结果。
实际：两次202且同task_id，异内容409；四类记录各1。成功后重复投递attempts从3增至4，切片仍1份、摘要相同、ready审计仍1条。
结论：上述场景通过；处理中崩溃重投尚未执行，不能由此推断其通过。
证据：evidence/concurrent-submission.json、evidence/duplicate-delivery.json。
'@
$updates['reports/risk-transaction.md'] = @'
## 本机事务相关验证更新

手段：真实独立PostgreSQL集成测试；停止worker期间真实提交，恢复同一worker后核对同task_id。
实际：修正依赖后41项测试通过，含相关约束/事务用例。停止worker时202、queued、attempts=0；恢复后原task_id达到ready、attempts=1、error_code=null，无需重传。
证据：evidence/integration-after-dependency-fix.txt、evidence/worker-stop-before.json、evidence/worker-stop-after.json。
结论：测试及停启场景通过；尚须保留完整SQL/数据库关系核对来支持“无孤儿任务”的结论，不能只凭ready证明所有原始文件引用及所有事务故障场景无问题。至少一次消息投递不等于broker保证恰好一次投递。
'@
foreach ($path in $updates.Keys) {
    if (-not (Test-Path $path)) { throw "Missing required report: $path" }
}
foreach ($path in $updates.Keys) {
    $existing = Get-Content -Raw -Encoding UTF8 $path
    if ($existing.Contains($marker)) { Write-Host "Already updated: $path"; continue }
    Add-Content -Encoding UTF8 $path ("`r`n$marker`r`n更新时间：$timestamp`r`n" + $updates[$path])
    Write-Host "Updated: $path"
}
$head = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot record Git version.' }
$manifest = [ordered]@{ captured_at=$timestamp; head=$head; note='HEAD plus current working tree; no commit or peer-review claim'; files=@() }
$names = @('permission-probe-deployed.json','permission-db-side-effects.txt','task-scope-probe.json','task-404-comparison.json','original-access-probe.json','concurrent-submission.json','duplicate-delivery.json','worker-stop-before.json','worker-stop-after.json','submission-p95.json','submission-processing-comparison.json','integration-after-dependency-fix.txt')
foreach ($name in $names) {
    $path = Join-Path $root $name
    $manifest.files += @{ path=$path; sha256=(Get-FileHash -Algorithm SHA256 $path).Hash }
}
$out = Join-Path $root ('local-archive-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $out
Write-Host "Evidence manifest: $out"
Write-Host 'Done. Security rescan, missing functionality, crash tests, peer review and Git commit remain pending.'
