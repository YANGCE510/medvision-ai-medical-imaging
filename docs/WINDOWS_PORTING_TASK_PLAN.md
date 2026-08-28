# MedVision AI Workbench 原生 Windows 适配任务书

## 1. 任务目标

在不复制业务代码、不改变现有接口的前提下，为 MedVision AI Workbench 增加 Windows 10/11 原生运行支持，使同一套 Vue、Spring Boot、FastAPI 和推理代码可以在 Linux 与 Windows 上运行。

本任务只负责 Windows 平台适配，不重写现有功能，不修改分割算法。

## 2. 当前代码基线

当前仓库已经完成以下解耦：

- CT 全器官推理和三维重建代码位于 `ai-backend/backend/ct/`，不再放在 Vue 目录。
- 报告接口位于 `ai-backend/backend/report/`，原 API 地址保持不变。
- 跨平台 Python 运行环境逻辑位于 `ai-backend/backend/core/runtime.py`。
- Linux 专用启动逻辑位于 `scripts/linux/`，原 `ai-backend/start_ppgl_*.sh` 命令仍可使用。
- Java 调用 Python 的命令可通过 `PPGL_PYTHON_BIN` 配置。
- `gltfpack` 可通过 PATH 或 `PPGL_GLTFPACK_BIN` 配置。
- 脑胶质瘤模块已经包含部分 Windows 路径、进程和文件锁兼容逻辑。

开始工作前，先从最新 `main` 创建独立分支：

```powershell
git switch main
git pull --ff-only
git switch -c feat/windows-support
```

## 3. 必须遵守的边界

以下内容必须保持兼容：

- 不复制 `frontend-vue-prototype`、`frontend-javaweb` 或 `ai-backend`，禁止建立两套 Linux/Windows 业务代码。
- 不修改现有 `/api/**` URL、请求字段和响应结构。
- 不修改现有数据库表结构，除非另行确认。
- 不修改病例目录结构、结果文件名和状态值。
- 不修改 CT 全器官、PPGL 肿瘤、脑胶质瘤的推理算法和模型输入输出。
- 不批量重命名 `PPGL_*` 环境变量、Java 包名或 JWT issuer。
- UI 状态继续使用“全器官分割完成”“PPGL：肿瘤分割完成”等业务名称，不暴露内部模型实现名。
- 不提交 `.env`、数据库、日志、医学影像、病例结果、模型权重或密钥。

如果发现必须改变公共接口或病例格式才能适配 Windows，应先记录原因并与项目负责人确认，不能直接修改。

## 4. 目标运行环境

首个 Windows 支持版本以以下环境为准：

- Windows 10/11 x64
- PowerShell 7
- NVIDIA GPU、可用的显卡驱动和项目所需 CUDA 运行环境
- Git、Miniconda/Conda
- Node.js 与 npm
- JDK 21、Maven
- MySQL 8
- Ollama

运行数据必须放在仓库外，例如：

```text
D:\MedVisionData
```

至少使用一次包含空格的目录和一次包含中文的目录做路径兼容测试。

## 5. 分阶段任务

### 阶段 A：Windows 环境与配置验证

- [ ] 在 Windows 克隆仓库，确认 Git 长路径支持已经开启。
- [ ] 安装前端、Java、Python 和推理依赖。
- [ ] 从 `.env.example` 创建本地 `.env`，不得提交真实 `.env`。
- [ ] 设置 `PPGL_DATA_ROOT` 到仓库外的 Windows 数据目录。
- [ ] 设置 `PPGL_PYTHON_BIN`，可填写 `python` 或目标环境的 `python.exe` 绝对路径。
- [ ] 验证 `PPGL_GLTFPACK_BIN`，或确保 `gltfpack` 可以从 PATH 找到。
- [ ] 配置 MySQL、JWT 密钥、内部 API Key、模型路径和 Ollama 模型。
- [ ] 验证数据库初始化和首次管理员账号创建流程。

验收结果：PowerShell 中能够分别执行 Python、npm、Java、Maven、MySQL 和 Ollama 命令，所有运行目录均位于仓库外。

### 阶段 B：实现 Windows 启停脚本

在 `scripts/windows/` 新增 PowerShell 脚本，功能与 `scripts/linux/` 对齐：

- [ ] `start_ppgl_ai.ps1`：启动 Ollama、FastAPI 和 Vue。
- [ ] `start_ppgl_node.ps1`：支持后端节点启动、模型预加载和停止模式。
- [ ] 从仓库根目录加载 `.env`，禁止使用 `Invoke-Expression` 执行 `.env` 内容。
- [ ] 启动前检查 JWT 密钥、内部 API Key、Python、Ollama、npm 和必要目录。
- [ ] 使用 `Start-Process -PassThru` 保存本次启动的进程 ID。
- [ ] PID 文件和日志保存到 `PPGL_DATA_ROOT`，不得写入仓库。
- [ ] 停止服务时只终止脚本启动的 PID，禁止按进程名结束系统中全部 Python、Java 或 Node 进程。
- [ ] 使用 `Invoke-WebRequest` 或 `Invoke-RestMethod` 完成服务健康检查。
- [ ] 启动失败时返回非零退出码，并输出对应日志路径。

建议增加兼容入口：

```text
ai-backend/start_ppgl_ai.ps1
ai-backend/start_ppgl_node.ps1
```

兼容入口只负责转发到 `scripts/windows/`，不复制启动逻辑。

验收结果：关闭所有服务后，可以通过一条 PowerShell 命令启动；也可以通过明确的停止命令只关闭本项目进程。

### 阶段 C：Python 与外部命令兼容

- [ ] 验证 `ai-backend/backend/core/runtime.py` 能找到 Conda/venv 的 `Scripts`、`Library/bin` 和 `python.exe`。
- [ ] 验证 `TotalSegmentator.exe`、`gltfpack.cmd` 或配置的绝对命令路径。
- [ ] 验证 PPGL 推理脚本能够处理 Windows 路径分隔符、空格和中文。
- [ ] 验证脑胶质瘤模块的 Windows 长路径、文件锁、进程组与超时终止逻辑。
- [ ] 检查子进程日志中的命令展示，避免因简单字符串拼接造成误导；不得把密钥写入日志。
- [ ] 只修改确实阻塞 Windows 的平台代码，不改推理数学逻辑。

验收结果：CT 和 MRI 推理命令能够从同一套 FastAPI 业务代码启动，不需要手工修改源码路径。

### 阶段 D：Java 与前端联调

- [ ] 使用 JDK 21 完成 `mvn package`。
- [ ] 验证 Java 通过 `PPGL_PYTHON_BIN` 调用正确的 Windows Python 环境。
- [ ] 验证 Vue 的代理地址来自现有配置，不写死本机 IP。
- [ ] 验证首次使用者能够完成初始化并登录，不会卡在登录页面。
- [ ] 验证 CT 与 MRI 病例仍在统一病例管理页面展示。
- [ ] 验证删除病例、修改病例号和失败后重新分割功能。

验收结果：Windows 浏览器能够通过 Vue/Spring Boot 正常使用 FastAPI 分析功能，刷新和重启后病例仍存在。

### 阶段 E：完整功能回归

使用已授权、已脱敏的测试数据，分别完成以下回归：

| 功能 | Windows 验收要求 |
| --- | --- |
| CT 上传 | `.nii.gz` 上传成功，病例进入统一病例管理 |
| 全器官分割 | 独立启动、完成、查看切片和三维模型 |
| PPGL 肿瘤分割 | 独立启动，不依赖全器官任务；三维阅片存在 PPGL 肿瘤选项 |
| 联合阅片 | 全器官与 PPGL 结果可以共同显示和独立开关 |
| MRI 上传 | 四序列病例上传和校验成功 |
| 脑胶质瘤分割 | 推理完成，分区、切片、三维结果可查看 |
| AI 报告 | 已有分割结果能够生成固定结构报告，不显示无依据的随机结论 |
| 报告问答 | 确定性问题优先读取结构化结果，流式接口正常 |
| 病例操作 | 重命名、删除、失败重试正常 |
| 安全 | 未登录无法读取病例；普通医生不能访问其他医生病例 |
| 数据持久化 | 重启全部服务后，数据库、病例和报告不丢失 |

每个失败项应记录：操作步骤、错误信息、日志路径、环境版本和是否能稳定复现。日志中不得包含病例原始数据或密钥。

### 阶段 F：交付

- [ ] 在 README 的用户安装部分增加 Windows 启动说明，不写开发日记。
- [ ] 提交 Windows 脚本和确实需要的平台兼容修改。
- [ ] 确认 `git status` 中没有 `.env`、病例、权重、数据库、日志、`node_modules`、`target` 或 `dist`。
- [ ] 推送 `feat/windows-support` 分支并创建 Pull Request。
- [ ] PR 中列出实际测试的 Windows、GPU、CUDA、Python、Java、Node 和 MySQL 版本。
- [ ] 附上功能验收结果，不上传真实医学影像截图。

## 6. 完成标准

同时满足以下条件才算完成：

1. Linux 与 Windows 共用一套 Vue、Java、FastAPI 和推理代码。
2. Windows 可以通过 PowerShell 完整启动和停止服务。
3. CT 全器官、PPGL、脑胶质瘤三条分割链路通过真实功能测试。
4. 病例管理、三维阅片、AI 报告和问答通过回归。
5. 数据、配置、模型权重和日志均位于仓库外。
6. 原有 Linux 启动命令和主要功能不受影响。
7. Git 提交中不存在密钥、医学数据、模型权重和构建产物。

## 7. 建议排期

| 工作项 | 预计时间 |
| --- | ---: |
| 环境安装与配置 | 0.5–1 天 |
| PowerShell 启停脚本 | 1 天 |
| CT、PPGL、脑胶质瘤兼容调整 | 1–2 天 |
| Java、Vue 联调与完整回归 | 1 天 |
| 使用说明和 PR 整理 | 0.5 天 |

总计约 4–5.5 个工作日。若 Windows 下的 CUDA、VTK、TotalSegmentator 或 nnU-Net 依赖需要重新匹配版本，时间可能增加。
