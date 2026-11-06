<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
type Task = { task_id: string; status: string; stage: string; attempts: number; retries: number; error_code: string | null }
const token = ref(''), file = ref<File | null>(null), taskId = ref(''), task = ref<Task | null>(null)
const username = ref(''), password = ref('')
const busy = ref(false), error = ref(''), watching = ref(false)
const labels: Record<string, string> = { queued: '排队中', processing: '处理中', ready: '已就绪', failed: '失败' }
let timer: ReturnType<typeof setTimeout> | undefined
let uploadKey = crypto.randomUUID(), retryKey = crypto.randomUUID()
function stop() { watching.value = false; clearTimeout(timer) }
function changed(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  uploadKey = crypto.randomUUID()
}
async function api(path: string, options: RequestInit = {}) {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch('/api/v1' + path, { ...options, signal: controller.signal,
      headers: { ...options.headers, Authorization: `Bearer ${token.value}` } })
    const data = await response.json()
    if (!response.ok) throw new Error(`${response.status} · ${data.message ?? '请求失败'}`)
    return data
  } finally { clearTimeout(timeout) }
}
async function refresh() {
  if (!taskId.value.trim()) return
  try {
    task.value = await api('/tasks/' + encodeURIComponent(taskId.value.trim()))
    error.value = ''
    if (task.value && ['ready', 'failed'].includes(task.value.status)) stop()
  } catch (e) { error.value = String(e); stop() }
}
async function poll() {
  await refresh()
  if (watching.value) timer = setTimeout(poll, 1500)
}
function watch() { stop(); watching.value = true; void poll() }
async function submit() {
  if (!file.value || !token.value.trim()) { error.value = '请填写演示令牌并选择文件。'; return }
  if (file.value.size > 20 * 1024 * 1024) { error.value = '文件不能超过20 MiB。'; return }
  busy.value = true; error.value = ''; stop()
  try {
    const form = new FormData(); form.append('file', file.value)
    const data = await api('/materials', { method: 'POST', headers: { 'Idempotency-Key': uploadKey }, body: form })
    taskId.value = data.task_id; task.value = null; retryKey = crypto.randomUUID(); watch()
  } catch (e) { error.value = String(e) } finally { busy.value = false }
}
async function retry() {
  busy.value = true; error.value = ''
  try {
    await api('/tasks/' + encodeURIComponent(taskId.value) + '/retry', {
      method: 'POST', headers: { 'Idempotency-Key': retryKey } })
    retryKey = crypto.randomUUID(); watch()
  } catch (e) { error.value = String(e) } finally { busy.value = false }
}
async function login() {
  busy.value = true; error.value = ''; stop()
  try {
    const result = await api('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }) })
    token.value = result.access_token; password.value = ''
  } catch (e) { error.value = String(e) } finally { busy.value = false }
}
function logout() { password.value = ''; stop(); token.value = ''; task.value = null; taskId.value = ''; error.value = '' }
onUnmounted(stop)
</script>
<template>
  <main>
    <p class="eyebrow">LABMATE · 第八课模块演示</p>
    <h1>资料处理</h1>
    <p>提交资料后可查看处理进度。使用账号密码登录后上传资料；令牌仅保存在当前页面内存。</p>
    <section>
      <label>账号<input v-model="username" autocomplete="username" /></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" /></label>
      <button :disabled="busy || !username || !password" @click="login">登录</button>
      <p v-if="token">已取得登录令牌，可提交或查询任务。</p>
      <label>兼容旧CLI演示令牌<input v-model="token" type="password" autocomplete="off" placeholder="仅保存在当前页面内存中" @input="stop" /></label>
      <button class="quiet" @click="logout">清除令牌与会话</button>
    </section>
    <section>
      <h2>上传资料</h2>
      <p>支持UTF-8 TXT、Markdown、可提取文本的PDF，最大20 MiB。请只使用允许上传的虚构演示资料。</p>
      <input type="file" accept=".txt,.md,.pdf" :disabled="busy" @change="changed" />
      <button :disabled="busy || !file || !token" @click="submit">{{ busy ? '提交中…' : '提交处理' }}</button>
    </section>
    <section>
      <h2>任务状态</h2>
      <label>任务标识<input v-model="taskId" placeholder="提交后自动填入，也可输入已有标识" @input="stop" /></label>
      <div class="actions"><button :disabled="!taskId || !token || busy" @click="watch">查询并跟踪</button><button class="quiet" @click="stop">停止跟踪</button></div>
      <p v-if="watching">正在跟踪；排队表示已持久化接收，尚未完成处理。</p>
      <dl v-if="task"><dt>当前状态</dt><dd>{{ labels[task.status] ?? task.status }}</dd><dt>处理阶段</dt><dd>{{ task.stage }}</dd><dt>领取 / 自动重试</dt><dd>{{ task.attempts }} / {{ task.retries }}</dd><dt v-if="task.error_code">错误</dt><dd v-if="task.error_code">{{ task.error_code }}</dd></dl>
      <button v-if="task?.status === 'failed'" :disabled="busy" @click="retry">原因修正后重试</button>
      <p v-else-if="!task && !watching">暂无查询结果。</p>
    </section>
    <p v-if="error" role="alert" class="error">{{ error }}。可核对令牌、任务标识或稍后重试；同一文件重按提交会复用本次提交键。</p>
  </main>
</template>
<style>
:root{font-family:system-ui,sans-serif;color:#17342f;background:#f4f5ef;line-height:1.6}body{margin:0}main{max-width:760px;margin:auto;padding:48px 24px}.eyebrow{font-size:12px;letter-spacing:2px}h1{font-size:36px;margin:10px 0}h2{font-size:21px}section{background:white;border:1px solid #d9e0d6;border-radius:12px;padding:24px;margin:20px 0}label{display:block;font-weight:600}input:not([type=file]){display:block;box-sizing:border-box;width:100%;padding:12px;border:1px solid #b9c7bf;border-radius:6px;margin:8px 0}button{border:0;border-radius:6px;padding:11px 18px;background:#235c4e;color:white;cursor:pointer;margin-top:12px}.quiet{background:#e7eee8;color:#23473d}button:disabled{opacity:.5;cursor:default}.actions{display:flex;gap:10px}dl{display:grid;grid-template-columns:150px 1fr;gap:8px}dd{margin:0;overflow-wrap:anywhere}.error{padding:16px;background:#ffe9e0;color:#8b3521}p{color:#4e655d}input[type=file]{max-width:100%}
</style>
