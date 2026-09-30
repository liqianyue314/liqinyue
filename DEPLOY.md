# 多平台在线课学习进度智能监测与提醒助手部署指南

本项目由 FastAPI 后端和 `templates/index.html` 单文件前端组成，支持两种部署方式：

- 一体化部署：后端同时托管页面和 API，适合快速演示。
- 前后端分离：前端静态托管，后端部署到云服务器或云函数，适合线上访问和比赛展示。

## 一、云端后端部署

### 1. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows：

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

生产环境至少配置：

```bash
DEEPSEEK_API_KEY=sk-你的密钥
FRONTEND_ORIGINS=https://你的前端域名.vercel.app
HOST=0.0.0.0
PORT=8000
```

如果前端和后端部署在多个域名，用英文逗号分隔：

```bash
FRONTEND_ORIGINS=https://example.com,https://www.example.com,https://demo.example.cn
```

如果中国网络环境下无法直接访问 DeepSeek，可以配置 HTTP 代理或 OpenAI 兼容网关：

```bash
HTTPS_PROXY=http://127.0.0.1:7890
HTTP_PROXY=http://127.0.0.1:7890
ALL_PROXY=http://127.0.0.1:7890
```

或：

```bash
DEEPSEEK_BASE_URL=https://你的兼容网关/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 3. 启动生产服务

```bash
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

项目也支持：

```bash
python main.py --server --host 0.0.0.0 --port 8000
```

云平台启动命令建议使用：

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

健康检查地址：

```text
GET /health
```

预期返回：

```json
{"status":"ok","service":"learning-progress-monitor"}
```

## 二、一体化部署

如果云平台支持 Python Web 服务，直接部署整个项目目录：

```text
main.py
requirements.txt
templates/index.html
```

启动后访问：

```text
https://你的后端域名/
```

这种方式不需要配置前端 API 地址，页面会默认使用同源 API。

适合：

- Render Web Service
- Railway Service
- 阿里云 / 腾讯云轻量服务器
- 自建 Linux 云主机

## 三、前后端分离部署

### 1. 前端静态文件

前端只需要托管：

```text
templates/index.html
```

可以将文件复制为静态托管平台需要的入口文件：

```bash
cp templates/index.html index.html
```

如果使用 Vercel，在项目根目录创建 `index.html`，或者将 `templates` 目录配置为静态根目录。

### 2. 配置后端地址

在 `index.html` 中，Vue 脚本之前已经提供了运行时配置入口：

```html
<script>
  window.APP_CONFIG = {
    API_BASE_URL: "https://你的后端域名"
  };
</script>
```

示例：

```html
<script>
  window.APP_CONFIG = {
    API_BASE_URL: "https://learning-api.example.com"
  };
</script>
```

不要在地址末尾重复添加 `/`。前端会自动拼接：

```text
/api/data
/api/upload-multi
/api/generate-ai-text
/api/rag/upload-doc
/api/rag/chat
/api/export-report
```

如果不配置 `API_BASE_URL`，默认使用同源请求，适合一体化部署。

### 3. Vercel 部署示例

1. 将 `index.html` 放在静态项目根目录。
2. 推送到 GitHub 或 GitLab。
3. 在 Vercel 导入仓库。
4. Framework Preset 选择 `Other`。
5. Build Command 留空。
6. Output Directory 使用 `.`。
7. 修改 `window.APP_CONFIG.API_BASE_URL` 为后端公网 HTTPS 地址。
8. 后端的 `FRONTEND_ORIGINS` 配置为 Vercel 域名。

### 4. Gitee Pages / 云存储部署

1. 将 `templates/index.html` 复制到静态站点根目录并命名为 `index.html`。
2. 在文件中填写后端公网地址。
3. 开启 Gitee Pages、OSS 静态网站或 COS 静态网站。
4. 将生成的域名加入后端 `FRONTEND_ORIGINS`。
5. 确保前端和后端都使用 HTTPS，否则浏览器可能阻止跨域请求。

## 四、前后端分离接口清单

| 接口 | 方法 | 用途 |
|---|---|---|
| `/health` | GET | 云平台健康检查 |
| `/api/data` | GET / POST | 获取示例数据或导入单文件 |
| `/api/upload-multi` | POST | 多平台文件按学号合并 |
| `/api/generate-ai-text` | POST | 生成 AI 督促文案 |
| `/api/rag/upload-doc` | POST | 上传 TXT / MD / PDF 课程资料 |
| `/api/rag/chat` | POST | RAG 课程问答 |
| `/api/export-report` | GET | 导出 Markdown 或 Excel 报告 |

## 五、手机 H5 验收清单

部署完成后，使用手机浏览器检查：

- 左侧导航可以通过顶部菜单按钮打开和关闭。
- 学情看板 KPI 在窄屏下自动降为两列或单列。
- 右侧 AI、RAG 卡片自动变为纵向排列。
- 学生明细表只在卡片内部横向滚动，不撑破页面。
- 文件上传按钮可以选择 CSV / XLSX / XLS。
- RAG 资料上传支持 TXT / MD / PDF。
- AI 请求失败时仍显示本地降级文案。
- 报告下载可以在手机浏览器保存文件。
- 访问 `/health` 返回 `status=ok`。

## 六、安全建议

- 不要把真实 DeepSeek Key 写入 Git 仓库。
- 生产环境优先使用后端环境变量 `DEEPSEEK_API_KEY`。
- 页面输入的 API Key 只保存在当前浏览器内存，并会随请求发送到后端。
- 生产环境应将 `FRONTEND_ORIGINS` 配置为真实域名，不建议长期使用 `*`。
- 建议为云服务配置 HTTPS、请求限流和文件大小限制。
- 如果使用公共比赛演示地址，建议配置独立的演示 API Key 和日志脱敏。
