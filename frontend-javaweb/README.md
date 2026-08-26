# PPGL Analyze JavaWeb

这是系统唯一的公开业务后端，负责身份认证、权限、业务数据和 AI 网关。
Vue Web 只访问 Spring Boot；Spring Boot 再使用内部密钥调用 FastAPI。

## 主要功能

- 用户登录/注册，支持医生、患者、管理员角色
- CT 影像上传与病例管理
- AI 分割任务提交、状态查询与结果归档
- 报告列表、报告详情、医生复核与 AI 报告问答
- 患者端随访计划、反馈和报告查看
- Vue Web 的统一 `/api` 入口和 FastAPI AI 网关
- 患者微信小程序原型

`src/main/resources/static/` 中保留的页面是旧比赛界面，不再作为当前 Web 前端维护；
当前唯一 Web 前端为 `frontend-vue-prototype/`。

## AI 网关

Vue 调用 `/api/ai/**`，Spring Boot 在校验医生/管理员 JWT 后，把请求转发给
`ppgl.pipeline.base-url`。转发请求会携带 `X-PPGL-Internal-Key` 及受信用户上下文，
FastAPI 不对浏览器或局域网直接暴露。

## 目录结构

```text
frontend-javaweb/
├── pom.xml
├── src/main/java/com/ppgl/analyze/
│   ├── analysis/    # AI 分析任务、Jetson/推理流水线调用
│   ├── auth/        # 登录注册与用户角色
│   ├── care/        # 患者随访与反馈
│   ├── ct/          # CT 上传与病例记录
│   ├── report/      # AI 报告、复核、问答
│   └── viewer/      # 三维/病例查看文件接口
├── src/main/resources/
│   ├── static/      # Web 前端静态页面和资源
│   ├── schema.sql   # 数据库建表脚本
│   └── application.properties
├── patient-miniprogram/  # 微信小程序原型
└── python-worker/        # 本地分析 worker 示例
```

## 运行方式

需要 Java 21、Maven 和 MySQL。

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

## 配置说明

主要配置文件：

```text
src/main/resources/application.properties
```

默认数据库：

```properties
spring.datasource.url=jdbc:mysql://localhost:3306/ppgl_analyze
spring.datasource.username=${MYSQL_USER:root}
spring.datasource.password=${MYSQL_PASSWORD:}
```

AI 推理服务默认指向本机示例：

```properties
ppgl.pipeline.base-url=http://127.0.0.1:8000
ppgl.llm.chat-url=http://127.0.0.1:8000/api/llm/chat/stream
```

部署到 Jetson、服务器或评测机时，只需要把这些地址改为实际服务地址。

## 隐私说明

本提交版没有包含 `uploads/`、`jobs/`、`target/`、嵌套备份项目、医学影像和运行结果。评审运行时请使用合规脱敏的测试数据。
