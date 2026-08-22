# Code_ALL

Unified local PPGL inference pipeline for the Jetson AGX Orin deployment.

The entrypoint is:

```bash
source /path/to/anaconda3/etc/profile.d/conda.sh
conda activate ppgl-gpu38

python /path/to/PPGL/Code_ALL/run_case_pipeline.py \
  --case-id PPGL_Tr_0029 \
  --image /path/to/PPGL/dataset/images/PPGL_Tr_0029.nii.gz \
  --mode jetson_fast
```

Default output root:

```text
/path/to/PPGL/Code_ALL/runs
```

## One-command web startup

Start local MiniCPM chat, FastAPI backend, and Vite frontend:

```bash
/path/to/PPGL/Code_ALL/start_ppgl_ai.sh
```

The script will prompt for `REPORT_OPENAI_BASE_URL` and `REPORT_OPENAI_API_KEY` if they are not already set.
To avoid typing the online model settings every time, create `/path/to/PPGL/Code_ALL/.env`:

```bash
REPORT_OPENAI_BASE_URL=http://127.0.0.1:2456
REPORT_OPENAI_MODEL=gpt-5.5
REPORT_OPENAI_REASONING_EFFORT=xhigh
REPORT_OPENAI_API_KEY=your_key
```

Then run the startup script and enter only the API key when prompted. The frontend URL is printed at the end.

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

Pipeline stages:

1. GCPV5 tumor inference.
2. TotalSegmentator anatomy inference.
3. APR false-positive filtering using TotalSegmentator anatomy anchors.
4. Final fusion with tumor priority.
5. Basic clinical metrics and markdown report.

Modes:

- `jetson_fast`: TotalSegmentator only segments `kidney_left`, `kidney_right`, and `aorta`.
- `abdomen`: TotalSegmentator segments a practical abdominal ROI subset.
- `full_total`: TotalSegmentator runs the full `total` task.

For edge deployment, use `jetson_fast` first. Use `full_total` only when full visible-organ output is required.

Jetson inference keeps the PyTorch path by default and enables GCPV5 AMP plus TF32 for speed. For strict A/B
validation runs, add `--no-gcp-amp --no-allow-tf32`.

## Experimental GCPV5 TensorRT backend

The TensorRT path is intentionally opt-in and only replaces the GCPV5 tumor UNet forward pass. TotalSegmentator,
preprocessing, APR, fusion, and reporting stay unchanged.

Build the fixed ROI-160 engine:

```bash
source /path/to/anaconda3/etc/profile.d/conda.sh
conda activate ppgl-gpu38
export LD_LIBRARY_PATH="/path/to/anaconda3/envs/ppgl-gpu38/lib:${LD_LIBRARY_PATH:-}"

python /path/to/PPGL/Code_ALL/export_gcpv5_trt.py \
  --roi-size 160
```

If export fails with `Python package 'onnx' is required`, install an offline/prebuilt `onnx` wheel into `ppgl-gpu38`
first. The current Jetson image already has `trtexec` and system TensorRT Python bindings.

Run a case with the TensorRT GCPV5 backend:

```bash
python /path/to/PPGL/Code_ALL/run_case_pipeline.py \
  --case-id PPGL_Tr_0029 \
  --image /path/to/PPGL/dataset/images/PPGL_Tr_0029.nii.gz \
  --mode jetson_fast \
  --gcp-backend trt \
  --gcp-engine /path/to/PPGL/Code_ALL/engines/gcpv5/gcpv5_roi160_fp16.engine
```

Web API runs can pass `gcp_backend=trt` and `gcp_engine=/path/to/PPGL/Code_ALL/engines/gcpv5/gcpv5_roi160_fp16.engine`.

If TotalSegmentator masks have already been generated elsewhere, keep the new run self-contained while avoiding
rerunning TotalSegmentator:

```bash
python /path/to/PPGL/Code_ALL/run_case_pipeline.py \
  --case-id PPGL_Tr_0029 \
  --image /path/to/PPGL/dataset/images/PPGL_Tr_0029.nii.gz \
  --mode jetson_fast \
  --totalseg-existing-dir /path/to/PPGL/agent_cases/PPGL_Tr_0029/total/totalseg_total
```
