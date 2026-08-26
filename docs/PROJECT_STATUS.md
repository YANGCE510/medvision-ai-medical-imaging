# PROJECT STATUS

## 当前基线

- Git 基线范围：本目录（`代码/`）中的源码、依赖描述、构建配置和说明文件。
- 当前目录不包含模型权重、医学影像病例、推理输出或日志；这些运行资产已由根目录 `.gitignore` 排除。
- 本文仅记录现状，不改变业务、模型或部署逻辑。

## 架构概览

```text
frontend-javaweb (Spring Boot + MySQL)
  ├─ 医生/患者/管理员接口、病例与报告管理、静态 Web 页面
  ├─ patient-miniprogram 微信小程序原型
  └─ HTTP 调用 ai-backend 的分析与报告问答接口

frontend-vue-prototype (Vue 3 + Vite)
  └─ 独立 Web 原型

ai-backend (FastAPI)
  ├─ 病例任务、文件管理、推理编排与结果服务
  ├─ AI 报告生成与流式问答
  └─ Jetson/MiniCPM 节点启动封装

pipeline-otafv2
  ├─ raw GCP 肿瘤分割
  ├─ organ tune 与 TotalSegmentator 解剖分割
  ├─ APR 过滤与结果融合
  └─ adrenal specialist（nnUNet）推理

envs/
  └─ GPU 与 Jetson CPU 的 Conda 环境描述
```

## 已知部署阻塞点

| 阻塞项 | 依据 | 部署前需要提供或完成的内容 |
| --- | --- | --- |
| 模型权重和推理引擎未随代码提交 | `WEIGHTS_AND_DATA.md` 及 OTAFV2 配置引用 `ckpt/`、`checkpoints/`、`models/`、`engines/` | 在受控位置提供已授权权重、TensorRT 引擎（如使用）及其路径配置。 |
| TotalSegmentator/nnUNet 运行资产缺失 | 推理代码需要 TotalSegmentator/nnUNet 可执行环境、预训练权重和相关目录 | 安装对应工具并配置权重、`nnUNet_*` 目录和命令可用性。 |
| FastAPI 服务依赖没有单独的锁定依赖文件 | 环境 YAML 只声明了推理栈；`ai-backend/backend/main.py` 导入 FastAPI/Uvicorn 运行所需组件 | 在目标 Conda 环境中补齐并验证 FastAPI、Uvicorn 及服务所需的 Python 包。 |
| ProgressPatchV5 权重不随仓库提交 | 默认从 `ai-backend/progress_patch_v5/weights/model_best.pth` 加载 | 在部署环境放置已授权权重，或使用 `PPGL_V5_CHECKPOINT` 覆盖相对路径。 |
| Java 主应用依赖外部 MySQL，且自动建表关闭 | `application.properties` 使用 MySQL，`spring.sql.init.mode=never` | 创建数据库并执行/管理 `schema.sql`，提供 `MYSQL_USER`、`MYSQL_PASSWORD` 与可访问的数据库实例。 |
| 合规测试影像未包含 | 根目录说明明确不提交病例和医学影像 | 在部署环境挂载或导入已授权、已脱敏的测试/生产影像，并落实访问控制。 |

## Git 提交边界

应提交：源码、`pom.xml`、`package.json`/`package-lock.json`、Conda 环境文件、默认配置、SQL 建表脚本和项目说明。

不应提交：`.env` 与私有小程序配置、证书和密钥、模型权重/推理引擎、医学影像与病例数据、上传目录、任务目录、数据库文件、日志、缓存与构建产物。

## 公开前后续事项

- [ ] 移除 Vue 原型登录页中的默认演示密码。
- [ ] 在公开发布前，对拟提交内容执行更完整的密钥扫描，并处理扫描发现项。
