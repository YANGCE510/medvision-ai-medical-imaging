<h1 align="center">PPGL Assist AI Medical Imaging</h1>

<p align="center">
  面向嗜铬细胞瘤与副神经节瘤场景的智能影像辅助分析系统
</p>

<p align="center">
  <b>CT 病例管理</b> · <b>全器官分割</b> · <b>PPGL 肿瘤分割</b> · <b>2D/3D 阅片</b> · <b>AI 报告</b> · <b>医学知识问答</b>
</p>

<p align="center">
  <a href="#项目简介">项目简介</a> ·
  <a href="#主要功能">主要功能</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#使用说明">使用说明</a> ·
  <a href="#模型与数据">模型与数据</a> ·
  <a href="#部署与安全">部署与安全</a>
</p>

<p align="center">
  <img src="docs/assets/cover.png" alt="PPGL Assist 系统封面" width="920">
</p>

## 项目简介

PPGL Assist 以 CT 病例为入口，为 PPGL 相关影像分析提供一套完整的使用流程：上传影像、分别执行全器官分割和 PPGL 肿瘤分割、查看二维与三维结果、读取量化指标，并生成结构化 AI 辅助报告。系统还提供医学知识检索与病例报告问答功能。

系统的主要操作界面面向医生使用。患者端提供已审核报告查看与反馈原型，管理员角色用于权限区分。

> 本项目用于科研与教学场景的原型验证，不提供临床诊断结论。公开仓库不包含真实临床影像、患者隐私数据或模型权重。

## 主要功能

| 功能 | 使用说明 |
| --- | --- |
| 病例管理 | 上传 CT、查看病例列表与详情、修改病例编号、删除病例，并可重新执行失败的分割任务。 |
| 全器官分割 | 对 CT 中的主要解剖结构进行自动分割，生成结构标签、体积指标和三维模型。 |
| PPGL 肿瘤分割 | 使用独立的 PPGL 分割模型生成肿瘤掩膜、体积、最大径和三维肿瘤模型。该任务不依赖全器官分割结果。 |
| 2D/3D 阅片 | 在二维切片中查看 CT 与分割叠加结果，在三维视图中独立或联合显示器官和 PPGL 肿瘤。 |
| AI 辅助报告 | 根据病例分割结果和量化指标，按照固定结构生成辅助分析报告。 |
| 报告问答 | 围绕当前病例报告继续提问，并通过流式输出查看回答。 |
| 医学知识问答 | 从本地 PPGL 医学知识库检索相关资料，并结合检索结果回答问题。 |
| 访问控制 | 通过登录认证、角色权限和病例归属限制病例、影像与报告的访问范围。 |

全器官分割和 PPGL 肿瘤分割是两个独立功能。使用者可以只运行其中一个，也可以全部运行后进行联合阅片。

## 典型使用流程

1. 使用医生账号登录系统。
2. 上传 `.nii.gz` 格式的 CT 影像并创建病例。
3. 在病例详情页按需启动“全器官分割”或“PPGL 肿瘤分割”。
4. 等待任务状态显示“全器官分割完成”或“PPGL：肿瘤分割完成”。
5. 查看分割指标、二维切片和三维模型；两个任务均完成后可进行联合阅片。
6. 生成结构化 AI 辅助报告，并围绕报告内容继续问答。

## 运行前准备

推荐在 Linux 环境中运行。完整 AI 推理建议使用支持 CUDA 的 NVIDIA GPU。

需要提前安装：

- JDK 21（必须是 JDK，不能只有 JRE）
- Maven
- MySQL 8.x
- Node.js 20 或更高版本、npm
- Conda
- Ollama，或其他兼容 OpenAI API 的本地大模型服务

可以先检查基础环境：

```bash
java -version
javac -version
mvn -version
mysql --version
node --version
npm --version
conda --version
ollama --version
```

完整推理还需要：

- PPGL 分割权重
- 全器官分割所需权重
- 已授权并完成脱敏的 CT 测试影像

## 快速开始

以下命令以 Ubuntu/Linux 和单机运行环境为例。

### 1. 获取项目

```bash
git clone https://github.com/ChangjinHe2000/ppgl-assist-ai-medical-imaging.git
cd ppgl-assist-ai-medical-imaging
```

### 2. 安装项目依赖

创建 Python 推理环境：

```bash
conda env create -f envs/environment.inference.yml
conda activate ppgl
```

安装 Vue 前端依赖：

```bash
cd frontend-vue-prototype
npm ci
cd ..
```

Spring Boot 依赖会在首次执行 Maven 启动命令时自动下载。

### 3. 初始化 MySQL 数据库

先进入 MySQL 管理终端。Ubuntu 默认安装通常可以使用：

```bash
sudo mysql
```

如果你的 MySQL root 账号使用密码登录，则改用 `mysql -u root -p`。

在 MySQL 中创建项目数据库和专用账号；请将示例密码替换为自己的强密码：

```sql
CREATE DATABASE IF NOT EXISTS ppgl_analyze
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'ppgl_app'@'127.0.0.1'
  IDENTIFIED BY 'replace_with_a_strong_password';

GRANT ALL PRIVILEGES ON ppgl_analyze.*
  TO 'ppgl_app'@'127.0.0.1';

FLUSH PRIVILEGES;
EXIT;
```

导入数据表：

```bash
mysql -h 127.0.0.1 -u ppgl_app -p ppgl_analyze \
  < frontend-javaweb/src/main/resources/schema.sql
```

### 4. 配置运行参数

复制配置模板：

```bash
cp .env.example .env
```

编辑 `.env`，至少确认以下配置：

| 配置项 | 作用 | 本地示例 |
| --- | --- | --- |
| `PPGL_DATA_ROOT` | 保存病例、日志、RAG 索引和运行结果 | `$HOME/ppgl-assist-data` |
| `MYSQL_HOST` | MySQL 地址 | `127.0.0.1` |
| `MYSQL_DATABASE` | 数据库名称 | `ppgl_analyze` |
| `MYSQL_USER` | 数据库账号 | `ppgl_app` |
| `MYSQL_PASSWORD` | 数据库密码 | 第 3 步设置的密码 |
| `PPGL_AUTH_JWT_SECRET` | 登录令牌签名密钥 | 至少 32 个随机字符 |
| `PPGL_INTERNAL_API_KEY` | 业务后端访问 AI 服务的内部密钥 | 强随机字符串 |
| `TOTALSEG_WEIGHTS_PATH` | 全器官分割权重目录 | `$HOME/.totalsegmentator/nnunet/results` |
| `PPGL_V5_CHECKPOINT` | PPGL 分割权重文件（可选覆盖） | `weights/model_best.pth` 或绝对路径 |

可以执行两次下面的命令，分别生成 JWT 密钥和内部 API 密钥：

```bash
openssl rand -hex 32
```

真实 `.env` 已被 Git 排除，不要将其中的密码或密钥上传到公开仓库。

### 5. 准备模型

将 PPGL 分割权重放到默认位置：

```text
ai-backend/progress_patch_v5/weights/model_best.pth
```

也可以在 `.env` 中通过 `PPGL_V5_CHECKPOINT` 指定其他位置。该权重暂不随仓库发布，后续将上传至 Hugging Face，并在本文档中补充下载地址。

全器官分割首次运行时可能需要下载模型权重。请确保 `TOTALSEG_WEIGHTS_PATH` 指向当前用户可读写的目录，并保持网络可用。

AI 报告和问答需要可用的大模型。默认启动脚本使用 Ollama，并查找 `ppgl-qwen3-32b-q4:latest`。如果本机没有该模型，可使用已经安装的其他 Ollama 模型，例如：

```bash
ollama pull qwen3:8b
```

随后在 `.env` 中加入或修改：

```dotenv
OLLAMA_MODEL=qwen3:8b
CHAT_OPENAI_MODEL=qwen3:8b
REPORT_OPENAI_MODEL=qwen3:8b
```

### 6. 启动全部服务

打开第一个终端，在项目根目录启动 Ollama、FastAPI 和 Vue：

```bash
set -a
source .env
set +a

bash ai-backend/start_ppgl_ai.sh
```

看到 FastAPI 运行在 `8000` 端口、Vue 运行在 `5173` 端口后，打开第二个终端启动 Spring Boot：

```bash
set -a
source .env
set +a

cd frontend-javaweb
mvn spring-boot:run
```

服务启动完成后访问：

```text
http://127.0.0.1:5173/
```

### 7. 创建本地医生账号

项目不提供固定的默认账号和密码。公开注册接口只创建患者账号；本地首次体验医生工作流时，可以先注册一个测试账号，再将其角色调整为医生。

在项目根目录执行一次：

```bash
DEMO_PASSWORD="$(openssl rand -hex 16)"

curl --fail-with-body -X POST http://127.0.0.1:8080/api/auth/register \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"doctor_demo\",\"password\":\"${DEMO_PASSWORD}\",\"displayName\":\"演示医生\",\"phone\":\"13800000000\",\"patientIdCard\":\"110101199001011234\"}"

mysql -h 127.0.0.1 -u ppgl_app -p ppgl_analyze \
  -e "UPDATE users SET role='DOCTOR', patient_id_card=NULL WHERE username='doctor_demo';"

echo "医生账号：doctor_demo"
echo "医生密码：${DEMO_PASSWORD}"
unset DEMO_PASSWORD
```

记录终端显示的随机密码，然后使用 `doctor_demo` 登录。若注册信息与本地已有账号冲突，请更换用户名、手机号和身份证号示例值。服务器部署时应由数据库管理员创建独立账号，不要继续使用演示账号。

## 使用说明

### 上传病例

1. 使用医生账号登录后进入“上传病例”。
2. 选择经过授权和脱敏的 CT 文件，当前主要支持 `.nii.gz` 格式。
3. 上传完成后，系统会生成病例编号并进入病例详情页。

### 执行分割

病例详情页提供两个独立任务：

- “全器官分割”生成器官掩膜、器官体积和三维结构。
- “PPGL 肿瘤分割”生成 PPGL 肿瘤掩膜、体积、最大径和三维肿瘤结构。

两个任务可以分别运行，互不绑定。任务失败后可以在病例管理页面重新尝试分割。

### 查看结果

- 在病例详情页查看分割进度、量化指标和结果文件。
- 在二维视图中查看 CT 与分割掩膜的叠加效果。
- 在三维视图中勾选器官或 PPGL 肿瘤，并调整显示范围。
- 两类分割都完成后，可同时加载器官与肿瘤进行联合阅片。

### 生成 AI 报告

分割完成后进入报告页面生成结构化 AI 辅助报告。报告按照固定章节组织，病例数据和量化结果会填入对应位置。报告仅供辅助参考，使用者应结合原始影像和专业判断进行复核。

### 病例管理

病例列表支持查看详情、修改病例编号、删除病例和重试失败任务。删除病例会同时移除对应的运行文件，操作前请确认不再需要这些数据或已经完成备份。

## 可选：启用医学知识问答

RAG 知识库不是影像分割的必需条件。需要使用医学知识检索和问答时，再执行以下初始化操作。

```bash
set -a
source .env
set +a

mkdir -p "$PPGL_DATA_ROOT"/{rag-documents,rag-parsed,rag-index}
cp --update=none ai-backend/knowledge_base/documents/* "$PPGL_DATA_ROOT/rag-documents/"

cd ai-backend
python -m backend.rag.build_chunks \
  --documents "$PPGL_DATA_ROOT/rag-documents" \
  --output "$PPGL_DATA_ROOT/rag-parsed/chunks.jsonl"

python -c 'from backend.rag.vector_store import build_vector_index; print(build_vector_index(device="cuda", batch_size=16))'
```

首次构建会下载默认的 `BAAI/bge-m3` 向量模型。无 GPU 时可将 `device="cuda"` 改为 `device="cpu"`，但构建速度会更慢。

## 模型与数据

公开仓库不包含以下资产：

- PPGL 分割权重
- 全器官分割权重
- 真实医学影像
- 数据库内容、上传文件、日志和推理结果
- 本地大模型文件和私有配置

运行数据默认保存在 `~/ppgl-assist-data`。通过 `PPGL_DATA_ROOT` 可以改为其他项目外目录，推荐结构如下：

```text
$PPGL_DATA_ROOT/
├── uploads/        # 上传的病例文件
├── jobs/           # 分析任务状态与中间结果
├── cases/          # AI 病例工作区和推理结果
├── logs/           # 服务日志
├── rag-documents/  # RAG 原始文档
├── rag-parsed/     # RAG 切块结果
└── rag-index/      # Qdrant 本地向量索引
```

请只使用已获得授权且完成脱敏的测试影像。模型与数据的补充说明见 [WEIGHTS_AND_DATA.md](WEIGHTS_AND_DATA.md)。

## 部署与安全

本地体验可以直接使用上述启动方式。服务器部署推荐使用单机或内网环境，并遵循以下配置：

- 使用 Nginx 托管前端构建产物，将 `/api` 请求转发到 Spring Boot。
- 仅向使用者开放 Web 入口，FastAPI 和 MySQL 保持在本机或内网。
- 为 `PPGL_AUTH_JWT_SECRET`、`PPGL_INTERNAL_API_KEY` 和数据库账号设置独立的强密码。
- 将病例、数据库、模型、日志和运行结果放在代码仓库之外，并定期备份。
- 不要把 `.env`、真实病例、患者信息或模型权重上传到公开仓库。
- 确保服务运行账号对数据目录和模型目录具有所需的读写权限。

常用服务器配置示例：

| 配置项 | 示例 |
| --- | --- |
| `PPGL_DATA_ROOT` | `/var/lib/ppgl-assist` |
| `MYSQL_HOST` | MySQL 内网地址 |
| `PPGL_PIPELINE_BASE_URL` | `http://ai-service:8000` |
| `VITE_API_PROXY_TARGET` | `http://java-service:8080` |
| `CHAT_OPENAI_BASE_URL` | 内网大模型服务地址 |

## 常见问题

### Maven 提示没有编译器

这表示当前使用的是 JRE，或 `JAVA_HOME` 没有指向 JDK 21。确认以下两个命令都能正常输出版本：

```bash
java -version
javac -version
```

Ubuntu 的 JDK 21 常见配置为：

```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"
```

### 分割失败后在哪里查看日志

服务日志位于：

```text
$PPGL_DATA_ROOT/logs/
```

每个病例的分割日志和错误信息位于：

```text
$PPGL_DATA_ROOT/cases/<病例编号>/
```

修正模型路径、显存或依赖问题后，可以在病例管理页面重新尝试失败的任务。

### 页面可以打开，但无法登录或调用接口

请确认 Spring Boot 已运行在 `8080` 端口，Vue 的 `VITE_API_PROXY_TARGET` 指向该地址，并且登录账号已经存在于当前配置对应的 MySQL 数据库中。

## 系统组成

```text
浏览器（Vue，5173）
  └─ 病例操作、结果查看与报告交互
       ↓ /api
Spring Boot（8080）
  └─ 登录认证、角色与病例权限、业务数据、AI 请求转发
       ↓ 内部 API
FastAPI（8000）
  └─ 全器官分割、PPGL 肿瘤分割、三维产物、RAG 与 AI 报告
```

主要目录：

```text
.
├── frontend-vue-prototype/  # Vue Web 界面
├── frontend-javaweb/        # Spring Boot 业务后端与患者端原型
├── ai-backend/              # FastAPI、分割推理、RAG 和报告服务
├── envs/                    # Conda 环境配置
├── docs/                    # 补充说明与图片资源
└── WEIGHTS_AND_DATA.md      # 模型权重和医学数据说明
```
