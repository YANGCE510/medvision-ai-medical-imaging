# PPGL AI Backend

FastAPI 内部 AI 服务，提供全器官分割、PPGL 肿瘤分割、3D 产物、RAG 检索与 AI 报告能力。

FastAPI is the internal AI service. It owns model execution, AI task workspaces, generated artifacts,
RAG retrieval, and report generation. User login, roles, business records, and the public API belong to
Spring Boot. The browser must use Spring Boot's `/api/ai/**` gateway instead of connecting to port 8000.

Runtime data is intentionally kept outside the code repository. Set `PPGL_DATA_ROOT` before starting services:

```bash
export PPGL_DATA_ROOT=/mnt/20T/ppgl-assist-data
mkdir -p "$PPGL_DATA_ROOT"/{cases,logs,rag-documents,rag-index,rag-parsed}
```

FastAPI uses `$PPGL_DATA_ROOT/cases` for AI case workspaces by default. RAG documents, parsed chunks, and Qdrant
indexes can be overridden with `PPGL_RAG_DOCUMENTS_DIR`, `PPGL_RAG_CHUNKS_PATH`, and `PPGL_QDRANT_PATH`.

PPGL 分割任务使用仓库内的推理运行时 `ai-backend/progress_patch_v5/`，默认权重位置为
`ai-backend/progress_patch_v5/weights/model_best.pth`.

The entrypoint is:

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ppgl-gpu38

python ai-backend/run_totalseg_pipeline.py \
  --case-id PPGL_Tr_0029 \
  --image demo-data/PPGL_Tr_0029.nii.gz \
  --mode jetson_fast
```

全器官与 PPGL 分割是独立任务：全器官任务只运行 TotalSegmentator；PPGL 任务生成肿瘤 mask、量化指标和独立 3D mesh。失败任务可通过 Web 页面强制重试。

Default output root:

```text
$PPGL_DATA_ROOT/cases
```

## One-command web startup

Start Ollama, FastAPI backend, and Vite frontend:

```bash
./ai-backend/start_ppgl_ai.sh
```

启动脚本读取仓库根目录 `.env` 或 `ai-backend/.env`。真实密钥、模型地址和运行数据目录应通过环境变量配置，不能提交到 Git。

例如，配置兼容 OpenAI 的在线模型时可在 `ai-backend/.env` 中填写：

```bash
REPORT_OPENAI_BASE_URL=http://127.0.0.1:2456
REPORT_OPENAI_MODEL=gpt-5.5
REPORT_OPENAI_REASONING_EFFORT=xhigh
REPORT_OPENAI_API_KEY=your_key
```

前端访问地址会在脚本启动完成后打印。

## Generic streaming chat API

Use this API when another Web system already has the report, metrics, risk result, and chat history in its own
database, and only wants to use the Jetson as a local LLM compute node.

Endpoint:

```http
POST http://127.0.0.1:8000/api/llm/chat/stream
Content-Type: application/json
Accept: application/x-ndjson
```

Request:

```json
{
  "question": "这个病例为什么需要医生复核？",
  "context": {
    "report": "AI报告正文 Markdown 或纯文本",
    "metrics": {
      "tumor_volume_ml": 1.765,
      "max_diameter_mm": 17.0
    },
    "risk": {
      "level": "high",
      "reasons": ["邻近大血管", "多组件"]
    }
  },
  "history": [],
  "max_tokens": 800
}
```

Streaming response format is newline-delimited JSON:

```json
{"type":"delta","text":"根据"}
{"type":"delta","text":"当前"}
{"type":"done","answer":"完整回答...","metadata":{"provider":"openai_compat","stream":true}}
```

Web clients should append every `delta.text` to the chat bubble. When `type` is `done`, save `answer` as the final
assistant message. If `type` is `error`, show `detail`.

Curl test:

```bash
curl -N -X POST http://127.0.0.1:8000/api/llm/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这个病例为什么需要医生复核？",
    "context": {
      "report": "AI报告提示肿瘤靠近下腔静脉。",
      "metrics": {"tumor_volume_ml": 1.765, "max_diameter_mm": 17.0},
      "risk": {"level": "high", "reasons": ["邻近大血管", "多组件"]}
    },
    "history": [],
    "max_tokens": 256
  }'
```

Prompt for the Web-system developer:

```text
请把 Jetson 当作本地大模型聊天计算节点使用，不要直接访问 18080 模型内部端口。

1. Jetson 服务地址：
   http://127.0.0.1:8000

2. 通用流式聊天接口：
   POST /api/llm/chat/stream
   Content-Type: application/json
   返回 application/x-ndjson，每行一个 JSON。

3. 请求体由 Web 系统提供完整文本上下文：
   - question：医生当前问题
   - context.report：AI报告 Markdown 或纯文本
   - context.metrics：分割指标 JSON，例如肿瘤体积、最大径、组件数量、器官距离
   - context.risk：风险等级和风险原因
   - history：最近 3 到 5 轮对话历史
   - max_tokens：建议 512 到 800

4. 前端流式读取规则：
   - type=delta：把 text 追加到当前 AI 回复气泡
   - type=done：保存 answer 作为最终回复
   - type=error：展示 detail

5. 注意：
   - 该接口只接收文本/JSON，不接收 CT、DICOM、NIfTI、mask 或图片。
   - Web 系统负责病例权限、数据库、聊天记录保存。
   - Jetson 只负责基于传入上下文进行本地模型推理并返回回答。
```

TotalSegmentator modes:

- `jetson_fast`: TotalSegmentator only segments `kidney_left`, `kidney_right`, and `aorta`.
- `abdomen`: TotalSegmentator segments a practical abdominal ROI subset.
- `full_total`: TotalSegmentator runs the full `total` task.

For edge deployment, use `jetson_fast` first. Use `full_total` only when full visible-organ output is required.

If TotalSegmentator masks have already been generated elsewhere, reuse them without rerunning inference:

```bash
python ai-backend/run_totalseg_pipeline.py \
  --case-id PPGL_Tr_0029 \
  --image demo-data/PPGL_Tr_0029.nii.gz \
  --mode jetson_fast \
  --totalseg-existing-dir demo-data/totalseg/PPGL_Tr_0029
```
