from fastapi import BackgroundTasks, FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import importlib.util
import os
import shutil
import subprocess
import uuid
import json
import sys
import traceback
import urllib.error
import urllib.request
import zipfile
from threading import Lock

from report_agent import (
    build_ai_report_chat_request,
    chat_with_ai_report,
    direct_ai_report_answer,
    generate_ai_report,
    llm_provider,
    save_ai_report_chat,
    stream_openai_text,
)

app = FastAPI(title="PPGL AI Segmentation API")


# 允许前端访问后端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 工程根目录：/path/to/PPGL/Code_ALL
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = Path("/path/to/PPGL/ppgl-frontend")
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

# 病例保存目录：/path/to/PPGL/Code_ALL/cases
CASES_DIR = BASE_DIR / "cases"
CASES_DIR.mkdir(parents=True, exist_ok=True)
RUNNING_CASES = set()
SEGMENTATION_LOCK = Lock()


class AiReportChatRequest(BaseModel):
    question: str
    history: List[Dict[str, Any]] = Field(default_factory=list)


class GenericLlmStreamChatRequest(BaseModel):
    question: str = ""
    context: Any = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    messages: Optional[List[Dict[str, Any]]] = None
    max_tokens: int = Field(default=800, ge=64, le=2000)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path.name}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ollama_chat_config() -> Optional[Dict[str, Any]]:
    base_url = os.environ.get("CHAT_OPENAI_BASE_URL", "")
    if "11434" not in base_url:
        return None
    model = os.environ.get("CHAT_OPENAI_MODEL", "").strip()
    if not model:
        return None
    native_base_url = base_url.rstrip("/")
    if native_base_url.endswith("/v1"):
        native_base_url = native_base_url[:-3]
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "-1").strip() or "-1"
    try:
        keep_alive_value: Union[int, str] = int(keep_alive)
    except ValueError:
        keep_alive_value = keep_alive
    return {
        "base_url": native_base_url,
        "model": model,
        "keep_alive": keep_alive_value,
    }


def post_ollama_json(url: str, payload: Dict[str, Any], timeout: float) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def unload_chat_model_for_segmentation(log_path: Optional[Path] = None) -> None:
    config = ollama_chat_config()
    if config is None:
        return
    payload = {"model": config["model"], "keep_alive": 0}
    response = post_ollama_json(f"{config['base_url']}/api/generate", payload, timeout=30)
    if log_path is not None:
        message = (
            f"[{now_text()}] Ollama chat model unloaded before segmentation: {config['model']}"
            if response is not None
            else f"[{now_text()}] Ollama chat model unload skipped/failed before segmentation: {config['model']}"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")


def preload_chat_model_after_segmentation(log_path: Optional[Path] = None) -> None:
    config = ollama_chat_config()
    if config is None:
        return
    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "think": False,
        "keep_alive": config["keep_alive"],
        "options": {"num_predict": 1, "temperature": 0},
    }
    response = post_ollama_json(f"{config['base_url']}/api/chat", payload, timeout=180)
    if log_path is not None:
        message = (
            f"[{now_text()}] Ollama chat model preloaded after segmentation: {config['model']}"
            if response is not None
            else f"[{now_text()}] Ollama chat model preload failed after segmentation: {config['model']}"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")


def stream_event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def text_from_payload_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, indent=2)


def has_payload_context(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def build_generic_llm_prompt(payload: GenericLlmStreamChatRequest) -> str:
    if payload.messages:
        message_lines = []
        for item in payload.messages:
            role = str(item.get("role", "user")).strip() or "user"
            content = text_from_payload_value(item.get("content", ""))
            if content:
                message_lines.append(f"{role}: {content}")
        prompt = "\n\n".join(message_lines).strip()
        if prompt:
            return prompt

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    has_context = has_payload_context(payload.context)
    context_text = text_from_payload_value(payload.context) if has_context else ""
    history_text = text_from_payload_value(payload.history[-6:]) if payload.history else ""
    if not has_context and not history_text:
        return question

    parts = []
    if history_text:
        parts.append(f"【最近对话历史】\n{history_text}")
    if has_context:
        parts.append(f"【上下文】\n{context_text}")
    parts.append(f"【用户输入】\n{question}")
    return "\n\n".join(parts)


def parse_status_time(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def validated_case_dir_path(case_id: str) -> Path:
    if (
        not case_id
        or not case_id.strip()
        or case_id in {".", ".."}
        or "/" in case_id
        or "\\" in case_id
    ):
        raise HTTPException(status_code=400, detail="Invalid case_id")

    cases_root = CASES_DIR.resolve()
    case_dir = (CASES_DIR / case_id).resolve()
    if case_dir.parent != cases_root:
        raise HTTPException(status_code=400, detail="Invalid case_id")
    return case_dir


def case_dir_for(case_id: str) -> Path:
    case_dir = validated_case_dir_path(case_id)
    if not case_dir.is_dir():
        raise HTTPException(status_code=404, detail="Case not found")
    return case_dir


def update_status(case_dir: Path, status: str, message: str, progress: int, **extra) -> None:
    payload = {
        "case_id": case_dir.name,
        "status": status,
        "message": message,
        "progress": int(progress),
        "updated_at": now_text(),
        **extra,
    }
    write_json(case_dir / "status.json", payload)


def status_with_pipeline_progress(case_dir: Path) -> dict:
    status_path = case_dir / "status.json"
    status = read_json(status_path) if status_path.exists() else {
        "case_id": case_dir.name,
        "status": "unknown",
        "message": "",
        "progress": 0,
        "updated_at": "",
    }

    result_path = case_dir / "output" / "result.json"
    if result_path.exists() and status.get("status") != "failed":
        enriched = dict(status)
        enriched.update(
            {
                "status": "completed",
                "message": status.get("message") or "AI 分割完成",
                "progress": 100,
                "result_path": str(result_path),
            }
        )
        return enriched

    if status.get("status") in {"completed", "failed"}:
        return status

    log_path = case_dir / "output" / "code_all" / "logs" / "pipeline.log"
    if not log_path.exists():
        status_time = parse_status_time(status.get("updated_at", ""))
        queued_age = (datetime.now() - status_time).total_seconds() if status_time else 0
        if (
            status.get("status") == "queued"
            and case_dir.name not in RUNNING_CASES
            and queued_age > 120
        ):
            stale = dict(status)
            stale.update(
                {
                    "status": "uploaded",
                    "message": "上一次任务未实际启动，请重新点击启动分割",
                    "progress": 0,
                    "stale_queue": True,
                }
            )
            return stale
        return status

    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")[-30000:]
    except OSError:
        return status

    rules = [
        ("[DONE] 5/5", 98, "正在整理最终结果", "analysis_done"),
        ("[START] 5/5", 92, "正在生成临床指标和分析报告", "analysis"),
        ("[DONE] 4/5", 88, "融合结果已生成", "fusion_done"),
        ("[START] 4/5", 80, "正在融合器官和肿瘤分割结果", "fusion"),
        ("[DONE] 3/5", 75, "APR 假阳性过滤完成", "apr_done"),
        ("[START] 3/5", 60, "正在进行 APR 假阳性过滤", "apr"),
        ("[DONE] 2/5", 55, "TotalSegmentator 器官分割完成", "total_done"),
        ("[START] 2/5", 40, "正在运行 TotalSegmentator 器官分割", "total"),
        ("GCPV5 raw label saved", 32, "正在保存 GCPV5 肿瘤分割结果", "gcp_saving"),
        ("Starting MONAI sliding-window inference", 20, "正在运行 GCPV5 肿瘤分割", "gcp_inference"),
        ("[START] 1/5", 15, "正在加载 GCPV5 肿瘤分割模型", "gcp"),
    ]

    enriched = dict(status)
    for pattern, progress, message, stage in rules:
        if pattern in text:
            enriched["status"] = "running"
            enriched["message"] = message
            enriched["progress"] = max(int(enriched.get("progress") or 0), progress)
            enriched["stage"] = stage
            enriched["pipeline_log"] = str(log_path)
            break

    return enriched


def output_file(case_id: str, filename: str) -> Path:
    case_dir = case_dir_for(case_id)
    path = case_dir / "output" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    return path


def result_output_path(case_id: str, key: str, fallback: Path) -> Path:
    case_dir = case_dir_for(case_id)
    result_path = case_dir / "output" / "result.json"
    path = fallback
    if result_path.exists():
        result = read_json(result_path)
        value = result.get("outputs", {}).get(key, "")
        if value:
            path = Path(value)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{path.name} not found")
    return path


def optional_file_path(value: str) -> Path:
    if not str(value or "").strip():
        return Path("__missing__")
    return Path(value)


def load_run_single_case():
    wrapper_path = FRONTEND_DIR / "inference_wrapper.py"
    spec = importlib.util.spec_from_file_location("ppgl_frontend_inference_wrapper", wrapper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load inference wrapper: {wrapper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_single_case


def subprocess_runtime_env() -> dict:
    env = os.environ.copy()
    env_prefix = Path(sys.executable).resolve().parent.parent
    env_bin = env_prefix / "bin"
    env_lib = env_prefix / "lib"
    env["PATH"] = str(env_bin) + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = str(env_lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                member = Path(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise HTTPException(status_code=400, detail=f"Invalid zip member: {info.filename}")
                target = (dest_dir / member).resolve()
                if dest_root not in target.parents and target != dest_root:
                    raise HTTPException(status_code=400, detail=f"Invalid zip member: {info.filename}")
            archive.extractall(dest_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid TotalSegmentator zip file")


def normalize_totalseg_existing_dir(totalseg_dir: Path) -> int:
    root_masks = sorted(totalseg_dir.glob("*.nii.gz"))
    if root_masks:
        return len(root_masks)

    nested_masks = sorted(totalseg_dir.rglob("*.nii.gz"))
    for src in nested_masks:
        dst = totalseg_dir / src.name
        if dst.exists():
            raise HTTPException(status_code=400, detail=f"Duplicate mask filename in zip: {src.name}")
        shutil.copy2(src, dst)
    return len(nested_masks)


def run_segmentation_task(
    case_id: str,
    mode: str,
    device: str,
    force: bool,
    totalseg_fast: bool,
    totalseg_fastest: bool,
    gcp_amp: bool,
    allow_tf32: bool,
    gcp_backend: str,
    gcp_engine: str,
) -> None:
    case_dir = CASES_DIR / case_id
    input_path = case_dir / "input" / "ct.nii.gz"
    output_dir = case_dir / "output"
    model_lifecycle_log = output_dir / "model_lifecycle.log"

    try:
        RUNNING_CASES.add(case_id)
        with SEGMENTATION_LOCK:
            run_single_case = load_run_single_case()

            if force and output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            update_status(case_dir, "running", "AI 分割正在运行", 10)
            unload_chat_model_for_segmentation(model_lifecycle_log)
            try:
                result = run_single_case(
                    input_path=str(input_path),
                    output_dir=str(output_dir),
                    device=device,
                    case_id=case_id,
                    mode=mode,
                    totalseg_fast=totalseg_fast,
                    totalseg_fastest=totalseg_fastest,
                    gcp_amp=gcp_amp,
                    allow_tf32=allow_tf32,
                    gcp_backend=gcp_backend,
                    gcp_engine=gcp_engine,
                )
            finally:
                preload_chat_model_after_segmentation(model_lifecycle_log)
            update_status(
                case_dir,
                "completed",
                "AI 分割完成",
                100,
                result=result,
            )
    except Exception as exc:
        error_path = case_dir / "error.log"
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        update_status(
            case_dir,
            "failed",
            "AI 分割失败",
            100,
            error=str(exc),
            error_log=str(error_path),
        )
    finally:
        RUNNING_CASES.discard(case_id)


def run_existing_totalseg_task(
    case_id: str,
    mode: str,
    device: str,
    totalseg_existing_dir: str,
    gcp_backend: str = "torch",
    gcp_engine: str = "",
) -> None:
    case_dir = CASES_DIR / case_id
    input_path = case_dir / "input" / "ct.nii.gz"
    output_dir = case_dir / "output"
    log_path = output_dir / "run_with_existing_totalseg.log"
    model_lifecycle_log = output_dir / "model_lifecycle.log"

    try:
        RUNNING_CASES.add(case_id)
        with SEGMENTATION_LOCK:
            output_dir.mkdir(parents=True, exist_ok=True)
            update_status(case_dir, "running", "AI 分割正在运行（复用已有 TotalSegmentator 结果）", 10)

            cmd = [
                sys.executable,
                str(BASE_DIR / "run_otafv2.py"),
                "--input",
                str(input_path),
                "--output",
                str(output_dir),
                "--case-id",
                case_id,
                "--mode",
                mode,
                "--device",
                device,
                "--gcp-backend",
                gcp_backend,
                "--totalseg-existing-dir",
                str(totalseg_existing_dir),
                "--force",
            ]
            if str(gcp_engine).strip():
                cmd.extend(["--gcp-engine", str(gcp_engine)])
            unload_chat_model_for_segmentation(model_lifecycle_log)
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=str(BASE_DIR),
                    env=subprocess_runtime_env(),
                    text=True,
                    capture_output=True,
                )
            finally:
                preload_chat_model_after_segmentation(model_lifecycle_log)
            log_path.write_text(
                "COMMAND:\n"
                + " ".join(cmd)
                + "\n\nSTDOUT:\n"
                + completed.stdout
                + "\n\nSTDERR:\n"
                + completed.stderr,
                encoding="utf-8",
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Code_ALL pipeline failed. See log: {log_path}")

            result_path = output_dir / "result.json"
            result = read_json(result_path) if result_path.exists() else {}
            update_status(
                case_dir,
                "completed",
                "AI 分割完成（已复用外部 TotalSegmentator 结果）",
                100,
                result=result,
            )
    except Exception as exc:
        error_path = case_dir / "error.log"
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        update_status(
            case_dir,
            "failed",
            "AI 分割失败",
            100,
            error=str(exc),
            error_log=str(error_path),
        )
    finally:
        RUNNING_CASES.discard(case_id)


@app.get("/")
async def root():
    return {
        "message": "PPGL AI Segmentation API is running"
    }


@app.post("/api/cases/upload")
async def upload_ct(file: UploadFile = File(...)):
    """
    上传 .nii.gz CT 文件。
    前端字段名必须是 file。
    """

    if not (file.filename or "").endswith(".nii.gz"):
        raise HTTPException(
            status_code=400,
            detail="当前仅支持 .nii.gz 文件"
        )

    case_id = f"case_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    case_dir = CASES_DIR / case_id
    input_dir = case_dir / "input"
    output_dir = case_dir / "output"

    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = input_dir / "ct.nii.gz"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    case_info = {
        "case_id": case_id,
        "original_filename": file.filename,
        "input_path": str(input_path),
        "created_at": now_text()
    }

    status_info = {
        "case_id": case_id,
        "status": "uploaded",
        "message": "CT 文件上传成功",
        "progress": 0,
        "updated_at": now_text()
    }

    write_json(case_dir / "case_info.json", case_info)
    write_json(case_dir / "status.json", status_info)

    return {
        "case_id": case_id,
        "status": "uploaded",
        "message": "CT 文件上传成功"
    }


@app.post("/api/cases/{case_id}/run-with-existing-totalseg")
async def run_case_with_existing_totalseg(
    case_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    totalseg_zip: UploadFile = File(...),
    mode: str = Form("abdomen"),
    device: str = Form("cuda"),
    gcp_backend: str = Form("torch"),
    gcp_engine: str = Form(""),
):
    if not (file.filename or "").endswith(".nii.gz"):
        raise HTTPException(status_code=400, detail="当前仅支持 ct.nii.gz")
    if not (totalseg_zip.filename or "").endswith(".zip"):
        raise HTTPException(status_code=400, detail="totalseg_zip must be a .zip file")
    if mode not in {"jetson_fast", "abdomen", "full_total"}:
        raise HTTPException(status_code=400, detail="mode must be jetson_fast, abdomen, or full_total")
    if gcp_backend not in {"torch", "trt"}:
        raise HTTPException(status_code=400, detail="gcp_backend must be torch or trt")
    if case_id in RUNNING_CASES:
        raise HTTPException(status_code=409, detail="Case is running")

    case_dir = validated_case_dir_path(case_id)
    input_dir = case_dir / "input"
    output_dir = case_dir / "output"
    totalseg_existing_dir = input_dir / "totalseg_existing"
    ct_path = input_dir / "ct.nii.gz"
    zip_path = input_dir / "totalseg_existing.zip"

    if output_dir.exists():
        shutil.rmtree(output_dir)
    if totalseg_existing_dir.exists():
        shutil.rmtree(totalseg_existing_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(ct_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    with open(zip_path, "wb") as buffer:
        shutil.copyfileobj(totalseg_zip.file, buffer)

    safe_extract_zip(zip_path, totalseg_existing_dir)
    mask_count = normalize_totalseg_existing_dir(totalseg_existing_dir)
    if mask_count <= 0:
        raise HTTPException(status_code=400, detail="No .nii.gz TotalSegmentator masks found in zip")

    case_info = {
        "case_id": case_id,
        "original_filename": file.filename,
        "input_path": str(ct_path),
        "totalseg_zip_filename": totalseg_zip.filename,
        "totalseg_existing_dir": str(totalseg_existing_dir),
        "totalseg_mask_count": mask_count,
        "mode": mode,
        "device": device,
        "created_at": now_text(),
        "source": "external_totalseg_zip",
    }
    write_json(case_dir / "case_info.json", case_info)

    update_status(
        case_dir,
        "queued",
        "AI 分割任务已提交（复用已有 TotalSegmentator 结果）",
        5,
        totalseg_existing_dir=str(totalseg_existing_dir),
        totalseg_mask_count=mask_count,
    )
    background_tasks.add_task(
        run_existing_totalseg_task,
        case_id,
        mode,
        device,
        str(totalseg_existing_dir),
        gcp_backend,
        gcp_engine,
    )
    return read_json(case_dir / "status.json")


@app.get("/api/cases")
async def list_cases():
    rows = []
    for case_dir in sorted(CASES_DIR.iterdir(), reverse=True):
        if not case_dir.is_dir():
            continue
        status_path = case_dir / "status.json"
        case_info_path = case_dir / "case_info.json"
        status = status_with_pipeline_progress(case_dir) if status_path.exists() else {}
        case_info = read_json(case_info_path) if case_info_path.exists() else {}
        rows.append(
            {
                "case_id": case_dir.name,
                "status": status.get("status", "unknown"),
                "message": status.get("message", ""),
                "progress": status.get("progress", 0),
                "original_filename": case_info.get("original_filename", ""),
                "created_at": case_info.get("created_at", ""),
                "updated_at": status.get("updated_at", ""),
            }
        )
    return {"cases": rows}


@app.delete("/api/cases/{case_id}")
async def delete_case(case_id: str):
    case_dir = case_dir_for(case_id)
    status = status_with_pipeline_progress(case_dir)

    if case_id in RUNNING_CASES or status.get("status") in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Case is running, cannot delete")

    try:
        shutil.rmtree(case_dir)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete case: {exc}")

    return {
        "case_id": case_id,
        "status": "deleted",
        "message": "病例已删除",
    }


@app.post("/api/cases/{case_id}/segment")
async def start_segmentation(
    case_id: str,
    background_tasks: BackgroundTasks,
    mode: str = "abdomen",
    device: str = "cuda",
    force: bool = False,
    totalseg_fast: bool = True,
    totalseg_fastest: bool = False,
    gcp_amp: bool = True,
    allow_tf32: bool = True,
    gcp_backend: str = "torch",
    gcp_engine: str = "",
):
    case_dir = case_dir_for(case_id)
    input_path = case_dir / "input" / "ct.nii.gz"
    result_path = case_dir / "output" / "result.json"

    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Input CT not found")
    if mode not in {"jetson_fast", "abdomen", "full_total"}:
        raise HTTPException(status_code=400, detail="mode must be jetson_fast, abdomen, or full_total")
    if gcp_backend not in {"torch", "trt"}:
        raise HTTPException(status_code=400, detail="gcp_backend must be torch or trt")
    if case_id in RUNNING_CASES:
        return read_json(case_dir / "status.json")
    if result_path.exists() and not force:
        update_status(case_dir, "completed", "AI 分割已完成", 100)
        return read_json(case_dir / "status.json")

    update_status(case_dir, "queued", "AI 分割任务已提交", 5)
    background_tasks.add_task(
        run_segmentation_task,
        case_id,
        mode,
        device,
        force,
        totalseg_fast,
        totalseg_fastest,
        gcp_amp,
        allow_tf32,
        gcp_backend,
        gcp_engine,
    )
    return read_json(case_dir / "status.json")


@app.get("/api/cases/{case_id}/status")
async def get_case_status(case_id: str):
    case_dir = case_dir_for(case_id)
    return status_with_pipeline_progress(case_dir)


@app.get("/api/cases/{case_id}/result")
async def get_case_result(case_id: str):
    return read_json(output_file(case_id, "result.json"))


@app.get("/api/cases/{case_id}/overlay")
async def get_case_overlay(case_id: str):
    return FileResponse(output_file(case_id, "overlay.png"), media_type="image/png")


@app.get("/api/cases/{case_id}/slice-gallery")
async def get_case_slice_gallery(case_id: str):
    case_dir = case_dir_for(case_id)
    manifest_path = result_output_path(
        case_id,
        "slice_gallery_path",
        case_dir / "output" / "slices" / "slice_gallery.json",
    )
    return read_json(manifest_path)


@app.get("/api/cases/{case_id}/slice-gallery/{filename}")
async def get_case_slice_image(case_id: str, filename: str):
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Invalid slice filename")
    case_dir = case_dir_for(case_id)
    image_path = case_dir / "output" / "slices" / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    return FileResponse(image_path, media_type="image/png")


@app.get("/api/cases/{case_id}/mask")
async def get_case_mask(case_id: str):
    return FileResponse(
        output_file(case_id, "mask.nii.gz"),
        media_type="application/gzip",
        filename=f"{case_id}_mask.nii.gz",
    )


@app.get("/api/cases/{case_id}/mesh")
async def get_case_mesh(case_id: str):
    case_dir = case_dir_for(case_id)
    mesh_path = result_output_path(
        case_id,
        "mesh_glb_path",
        case_dir / "output" / "meshes" / "scene.glb",
    )
    return FileResponse(
        mesh_path,
        media_type="model/gltf-binary",
        filename=f"{case_id}_scene.glb",
    )


@app.get("/api/cases/{case_id}/mesh-manifest")
async def get_case_mesh_manifest(case_id: str):
    case_dir = case_dir_for(case_id)
    manifest_path = result_output_path(
        case_id,
        "mesh_manifest_path",
        case_dir / "output" / "meshes" / "mesh_manifest.json",
    )
    return read_json(manifest_path)


@app.get("/api/cases/{case_id}/report", response_class=PlainTextResponse)
async def get_case_report(case_id: str):
    result = read_json(output_file(case_id, "result.json"))
    ai_report_path = optional_file_path(result.get("outputs", {}).get("ai_report_markdown_path", ""))
    if ai_report_path.is_file():
        return ai_report_path.read_text(encoding="utf-8")

    fallback_ai_report_path = case_dir_for(case_id) / "output" / "ai_report.md"
    if fallback_ai_report_path.is_file():
        return fallback_ai_report_path.read_text(encoding="utf-8")

    report_path = optional_file_path(result.get("outputs", {}).get("report_path", ""))
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail="report.md not found")
    return report_path.read_text(encoding="utf-8")


@app.post("/api/cases/{case_id}/ai-report/generate")
async def generate_case_ai_report(case_id: str):
    case_dir = case_dir_for(case_id)
    result_path = case_dir / "output" / "result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="请先完成分割，再生成 AI 报告")

    try:
        report = generate_ai_report(case_dir)
        (case_dir / "output" / "ai_report_error.log").unlink(missing_ok=True)
        return report
    except RuntimeError as exc:
        error_path = case_dir / "output" / "ai_report_error.log"
        error_path.write_text(str(exc), encoding="utf-8")
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        error_path = case_dir / "output" / "ai_report_error.log"
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise HTTPException(status_code=500, detail=f"AI 报告生成失败：{exc}")


@app.get("/api/cases/{case_id}/ai-report")
async def get_case_ai_report(case_id: str):
    case_dir = case_dir_for(case_id)
    report_path = case_dir / "output" / "ai_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="ai_report.json not found")
    return read_json(report_path)


@app.get("/api/cases/{case_id}/ai-report/chat")
async def get_case_ai_report_chat(case_id: str):
    case_dir = case_dir_for(case_id)
    chat_path = case_dir / "output" / "ai_report_chat.json"
    if not chat_path.exists():
        return {
            "case_id": case_id,
            "messages": [],
        }
    return read_json(chat_path)


@app.post("/api/cases/{case_id}/ai-report/chat")
async def chat_case_ai_report(case_id: str, payload: AiReportChatRequest):
    case_dir = case_dir_for(case_id)
    result_path = case_dir / "output" / "result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="请先完成分割，再进行 AI 问答")
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    output_dir = case_dir / "output"
    if not (output_dir / "ai_report.md").exists() and not (output_dir / "ai_report.json").exists():
        raise HTTPException(status_code=404, detail="请先生成 AI 报告，再进行 AI 问答")

    try:
        return chat_with_ai_report(case_dir, payload.question, payload.history)
    except RuntimeError as exc:
        error_path = case_dir / "output" / "ai_report_chat_error.log"
        error_path.write_text(str(exc), encoding="utf-8")
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        error_path = case_dir / "output" / "ai_report_chat_error.log"
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise HTTPException(status_code=500, detail=f"AI 问答失败：{exc}")


@app.post("/api/cases/{case_id}/ai-report/chat/stream")
async def stream_chat_case_ai_report(case_id: str, payload: AiReportChatRequest):
    case_dir = case_dir_for(case_id)
    result_path = case_dir / "output" / "result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="请先完成分割，再进行 AI 问答")
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    output_dir = case_dir / "output"
    if not (output_dir / "ai_report.md").exists() and not (output_dir / "ai_report.json").exists():
        raise HTTPException(status_code=404, detail="请先生成 AI 报告，再进行 AI 问答")

    def generate():
        answer_parts: list[str] = []
        try:
            direct = direct_ai_report_answer(case_dir, payload.question)
            if direct is not None:
                clean_question, answer, metadata = direct
                for index in range(0, len(answer), 18):
                    yield stream_event({"type": "delta", "text": answer[index : index + 18]})
                chat = save_ai_report_chat(case_dir, clean_question, answer, {**metadata, "stream": True})
                yield stream_event({"type": "done", "chat": chat})
                return

            clean_question, prompt = build_ai_report_chat_request(
                case_dir,
                payload.question,
                payload.history,
            )
            for delta in stream_openai_text(prompt):
                answer_parts.append(delta)
                yield stream_event({"type": "delta", "text": delta})

            answer = "".join(answer_parts).strip()
            if not answer:
                raise RuntimeError("OpenAI API returned an empty answer")

            chat = save_ai_report_chat(
                case_dir,
                clean_question,
                answer,
                {"provider": llm_provider(), "stream": True},
            )
            yield stream_event({"type": "done", "chat": chat})
        except RuntimeError as exc:
            error_path = case_dir / "output" / "ai_report_chat_error.log"
            error_path.write_text(str(exc), encoding="utf-8")
            yield stream_event({"type": "error", "detail": str(exc)})
        except Exception as exc:
            error_path = case_dir / "output" / "ai_report_chat_error.log"
            error_path.write_text(traceback.format_exc(), encoding="utf-8")
            yield stream_event({"type": "error", "detail": f"AI 问答失败：{exc}"})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/llm/chat/stream")
async def stream_generic_llm_chat(payload: GenericLlmStreamChatRequest):
    prompt = build_generic_llm_prompt(payload)

    def generate():
        answer_parts: list[str] = []
        try:
            for delta in stream_openai_text(prompt, max_output_tokens=payload.max_tokens):
                answer_parts.append(delta)
                yield stream_event({"type": "delta", "text": delta})

            answer = "".join(answer_parts).strip()
            if not answer:
                raise RuntimeError("OpenAI-compatible API returned an empty answer")

            yield stream_event(
                {
                    "type": "done",
                    "answer": answer,
                    "metadata": {
                        "provider": llm_provider(),
                        "stream": True,
                    },
                }
            )
        except RuntimeError as exc:
            yield stream_event({"type": "error", "detail": str(exc)})
        except Exception as exc:
            yield stream_event({"type": "error", "detail": f"AI 问答失败：{exc}"})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/cases/{case_id}/metrics")
async def get_case_metrics(case_id: str):
    result = read_json(output_file(case_id, "result.json"))
    metrics_path = Path(result.get("outputs", {}).get("clinical_metrics_path", ""))
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="clinical_metrics.json not found")
    return read_json(metrics_path)


@app.get("/api/cases/{case_id}/llm-context")
async def get_case_llm_context(case_id: str):
    result = read_json(output_file(case_id, "result.json"))
    context_path = Path(result.get("outputs", {}).get("llm_context_path", ""))
    if not context_path.exists():
        raise HTTPException(status_code=404, detail="llm_context.json not found")
    return read_json(context_path)


@app.get("/api/cases/{case_id}/risk")
async def get_case_risk(case_id: str):
    result = read_json(output_file(case_id, "result.json"))
    risk = result.get("risk_assessment") or result.get("clinical_metrics", {}).get("risk_assessment")
    if not risk:
        raise HTTPException(status_code=404, detail="risk_assessment not found")
    return risk


@app.get("/api/cases/{case_id}/label-map")
async def get_case_label_map(case_id: str):
    result = read_json(output_file(case_id, "result.json"))
    label_map_path = Path(result.get("outputs", {}).get("label_map_path", ""))
    if not label_map_path.exists():
        raise HTTPException(status_code=404, detail="label_map.json not found")
    return read_json(label_map_path)
