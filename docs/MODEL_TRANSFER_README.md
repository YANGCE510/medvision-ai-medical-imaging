# MedVision AI Workbench 模型包使用说明

## 模型包内容

```text
MedVision-Windows-模型包/
├── README.md
├── SHA256SUMS.txt
├── ppgl/
│   └── weights/
│       └── model_best.pth
└── totalsegmentator/
    └── nnunet/
        └── results/
            ├── Dataset291_TotalSegmentator_part1_organs_1559subj/
            ├── Dataset292_TotalSegmentator_part2_vertebrae_1532subj/
            ├── Dataset293_TotalSegmentator_part3_cardiac_1559subj/
            ├── Dataset294_TotalSegmentator_part4_muscles_1559subj/
            ├── Dataset295_TotalSegmentator_part5_ribs_1559subj/
            ├── Dataset298_TotalSegmentator_total_6mm_1559subj/
            └── Dataset300_body_6mm_1559subj/
```

本模型包只包含 PPGL 分割权重和当前项目使用的 TotalSegmentator 权重，不包含医学影像、病例、数据库、账号、日志或项目密钥。

Linux 参考环境版本：

- TotalSegmentator 2.11.0
- nnUNetv2 2.6.2
- PyTorch 2.5.1 + CUDA 12.1

Windows 可以根据实际显卡和驱动选择兼容的 PyTorch/CUDA 版本，但应优先保持 TotalSegmentator 与 nnUNetv2 版本一致。

## Windows 放置位置

将整个模型包复制到仓库外，例如：

```text
D:\MedVisionModels
```

不要把模型权重复制进 Git 仓库，也不要执行 `git add -f` 强制提交权重。

## 配置项目

在项目根目录的本地 `.env` 中加入或修改：

```dotenv
PPGL_V5_CHECKPOINT=D:/MedVisionModels/ppgl/weights/model_best.pth
TOTALSEG_WEIGHTS_PATH=D:/MedVisionModels/totalsegmentator/nnunet/results
```

Windows 的 `.env` 路径建议使用 `/`，避免反斜杠转义问题。

PPGL 的推理代码和模型配置已经包含在 Git 仓库中，因此只需要额外配置 `model_best.pth`。不要修改 `model_config.json`，除非权重确实由不同配置训练。

TotalSegmentator Python 包仍需安装到项目 Python 环境中。本模型包只用于离线提供权重，不代替 Python 包安装。

## PowerShell 检查

```powershell
Test-Path "D:/MedVisionModels/ppgl/weights/model_best.pth"
Get-ChildItem "D:/MedVisionModels/totalsegmentator/nnunet/results" -Directory

python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
TotalSegmentator --help
```

第一条命令应返回 `True`，TotalSegmentator 目录应显示 Dataset291–295、Dataset298 和 Dataset300。

如果已安装 Git for Windows，可以在 Git Bash 中验证传输完整性：

```bash
cd /d/MedVisionModels
sha256sum -c SHA256SUMS.txt
```

全部文件应显示 `OK`。

## 功能验收

配置完成并启动全部服务后，至少验证：

1. 上传一个已授权、已脱敏的 CT 病例。
2. 单独执行全器官分割并查看切片和三维模型。
3. 单独执行 PPGL 肿瘤分割。
4. 在联合阅片中确认 PPGL 肿瘤可以独立显示和隐藏。
5. 重启服务后确认病例和结果仍然存在。

如果 TotalSegmentator 提示缺少其他 Dataset，先记录所选模式、完整错误和缺少的数据集编号，再向项目负责人确认；不要让程序在不明确来源的情况下自动下载或替换现有权重。

## 注意事项

- 权重仅限项目授权范围内使用和传递。
- TotalSegmentator 的软件和模型使用应遵守其官方许可条款。
- 不要复制发送者机器上的 `~/.totalsegmentator/config.json`，接收者应在自己的环境中生成本机配置。
- 不要把模型目录、病例目录或数据库放在项目源码目录内。
