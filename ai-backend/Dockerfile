FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        gltfpack \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
        TotalSegmentator==2.11.0 \
        fastapi==0.141.1 \
        matplotlib==3.10.6 \
        monai==1.5.1 \
        nibabel==5.3.2 \
        nnunetv2==2.6.2 \
        numpy==1.26.4 \
        pandas==2.3.2 \
        Pillow==12.0.0 \
        PyJWT==2.10.1 \
        python-multipart==0.0.32 \
        qdrant-client==1.19.0 \
        rank-bm25==0.2.2 \
        scikit-image==0.25.2 \
        scikit-learn \
        scipy==1.15.2 \
        sentence-transformers==6.0.0 \
        SimpleITK==2.5.2 \
        tqdm==4.67.3 \
        uvicorn==0.52.4 \
        vtk==9.3.1

WORKDIR /app/ai-backend
COPY ai-backend/ /app/ai-backend/
COPY docs/model-evaluation/rag_evaluation*.json /app/docs/model-evaluation/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PPGL_DATA_ROOT=/var/lib/ppgl-assist \
    TOTALSEG_WEIGHTS_PATH=/models/totalsegmentator/nnunet/results \
    PPGL_V5_CHECKPOINT=/models/ppgl/weights/model_best.pth \
    PPGL_GLIOMA_MODEL_DIR=/var/lib/ppgl-assist/models/brain-glioma/nnUNetTrainer__nnUNetPlans__3d_fullres

WORKDIR /app/ai-backend/backend
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
