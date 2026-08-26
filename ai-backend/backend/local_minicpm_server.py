from __future__ import annotations

import json
import os
import queue
import re
import time
import uuid
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Dict, List

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
import transformers.generation.utils as generation_utils


DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "MiniCPM5-1B"
MODEL_DIR = os.environ.get("MINICPM_MODEL_DIR", str(DEFAULT_MODEL_DIR))
MODEL_NAME = os.environ.get("OPENAI_MODEL", "MiniCPM5-1B")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TRAILING_ROLE_LABEL_RE = re.compile(r"(^|[\s\r\n]+)(用户|医生|助手)([:：])?\s*$")

app = FastAPI(title="Local MiniCPM OpenAI-compatible API")
tokenizer = None
model = None
GENERATION_LOCK = Lock()

generation_utils.is_fsdp_managed_module = lambda _module: False


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_NAME
    messages: List[ChatMessage]
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    stream: bool = False


def load_model() -> None:
    global tokenizer, model
    if model is not None and tokenizer is not None:
        return

    if not os.path.isdir(MODEL_DIR):
        raise RuntimeError(f"MiniCPM model directory not found: {MODEL_DIR}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, trust_remote_code=True)
    dtype = torch.float16 if DEVICE == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        trust_remote_code=True,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
    )
    model.to(DEVICE)
    model.eval()


def messages_to_prompt(messages: list[ChatMessage]) -> str:
    rows = [{"role": item.role, "content": item.content} for item in messages]
    try:
        return tokenizer.apply_chat_template(rows, tokenize=False, add_generation_prompt=True)
    except Exception:
        prompt_parts: list[str] = []
        for item in rows:
            role = "用户" if item["role"] == "user" else "助手"
            if item["role"] == "system":
                role = "系统"
            prompt_parts.append(f"{role}: {item['content']}")
        prompt_parts.append("助手:")
        return "\n\n".join(prompt_parts)


def build_generate_kwargs(request: ChatCompletionRequest) -> Dict[str, Any]:
    prompt = messages_to_prompt(request.messages)
    inputs = tokenizer(prompt, return_tensors="pt").to(DEVICE)
    do_sample = request.temperature > 0
    eos_token_ids = [tokenizer.eos_token_id]
    for token in ["<|im_end|>", "<|endoftext|>"]:
        token_id = tokenizer.convert_tokens_to_ids(token)
        if isinstance(token_id, int) and token_id >= 0 and token_id not in eos_token_ids:
            eos_token_ids.append(token_id)
    return {
        **inputs,
        "max_new_tokens": request.max_tokens,
        "do_sample": do_sample,
        "temperature": request.temperature if do_sample else None,
        "top_p": request.top_p if do_sample else None,
        "eos_token_id": eos_token_ids,
        "pad_token_id": tokenizer.eos_token_id,
    }


def clean_generate_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    kwargs.pop("token_type_ids", None)
    return {key: value for key, value in kwargs.items() if value is not None}


def completion_payload(text: str, model_name: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
    }


def stream_line(payload: Dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def postprocess_text(text: str) -> str:
    clean = str(text or "").strip()
    index = find_stop_marker_index(clean)
    if index >= 0:
        clean = clean[:index].strip()
    while True:
        new_clean = TRAILING_ROLE_LABEL_RE.sub("", clean).rstrip()
        if new_clean == clean:
            return clean
        clean = new_clean


def find_stop_marker_index(text: str) -> int:
    indexes = [
        index
        for marker in [
            "\n\n用户：",
            "\n用户：",
            "\n\n用户:",
            "\n用户:",
            "\n\n用户",
            "\n用户",
            "\n\n医生：",
            "\n医生：",
            "\n\n医生:",
            "\n医生:",
            "\n\n医生",
            "\n医生",
            "\n\nUser:",
            "\nUser:",
            "\n\n助手：",
            "\n助手：",
            "\n\n助手:",
            "\n助手:",
            "\n\n助手",
            "\n助手",
            "\n\nAssistant:",
            "\nAssistant:",
        ]
        for index in [str(text or "").find(marker)]
        if index >= 0
    ]
    return min(indexes) if indexes else -1


@app.on_event("startup")
def startup() -> None:
    load_model()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "model": MODEL_NAME, "device": DEVICE, "model_dir": MODEL_DIR}


@app.get("/v1/models")
def list_models() -> Dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model"}]}


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="MiniCPM model is not loaded")

    if not request.stream:
        with GENERATION_LOCK:
            kwargs = clean_generate_kwargs(build_generate_kwargs(request))
            try:
                with torch.inference_mode():
                    output_ids = model.generate(**kwargs)
            except torch.cuda.OutOfMemoryError as exc:
                torch.cuda.empty_cache()
                raise HTTPException(status_code=507, detail="MiniCPM CUDA out of memory. Shorten the prompt or retry.") from exc
            input_length = int(kwargs["input_ids"].shape[-1])
            text = postprocess_text(tokenizer.decode(output_ids[0][input_length:], skip_special_tokens=True))
            return completion_payload(text, request.model)

    def events():
        with GENERATION_LOCK:
            kwargs = clean_generate_kwargs(build_generate_kwargs(request))
            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=1.0)
            kwargs["streamer"] = streamer
            errors: List[str] = []

            def run_generation() -> None:
                try:
                    with torch.inference_mode():
                        model.generate(**kwargs)
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    errors.append("MiniCPM CUDA out of memory. Shorten the prompt or retry.")
                except Exception as exc:
                    errors.append(str(exc))

            thread = Thread(target=run_generation)
            thread.start()

            generated = ""
            sent = ""
            stopped = False
            while True:
                try:
                    text = next(streamer)
                except queue.Empty:
                    if thread.is_alive():
                        continue
                    if errors:
                        yield stream_line(
                            {
                                "id": f"chatcmpl-{uuid.uuid4().hex}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": request.model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": errors[0]},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                        )
                    break
                except StopIteration:
                    break
                if not text:
                    continue
                generated += text
                stop_index = find_stop_marker_index(generated)
                if stop_index >= 0:
                    stopped = True
                visible = generated[:stop_index] if stopped else generated
                visible = visible.lstrip()
                if len(visible) <= len(sent):
                    continue
                text = visible[len(sent) :]
                sent = visible
                yield stream_line(
                    {
                        "id": f"chatcmpl-{uuid.uuid4().hex}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": request.model,
                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    }
                )
            thread.join()
            yield stream_line(
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )
            yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
