from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import torch


SYSTEM_TRT_SITE_PACKAGES = Path("/usr/lib/python3.8/dist-packages")


def import_tensorrt() -> Any:
    try:
        import tensorrt as trt  # type: ignore

        return trt
    except ModuleNotFoundError:
        if SYSTEM_TRT_SITE_PACKAGES.exists() and str(SYSTEM_TRT_SITE_PACKAGES) not in sys.path:
            sys.path.append(str(SYSTEM_TRT_SITE_PACKAGES))
        try:
            import tensorrt as trt  # type: ignore

            return trt
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "TensorRT Python package is not importable. On this Jetson it is usually available under "
                "/usr/lib/python3.8/dist-packages; set PYTHONPATH or install TensorRT bindings in ppgl-gpu38."
            ) from exc


def torch_dtype_from_trt(trt: Any, dtype: Any) -> torch.dtype:
    if dtype == trt.float32:
        return torch.float32
    if dtype == trt.float16:
        return torch.float16
    if dtype == trt.int32:
        return torch.int32
    if dtype == trt.int8:
        return torch.int8
    if hasattr(trt, "bool") and dtype == trt.bool:
        return torch.bool
    raise RuntimeError(f"Unsupported TensorRT dtype: {dtype}")


class TensorRTPredictor:
    """Callable MONAI sliding-window predictor backed by a fixed-shape TensorRT engine."""

    def __init__(self, engine_path: str | Path):
        self.engine_path = Path(engine_path).expanduser()
        if not self.engine_path.exists():
            raise FileNotFoundError(f"TensorRT engine not found: {self.engine_path}")
        if not torch.cuda.is_available():
            raise RuntimeError("TensorRT backend requires CUDA.")

        self.trt = import_tensorrt()
        logger = self.trt.Logger(self.trt.Logger.WARNING)
        if hasattr(self.trt, "init_libnvinfer_plugins"):
            self.trt.init_libnvinfer_plugins(logger, "")
        runtime = self.trt.Runtime(logger)
        engine_bytes = self.engine_path.read_bytes()
        self.engine = runtime.deserialize_cuda_engine(engine_bytes)
        if self.engine is None:
            raise RuntimeError(f"Failed to deserialize TensorRT engine: {self.engine_path}")
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError(f"Failed to create TensorRT execution context: {self.engine_path}")

        self.input_indices = [i for i in range(self.engine.num_bindings) if self.engine.binding_is_input(i)]
        self.output_indices = [i for i in range(self.engine.num_bindings) if not self.engine.binding_is_input(i)]
        if len(self.input_indices) != 1 or len(self.output_indices) != 1:
            raise RuntimeError(
                f"Expected one input and one output binding, got {len(self.input_indices)} inputs "
                f"and {len(self.output_indices)} outputs."
            )
        self.input_index = self.input_indices[0]
        self.output_index = self.output_indices[0]
        self.input_name = self.engine.get_binding_name(self.input_index)
        self.output_name = self.engine.get_binding_name(self.output_index)

    def __call__(self, x: torch.Tensor) -> torch.Tensor:
        if not x.is_cuda:
            raise RuntimeError("TensorRT predictor expects CUDA input tensors.")
        if x.dtype != torch.float32:
            x = x.float()
        x = x.contiguous()
        input_shape = tuple(int(v) for v in x.shape)

        if self.engine.is_shape_binding(self.input_index) or -1 in tuple(self.engine.get_binding_shape(self.input_index)):
            if not self.context.set_binding_shape(self.input_index, input_shape):
                raise RuntimeError(f"TensorRT rejected input shape for {self.input_name}: {input_shape}")
        else:
            engine_shape = tuple(int(v) for v in self.engine.get_binding_shape(self.input_index))
            if engine_shape != input_shape:
                raise RuntimeError(
                    f"TensorRT engine input shape mismatch for {self.input_name}: "
                    f"engine={engine_shape}, request={input_shape}"
                )

        output_shape = tuple(int(v) for v in self.context.get_binding_shape(self.output_index))
        if any(v < 0 for v in output_shape):
            raise RuntimeError(f"TensorRT output shape is unresolved for {self.output_name}: {output_shape}")
        output_dtype = torch_dtype_from_trt(self.trt, self.engine.get_binding_dtype(self.output_index))
        output = torch.empty(output_shape, device=x.device, dtype=output_dtype)

        bindings = [0] * int(self.engine.num_bindings)
        bindings[self.input_index] = int(x.data_ptr())
        bindings[self.output_index] = int(output.data_ptr())

        torch.cuda.synchronize()
        ok = self.context.execute_v2(bindings)
        torch.cuda.synchronize()
        if not ok:
            raise RuntimeError(f"TensorRT execution failed for engine: {self.engine_path}")
        return output.float() if output.dtype != torch.float32 else output
