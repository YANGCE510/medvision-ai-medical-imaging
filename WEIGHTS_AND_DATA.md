# 权重与数据说明

本提交目录只包含源码和可公开说明文件，不包含比赛/临床相关私有影像，也不包含模型权重。

## 需要外部提供的资产

如需完整运行 AI 推理，需要准备：

- PPGL/GCPV5 肿瘤分割权重，例如放到 `ai-backend/ckpt/model_best_160.pth`
- OTAFV2 相关 raw GCP、organ tune、adrenal specialist 权重，例如放到 `pipeline-otafv2/checkpoints/`
- TotalSegmentator/nnUNet 权重和对应运行环境
- 已授权、已脱敏的 `.nii.gz` 测试影像

这些文件不应直接提交到公开代码仓库。

## 为什么不上传

- 医学影像和模型权重属于隐私/敏感数据。
- 运行输出中可能包含病例 ID、影像空间信息或诊断相关结果，不适合作为公开代码的一部分。
