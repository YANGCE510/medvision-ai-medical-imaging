# PPGL Assist：智能影像辅助分析系统


## 功能概览

- CT 病例上传与任务管理
- PPGL 肿瘤及相关解剖结构分割推理
- 分割结果、量化指标与三维查看
- AI 辅助报告与报告问答
- 医生端/患者端基础业务页面
- 患者微信小程序原型

## 系统边界

```text
Vue Web（5173）
  └─ 只负责页面、交互和调用 Spring Boot 公开 API
       ↓ /api
Spring Boot（8080）
  ├─ 唯一公开业务后端：登录、JWT、角色、病例权限、业务数据
  └─ AI 网关：使用内部密钥和受信用户上下文调用 FastAPI
       ↓ /api（仅本机内部访问）
FastAPI（127.0.0.1:8000）
  └─ 只负责 AI：全器官/PPGL 推理、指标、三维产物、RAG 和 AI 报告
```

浏览器不再直接访问 FastAPI。Vue 中的 AI 请求使用 `/api/ai/**`，由 Spring Boot
完成登录和角色检查后转发。FastAPI 中的病例目录是 AI 任务工作区，不是用户或业务数据库。

## 目录结构

```text
PPGL_upload_ready/
├── frontend-javaweb/        # JavaWeb/Spring Boot 主项目、静态前端、小程序代码
├── frontend-vue-prototype/  # Vue3/Vite Web 前端原型
├── ai-backend/              # FastAPI 推理服务、报告接口、Jetson 节点封装
├── pipeline-otafv2/         # OTAFV2 推理流水线源码
├── envs/                    # 推理环境 Conda 配置
└── .gitignore               # 防止误传权重、影像、日志和缓存
```

## 环境要求

按实际运行的模块分别准备环境：

- JavaWeb 主项目：JDK 21、Maven、MySQL。
- Vue 前端原型：Node.js 与 npm。
- AI 后端与 OTAFV2 推理：Conda、Python 3.10、PyTorch 2.5.1、MONAI、nnUNetv2、nibabel、SimpleITK、scikit-image 等。
- GPU 推理环境：参考 `envs/environment.inference.yml`，默认包含 `pytorch-cuda=12.1`。
- CPU/Jetson CPU 推理环境：参考 `envs/environment.inference.jetson-cpu.yml`。
- 完整分割推理还需要 TotalSegmentator/nnUNet 对应运行环境和外部模型权重。

Conda 环境创建示例：

```bash
conda env create -f envs/environment.inference.yml
conda activate ppgl
```

CPU/Jetson CPU 环境示例：

```bash
conda env create -f envs/environment.inference.jetson-cpu.yml
conda activate ppgl
```

## 快速运行 JavaWeb 主项目

```bash
cd frontend-javaweb

export MYSQL_USER=root
export MYSQL_PASSWORD=your_mysql_password

mvn spring-boot:run
```

访问：

```text
http://127.0.0.1:8080/
```

数据库建表脚本：

```text
frontend-javaweb/src/main/resources/schema.sql
```

主要配置文件：

```text
frontend-javaweb/src/main/resources/application.properties
```

默认 AI 推理服务地址示例：

```properties
ppgl.pipeline.base-url=http://127.0.0.1:8000
ppgl.llm.chat-url=http://127.0.0.1:8000/api/llm/chat/stream
```

部署到 Jetson 或服务器时，请按实际地址修改上述配置。

## 启动 AI 后端

```bash
cd ai-backend/backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

完整推理需要另外准备模型权重、TotalSegmentator/nnUNet 运行环境，以及合法授权、已脱敏的测试影像。具体说明见 `WEIGHTS_AND_DATA.md`。

ProgressPatchV5 推理源码已收录在 `ai-backend/progress_patch_v5/`，默认从项目内相对路径
`ai-backend/progress_patch_v5/weights/model_best.pth` 加载权重。也可使用
`PPGL_V5_MODEL_DIR`、`PPGL_V5_CHECKPOINT` 和 `PPGL_V5_MODEL_CONFIG` 覆盖；相对值会基于项目目录或模型目录解析。

## Vue Web 前端

启动唯一的 Web 前端：

```bash
cd frontend-vue-prototype
npm install
npm run dev
```

浏览器访问 Vite 输出的本地地址，通常为：

```text
http://127.0.0.1:5173/
```
