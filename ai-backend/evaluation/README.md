# MedVision AI Workbench 评测工具

本目录的脚本用于工程评测，不用于临床诊断。医学影像、标签、预测掩膜、病例清单、原始模型回答和含本地路径的结果必须保存到仓库外。

## 脱敏 PPGL 病例与报告评测

以下命令以 6 个按肿瘤体积分位数选择的 PPGL 病例为第一轮集合。评测目录不在 Git 仓库内。

```bash
set -a
source .env
set +a

conda run -n ppgl python ai-backend/evaluation/run_deidentified_ppgl_report_evaluation.py \
  --images-dir /mnt/20T/PPGL/ALL_PUMCH_mutil/images \
  --labels-dir /mnt/20T/PPGL/ALL_PUMCH_mutil/labels_ablation_tumor_only \
  --evaluation-root /mnt/20T/ppgl-assist-data/evaluations/ppgl_report_20260828 \
  --case-ids PPGL_Tr_0088 PPGL_Tr_0132 PPGL_Tr_0161 PPGL_Tr_0106 PPGL_Tr_0145 PPGL_Tr_0021 \
  --models ppgl-qwen3-32b-q4:latest
```

输出中的 Dice、Precision、Recall 和体积误差评估 PPGL 肿瘤分割。报告评分只检查原始模型输出是否忠实复述分割事实并保留安全提示，是规则辅助代理评分，不是临床专家评分。

## 20 题 RAG 引用评测

```bash
set -a
source .env
set +a

python ai-backend/evaluation/run_rag_evaluation.py \
  --output-json docs/model-evaluation/rag_evaluation_20260828.json \
  --output-markdown docs/model-evaluation/rag_evaluation_20260828.md
```

题库位于 `rag_evaluation_cases.json`，检查预期文献是否被检索到、回答是否具有有效引用编号，以及预期文献是否被回答引用。

## 并发稳定性评测

```bash
set -a
source .env
set +a

python ai-backend/evaluation/run_concurrency_evaluation.py \
  --levels 1 3 5 \
  --repeats 2 \
  --output-json docs/model-evaluation/rag_concurrency_20260828.json \
  --output-markdown docs/model-evaluation/rag_concurrency_20260828.md
```

该测试只记录 API 状态和延迟，不保存回答文本、病例或密钥。
