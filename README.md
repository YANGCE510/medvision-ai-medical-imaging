<h1 align="center">PPGL Assist AI Medical Imaging</h1>

<p align="center">
  面向 PPGL 场景的智能影像辅助分析系统
</p>

<p align="center">
  <b>Vue</b> · <b>Spring Boot</b> · <b>FastAPI</b> · <b>Medical Imaging</b> · <b>RAG</b> · <b>AI Report</b>
</p>

<p align="center">
  <a href="#项目亮点">项目亮点</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#核心功能">核心功能</a> ·
  <a href="#快速启动">快速启动</a> ·
  <a href="#安全设计">安全设计</a>
</p>

<p align="center">
  <img src="docs/assets/cover.png" alt="PPGL Assist AI Medical Imaging cover" width="920">
</p>

PPGL Assist 是一个面向嗜铬细胞瘤/副神经节瘤（PPGL）场景的智能影像辅助分析系统。项目以 CT 病例为入口，整合病例管理、AI 分割推理、三维/二维查看、结构化 AI 报告、RAG 医学知识问答和权限控制，目标是展示一个完整的 AI 医疗影像应用开发闭环。

> 本项目用于工程能力展示和科研原型验证，不提供临床诊断结论，不包含真实临床影像、患者隐私数据或模型权重。

## 项目亮点

- 完整 AI 应用链路：Vue 前端、Spring Boot 业务后端、FastAPI AI 服务分层协作。
- 医疗数据访问控制：Spring Boot 统一处理登录、JWT、角色校验和病例权限，浏览器不直接访问 AI 服务。
- AI 能力解耦：全器官分割与 PPGL 肿瘤分割拆分为独立能力，便于替换模型和扩展推理流程。
- 自研模型接入：已将 ProgressPatchV5 推理代码纳入仓库，支持通过相对路径加载权重。
- RAG 问答与报告生成：支持医学知识库检索、病例上下文组装、报告生成和报告问答。
- 求职展示友好：代码仓库排除了权重、医学影像、运行结果、日志、构建产物和私有配置。

## 系统架构

```text
Vue Web（5173）
  └─ 负责页面展示、交互和调用 Spring Boot 公开 API
       ↓ /api
Spring Boot（8080）
  ├─ 唯一公开业务后端
  ├─ 登录、JWT、角色权限、病例权限、业务数据
  └─ AI 网关：使用内部密钥和受信用户上下文调用 FastAPI
       ↓ /api（建议仅内网/本机访问）
FastAPI（8000）
  └─ 负责 AI 能力：全器官分割、PPGL 分割、指标、三维产物、RAG、AI 报告
```

职责边界：

- Vue：只做用户界面，不保存密钥，不直接操作病例文件。
- Spring Boot：作为唯一公开业务入口，负责鉴权、权限、病例与报告业务。
- FastAPI：作为内部 AI 服务，负责推理、RAG、报告生成和 AI 文件产物管理。

## 核心功能

- 医生/患者/管理员登录与角色区分
- CT 病例上传、病例列表、病例详情
- 病例权限隔离与文件网关访问
- 全器官分割任务
- PPGL 肿瘤分割任务
- 分割结果指标展示
- 2D/3D 医学影像查看
- AI 辅助报告生成
- 报告问答与流式输出
- RAG 医学知识库检索与评估样例
- 患者微信小程序原型

## 目录结构

```text
.
├── frontend-vue-prototype/  # Vue 3 + Vite Web 前端
├── frontend-javaweb/        # Spring Boot 业务后端、静态页面、小程序原型
├── ai-backend/              # FastAPI AI 服务、RAG、报告、ProgressPatchV5 推理
├── pipeline-otafv2/         # OTAFV2 推理流水线
├── envs/                    # Conda 推理环境配置
├── docs/                    # 项目状态说明
├── WEIGHTS_AND_DATA.md      # 权重和数据放置说明
└── .gitignore               # 排除隐私数据、权重、日志和构建产物
```

## 环境要求

- JDK 21
- Maven
- MySQL
- Node.js / npm
- Conda / Python 3.10
- PyTorch、MONAI、nnUNetv2、nibabel、SimpleITK、scikit-image 等推理依赖

GPU 推理环境可参考：

```bash
conda env create -f envs/environment.inference.yml
conda activate ppgl
```

CPU/Jetson CPU 环境可参考：

```bash
conda env create -f envs/environment.inference.jetson-cpu.yml
conda activate ppgl
```

## 快速启动

### 1. 启动 FastAPI AI 服务

```bash
cd ai-backend/backend

export PPGL_INTERNAL_API_KEY=change-this-in-local-env

uvicorn main:app --host 127.0.0.1 --port 8000
```

### 2. 启动 Spring Boot 业务后端

```bash
cd frontend-javaweb

export MYSQL_USER=root
export MYSQL_PASSWORD=your_mysql_password
export PPGL_AUTH_JWT_SECRET=change-this-to-a-random-string-at-least-32-bytes
export PPGL_INTERNAL_API_KEY=change-this-in-local-env

mvn spring-boot:run
```

访问 Spring Boot：

```text
http://127.0.0.1:8080/
```

数据库建表脚本：

```text
frontend-javaweb/src/main/resources/schema.sql
```

### 3. 启动 Vue Web 前端

```bash
cd frontend-vue-prototype

npm install
npm run dev
```

访问 Vue：

```text
http://127.0.0.1:5173/
```

## 模型权重与医学数据

公开仓库不包含模型权重、真实医学影像和运行输出。完整运行推理前，需要在本地准备以下资产：

- ProgressPatchV5 PPGL 分割权重，默认位置：`ai-backend/progress_patch_v5/weights/model_best.pth`
- OTAFV2 / nnUNet / TotalSegmentator 所需权重和运行环境
- 已授权、已脱敏的 `.nii.gz` 测试影像

ProgressPatchV5 也支持通过环境变量覆盖模型路径：

```bash
export PPGL_V5_CHECKPOINT=ai-backend/progress_patch_v5/weights/model_best.pth
```

更多说明见 [WEIGHTS_AND_DATA.md](WEIGHTS_AND_DATA.md)。

## 安全设计

- 前端不保存后端内部密钥。
- Vue 只访问 Spring Boot 公开 API。
- Spring Boot 负责用户认证、JWT 签发、角色判断和病例权限控制。
- FastAPI 使用内部 API Key 和受信用户上下文，不作为公网直接入口。
- `.gitignore` 已排除 `.env`、证书、权重、医学影像、上传目录、任务目录、日志、缓存和构建产物。

公开部署前建议：

- 使用强随机 `PPGL_AUTH_JWT_SECRET` 和 `PPGL_INTERNAL_API_KEY`。
- 不提交真实病例、真实患者信息、模型权重和私有配置。
- 将 FastAPI 限制在内网或本机访问。
- 对公开仓库执行密钥扫描。

## 当前状态

本仓库当前重点展示 AI 应用开发能力，包括：

- 前后端业务闭环
- AI 服务网关化接入
- 医学影像推理流程封装
- 自研分割模型推理集成
- RAG 与 AI 报告能力
- 医疗数据访问控制意识

仍需根据实际部署环境补齐外部模型权重、测试影像、数据库和推理依赖。
