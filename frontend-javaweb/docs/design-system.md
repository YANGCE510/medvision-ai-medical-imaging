# PPGL Analyze Design System

## Product Positioning

PPGL Analyze is an AI Medical Imaging Analysis Platform, not a hospital admin system, pharmacy system, or appointment system.

The product promise is:

- Upload CT imaging data.
- Run automatic organ and tumor segmentation.
- Present AI analysis with clear evidence.
- Support doctor review and patient-facing report explanation.
- Keep Web and WeChat Mini Program experiences visually connected.

The design must make the AI imaging workflow feel trustworthy, evidence-based, and clinically bounded.

## Healthcare UX Principles

### Trust Comes From Evidence

Medical AI trust should be built from visible evidence, not decorative technology styling.

Required trust signals:

- Original CT availability.
- Segmentation availability.
- Tumor and organ relationship summaries.
- Risk level with reasons.
- Analysis progress and failure reasons.
- Report generated time.
- Doctor review status.
- Patient visibility status.
- AI disclaimer and clinical boundary.

Avoid showing a risk badge without the supporting reason or next action.

### AI Must Stay Clinically Bounded

AI output should be framed as assistance, not diagnosis.

Use:

- "AI 辅助分析"
- "报告解释助手"
- "需医生结合原始影像复核"
- "不能替代医生诊断或治疗建议"

Avoid:

- "AI 诊断结果"
- "最终判断"
- "自动确诊"
- Generic chatbot language that ignores the active report.

### Doctor Review Is A First-Class State

Doctor review is the key product boundary between internal AI analysis and patient-facing explanation.

Doctor-facing Web must distinguish:

- AI generated.
- Doctor reviewed.
- Published to patient.
- Withdrawn from patient.

Patient-facing Mini Program should only emphasize doctor-reviewed content.

### Imaging Workflow Must Be Visible

The core product flow is:

CT 上传 -> AI 分割 -> 风险分析 -> 医生审核 -> 患者查看 / AI 问答

Web pages should organize around this flow instead of generic CRUD sections.

### Accessibility Is Healthcare Quality

Healthcare interfaces must prioritize readability and recoverability.

Required:

- 16px+ Web body text where possible.
- High contrast foreground/background pairs.
- Visible labels for inputs.
- Clear loading, error, and empty states.
- Status text in addition to color.
- Large touch targets in Mini Program.
- Reduced decorative motion.

## Shared Visual Language

### Tone

The shared tone is clinical, calm, precise, and AI-capable.

Web should feel like a medical imaging workstation.

Mini Program should feel like a patient-friendly report explanation tool.

### Color Tokens

Core colors:

| Token | Web | Mini Program | Usage |
| --- | --- | --- | --- |
| `--color-primary` | `#2563eb` | `#2563eb` | Primary action, analysis status, active navigation |
| `--color-primary-dark` | `#1d4ed8` | `#1d4ed8` | Hover/pressed primary |
| `--color-primary-soft` | `#eaf1ff` | `#eaf1ff` | Primary soft background |
| `--color-accent` | `#0f9f8f` | `#0f9f8f` | Health/success accent |
| `--color-bg` | `#f5f7fb` | `#f5f7fb` | Page background |
| `--color-surface` | `#ffffff` | `#ffffff` | Cards, panels |
| `--color-surface-subtle` | `#f8fafc` | `#f8fafc` | Inputs, subtle areas |
| `--color-text` | `#172331` | `#172331` | Main text |
| `--color-text-soft` | `#526174` | `#526174` | Secondary text |
| `--color-text-muted` | `#758397` | `#758397` | Hints, metadata |
| `--color-border` | `#dbe4ef` | `#dbe4ef` | Main border |
| `--color-border-soft` | `#e7edf4` | `#e7edf4` | Section separators |

Risk and clinical status:

| Token | Usage |
| --- | --- |
| `--color-success` / `--color-success-soft` | Low risk, completed, published |
| `--color-warning` / `--color-warning-soft` | Medium risk, review needed, pending doctor action |
| `--color-danger` / `--color-danger-soft` | High risk, failed, destructive actions |
| `--color-status-uploading` | CT upload in progress |
| `--color-status-segmenting` | Organ/tumor segmentation in progress |
| `--color-status-analyzing` | AI analysis in progress |
| `--color-status-reviewing` | Waiting for doctor review |
| `--color-status-published` | Visible to patient |
| `--color-status-failed` | Failed analysis or unavailable AI service |

Imaging workstation colors:

| Token | Usage |
| --- | --- |
| `--color-image-bg` | CT viewer and 3D viewer background |
| `--color-image-panel` | Imaging toolbar/control panels |
| `--color-image-border` | Imaging panel borders |

Disclaimer:

| Token | Usage |
| --- | --- |
| `--color-disclaimer-bg` | Patient-facing AI/medical boundary notes |
| `--color-disclaimer-border` | Disclaimer border |
| `--color-disclaimer-text` | Disclaimer text |

### Radius

Web:

- `--radius-sm: 8px` for buttons and inputs.
- `--radius-md: 12px` for cards and section panels.
- `--radius-lg: 16px` for large workspaces and chat containers.
- `--radius-pill: 999px` for badges.

Mini Program:

- `--radius-sm: 16rpx`
- `--radius-md: 24rpx`
- `--radius-lg: 32rpx`
- `--radius-pill: 999rpx`

### Shadows

Use shadows sparingly.

- `--shadow-card` for normal cards.
- `--shadow-panel` for large workspaces.
- Avoid heavy shadows inside imaging viewer areas.

## Shared Component Standards

### PatientSummaryCard / CaseSummaryCard

Purpose: show who and what the active case is.

Use on:

- Web report detail.
- Web analysis queue item detail.
- Mini Program report detail header.

Required content:

- Patient name.
- Masked ID card where appropriate.
- Case/task ID.
- Original filename.
- Created/generated time.
- Doctor review status.

Behavior:

- Web may show dense metadata in two columns.
- Mini Program should show patient-safe summary and avoid overwhelming identifiers.

Do:

- Use neutral surface card.
- Put review/publish status near the title.
- Use `RiskLevelBadge` only when risk is known.

Do not:

- Use this card as a generic table row.
- Hide doctor review state in small metadata.

### CTScanInfoCard

Purpose: summarize imaging source and segmentation availability.

Required content:

- Original CT file name.
- Upload time.
- File size if available.
- Image availability.
- Segmentation availability.
- Mesh/surface availability if available.

Recommended states:

- `uploading`
- `segmenting`
- `analyzing`
- `failed`
- `completed`

Visual:

- Light card outside viewer.
- Black/dark viewer area only for actual CT/3D content.

### RiskLevelBadge

Purpose: communicate clinical risk without relying on color alone.

Allowed labels:

- Low: `常规复核`
- Medium: `建议复核`
- High: `建议重点复核`
- Unknown: `待医生确认`

Tone mapping:

- Low -> success.
- Medium -> warning.
- High -> danger.
- Unknown -> muted.

Rules:

- Badge must include text.
- Badge should be paired with reason or metric cards in report contexts.
- Patient-facing labels should be less alarming than raw model labels.

### AIAnalysisCard

Purpose: present AI output and operational state.

Required content:

- Current analysis stage.
- Progress if available.
- Model/compute node status if relevant.
- Latest message or failure reason.
- Next action.

Stages:

- CT uploaded.
- Segmentation running.
- AI analyzing.
- Report generated.
- Doctor reviewing.
- Published.

Do:

- Show progress and stage together.
- Show recoverable error text.
- Use compact status timeline for Web.

Do not:

- Show only a percentage without stage meaning.
- Hide failed reason behind a tooltip only.

### ReportSection

Purpose: structure clinical content.

Standard sections:

- 核心结论
- 主要依据
- 关键测量
- 邻近结构
- 待补充资料
- 报告限制
- 医生备注
- 下一步建议
- 免责声明

Rules:

- Each section needs a clear heading.
- Use tables only for comparison or structured measurements.
- Use bullets for reasons and next steps.
- Keep patient-facing copy plain and non-alarming.

### MedicalMetricCard

Purpose: show one clinical metric.

Required fields:

- Label.
- Value.
- Unit or helper text.
- Optional tone.

Examples:

- 肿瘤体积: `12.4 ml`
- 最大径: `28.1 mm`
- 疑似来源: `左侧肾上腺区域`
- 分割置信度: `待医生确认`

Rules:

- Numeric values should use tabular/consistent figures where possible.
- Unknown values should show `-` or `待医生确认`, not blank.
- High-risk metrics may use warning/danger tone, but must include text.

### ChatBubble

Purpose: support report-aware AI conversation.

Web doctor-facing:

- Assistant can use structured markdown.
- Replies may include clinical reasoning and report references.
- Provide copy action.
- Show stop generation state.

Mini Program patient-facing:

- Replies should be shorter.
- Use patient-friendly explanation.
- Avoid raw JSON, internal labels, or model jargon.
- Avoid alarming standalone risk terms.

Required chat context:

- Active report/case summary.
- AI boundary disclaimer.
- Suggested questions in empty state.

Recommended suggested questions:

- "这份报告主要说明什么？"
- "这些指标是什么意思？"
- "复诊时我应该问医生什么？"
- "还需要准备哪些资料？"

### EmptyState

Purpose: explain absence and next action.

Required fields:

- Title.
- Plain-language description.
- Optional action.

Examples:

- No reports: `医生发布报告后，你可以在这里查看。`
- No analysis tasks: `上传 CT 后可提交 AI 分割与分析。`
- No segmentation: `当前报告没有可显示的 NIfTI 分割结果。`

Do not:

- Use only `暂无数据`.
- Use decorative illustration as the main message.

### LoadingState

Purpose: show progress in medical workflows.

Required:

- Message.
- If process exceeds a moment, show stage text.

Examples:

- `正在上传 CT...`
- `正在加载 NIfTI 切片...`
- `正在生成 3D surface...`
- `AI 正在分析报告...`

Rules:

- Loading should not block unrelated reading when possible.
- Use progress bar for uploads and analysis queues.
- Use spinner only for short waits or unknown duration.

### Warning / Disclaimer

Purpose: communicate clinical boundaries and safety information.

Warning style:

- Use danger tone for failures, missing data, unavailable imaging, or destructive actions.

Disclaimer style:

- Use warm neutral tone for AI/medical boundary notes.
- Should be visible but not visually alarming.

Standard disclaimer:

`本页面用于帮助理解报告内容，不能替代医生诊断或治疗建议。请结合医生意见和原始影像复核。`

## AI Chat Page Guidance

### Web

The Web chat should feel like a report analysis assistant inside a medical workstation.

Required layout:

- Active case summary.
- Report risk/metric summary.
- Message stream.
- Suggested questions when empty.
- Input with send/stop states.
- AI boundary disclaimer.

The assistant should answer from the active report context.

### Mini Program

The Mini Program chat should feel like a patient report explainer.

Required layout:

- Compact report summary at top.
- Doctor-reviewed status.
- Patient-friendly suggestions.
- AI boundary disclaimer near the first message or input area.

Avoid:

- Long technical reports.
- Raw labels such as `apr_tumor_volume_ml`.
- Diagnostic certainty language.

## Report Detail Guidance

### Web Report Detail

Primary goal: medical imaging workstation.

Recommended hierarchy:

1. Case summary and doctor review status.
2. CT viewer: axial, sagittal, coronal, 3D surface.
3. Core metrics and risk summary.
4. Risk reasons and nearest structures.
5. Doctor review and patient publish actions.
6. Report-aware AI chat.

### Mini Program Report Detail

Primary goal: patient understanding.

Recommended hierarchy:

1. Doctor note.
2. Core conclusion.
3. Risk explanation.
4. Key measurements.
5. Doctor review points.
6. Next-step suggestions.
7. Disclaimer.
8. Ask AI to explain this report.

## Anti-Patterns

Avoid:

- Generic admin dashboard aesthetics.
- CRUD table as the dominant expression of the product.
- AI purple/pink gradients.
- Animated decorative backgrounds.
- Icon-only medical actions without labels.
- Risk color without text.
- Empty pages for visible navigation items.
- Demo account copy in patient-facing production UI.
- Showing patient reports without review context.

## Implementation Notes

Current foundation files:

- Web token and utility layer: `src/main/resources/static/assets/ui-system.css`
- Mini Program global tokens: `patient-miniprogram/app.wxss`
- Mini Program base components: `patient-miniprogram/components/*`

Business pages should be refactored only after this design system is used as the source of truth.
