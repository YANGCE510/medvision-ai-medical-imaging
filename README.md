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
  <a href="#部署规则">部署规则</a> ·
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
- 自研模型接入：已将 PPGL 肿瘤分割推理代码纳入仓库，支持通过相对路径加载权重。
- 独立 3D 可视化：全器官与 PPGL 肿瘤均生成独立 mesh，可联合加载；历史病例会按需补生成肿瘤 mesh。
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
- 病例删除、编号修改，以及失败任务的强制重试
- 病例权限隔离与文件网关访问
- 全器官分割任务
- PPGL 肿瘤分割任务
- 分割结果指标展示
- 2D/3D 医学影像查看
- 3D 结构中文显示与肿瘤优先展示
- AI 辅助报告生成
- 报告问答与流式输出
- RAG 医学知识库检索与评估样例
- 患者微信小程序原型

## 目录结构

```text
.
├── frontend-vue-prototype/  # Vue 3 + Vite Web 前端
├── frontend-javaweb/        # Spring Boot 业务后端、静态页面、小程序原型
├── ai-backend/              # FastAPI AI 服务、RAG、报告、全器官与 PPGL 分割推理
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

先复制配置模板并指定项目外的数据目录。运行数据、上传文件、病例产物、RAG 索引和日志都应放在这里，不要和代码仓库混在一起。

```bash
cp .env.example .env
# 编辑 .env：填写 MYSQL_PASSWORD、PPGL_AUTH_JWT_SECRET、PPGL_INTERNAL_API_KEY，
# 并将 PPGL_DATA_ROOT 改为本机项目外的可写目录。

set -a
source .env
set +a

mkdir -p "$PPGL_DATA_ROOT"/{uploads,jobs,cases,logs,rag-documents,rag-index,rag-parsed}
```

真实 `.env` 不要提交到 Git。

### 1. 启动 AI 服务和 Vue 前端

```bash
set -a
source .env
set +a

bash ai-backend/start_ppgl_ai.sh
```

该脚本会启动 Ollama、FastAPI（8000）和 Vue（5173）。需要先在 `ppgl` Conda 环境中安装 TotalSegmentator，并在本机准备配置的 Ollama 模型。

### 2. 启动 Spring Boot 业务后端

```bash
set -a
source .env
set +a

cd frontend-javaweb
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

### 3. 初始化 RAG 知识库（首次运行）

```bash
cd frontend-vue-prototype
cp --update=none ../ai-backend/knowledge_base/documents/* "$PPGL_DATA_ROOT/rag-documents/"

cd ../ai-backend
python -m backend.rag.build_chunks \
  --documents "$PPGL_DATA_ROOT/rag-documents" \
  --output "$PPGL_DATA_ROOT/rag-parsed/chunks.jsonl"

python -c 'from backend.rag.vector_store import build_vector_index; print(build_vector_index(device="cuda", batch_size=16))'
```

如无 GPU，可将 `device="cuda"` 改为 `device="cpu"`，但构建会明显更慢。构建完成后刷新知识库页面即可使用。

访问地址：

```text
http://127.0.0.1:5173/
```

## 模型权重与医学数据

公开仓库不包含模型权重、真实医学影像和运行输出。完整运行推理前，需要在本地准备以下资产：

- PPGL 分割权重，默认位置：`ai-backend/progress_patch_v5/weights/model_best.pth`。该权重暂不随代码仓库发布，后续将上传至 Hugging Face，并在此处补充下载链接。
- TotalSegmentator 所需权重和运行环境
- 已授权、已脱敏的 `.nii.gz` 测试影像

PPGL 分割运行时也支持通过环境变量覆盖模型路径：

```bash
export PPGL_V5_CHECKPOINT=ai-backend/progress_patch_v5/weights/model_best.pth
```

更多说明见 [WEIGHTS_AND_DATA.md](WEIGHTS_AND_DATA.md)。

## 数据目录规范

代码仓库只放源码、配置模板、依赖文件、数据库迁移/建表脚本和项目说明。数据库、上传文件、病例推理产物、RAG 索引、日志和真实 `.env` 都属于运行资产，应放在项目外部目录。

推荐结构：

```text
$PPGL_DATA_ROOT/
├── uploads/        # Java 端上传文件和查看器病例文件
├── jobs/           # Java 端分析任务状态
├── cases/          # FastAPI AI 病例工作区
├── logs/           # 启动脚本和服务日志
├── rag-documents/  # RAG 原始知识文档
├── rag-index/      # Qdrant 本地索引
└── rag-parsed/     # RAG 切块结果
```

默认情况下，服务会使用 `~/ppgl-assist-data`。如果要放到大硬盘，启动前设置：

```bash
export PPGL_DATA_ROOT=/mnt/20T/ppgl-assist-data
```

## 部署规则

本项目支持本地开发和单机/内网部署，但两者必须使用不同配置。不要把开发机的 `127.0.0.1`、`/mnt/20T` 或模型路径直接带到服务器。

| 配置项 | 本地开发示例 | 线上部署示例 |
| --- | --- | --- |
| `PPGL_DATA_ROOT` | `/mnt/20T/ppgl-assist-data` | `/var/lib/ppgl-assist` |
| `MYSQL_HOST` | `127.0.0.1` | `mysql` 或数据库内网 IP |
| `PPGL_PIPELINE_BASE_URL` | `http://127.0.0.1:8000` | `http://ai-service:8000` |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8080` | `http://java-service:8080` |
| `CHAT_OPENAI_BASE_URL` | `http://127.0.0.1:11434/v1` | 内网 LLM 服务地址 |

### 本地开发

复制配置模板并按自己的机器修改。Shell 启动前需要导出变量；`ai-backend/start_ppgl_ai.sh` 会自动读取仓库根目录或 `ai-backend/.env`。

```bash
cp .env.example .env
# 编辑 .env：至少填写 MYSQL_PASSWORD、PPGL_AUTH_JWT_SECRET、PPGL_INTERNAL_API_KEY，
# 并将 PPGL_DATA_ROOT 改为本机项目外的可写目录。

set -a
source .env
set +a
```

随后按“快速启动”中的 FastAPI、Spring Boot、Vue 顺序启动。Vue 开发服务器通过 `VITE_API_PROXY_TARGET` 转发 `/api` 到 Spring Boot；浏览器不直接访问 FastAPI。

### 单机/内网服务器部署

1. 创建专用运行用户和数据目录，运行用户必须拥有数据目录和模型目录的读写权限。

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin ppgl || true
sudo install -d -o ppgl -g ppgl /var/lib/ppgl-assist/{uploads,jobs,cases,logs,rag-documents,rag-index,rag-parsed}
sudo install -d -o ppgl -g ppgl /etc/ppgl-assist
sudo cp .env.example /etc/ppgl-assist/ppgl-assist.env
sudo chmod 600 /etc/ppgl-assist/ppgl-assist.env
sudo chown ppgl:ppgl /etc/ppgl-assist/ppgl-assist.env
```

2. 编辑 `/etc/ppgl-assist/ppgl-assist.env`：使用 `/var/lib/ppgl-assist`，填写真实密钥和数据库地址；若 AI、MySQL、LLM 不在同一台机器，填写其内网 DNS 或 IP。不要把 FastAPI 的 `8000` 端口暴露到公网。

3. 以 `ppgl` 用户启动服务时加载该文件：

```bash
set -a
source /etc/ppgl-assist/ppgl-assist.env
set +a
```

启动 Java 时以上环境变量会自动映射到 `application.properties`；启动 Vue 开发服务时 `VITE_API_PROXY_TARGET` 会映射代理目标。生产 Web 前端应由 Nginx 托管构建产物，并将 `/api` 反向代理到 Spring Boot；Nginx 是唯一对公网开放的入口。

4. 部署前检查：服务器能连接 `MYSQL_HOST:MYSQL_PORT`，`PPGL_DATA_ROOT` 与 `TOTALSEG_WEIGHTS_PATH` 可被 `ppgl` 用户访问，且 FastAPI、Java、LLM 服务之间的内网地址可达。

## 安全设计

- 前端不保存后端内部密钥。
- Vue 只访问 Spring Boot 公开 API。
- Spring Boot 负责用户认证、JWT 签发、角色判断和病例权限控制。
- FastAPI 使用内部 API Key 和受信用户上下文，不作为公网直接入口。
- `.gitignore` 已排除 `.env`、证书、权重、医学影像、上传目录、任务目录、日志、缓存和构建产物。
- 数据库和运行数据不作为代码仓库的一部分管理。

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
