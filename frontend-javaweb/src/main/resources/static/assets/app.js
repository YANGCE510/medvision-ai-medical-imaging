const { createApp, computed, nextTick, reactive, ref, watch } = Vue;

createApp({
    setup() {
        const AUTH_STORAGE_KEY = "ppglAnalyzeAuth";
        const MENU_STORAGE_KEY = "ppglAnalyzeActiveMenu";
        const ID_CARD_PATTERN = /^[1-9]\d{16}[0-9Xx]$/;
        const isAuthed = ref(false);
        const isBusy = ref(false);
        const authMode = ref("login");
        const activeMenu = ref("dashboard");
        const showCtUploadModal = ref(false);
        const actionConfirm = reactive({
            visible: false,
            type: "info",
            title: "",
            message: "",
            detail: "",
            confirmText: "确认",
            cancelText: "取消"
        });
        let actionConfirmResolver = null;
        const currentUser = reactive({
            id: null,
            username: "",
            displayName: "",
            email: "",
            phone: "",
            patientIdCard: "",
            role: "",
            roleLabel: ""
        });
        const authForm = reactive({
            username: "",
            password: "",
            displayName: "",
            email: "",
            phone: "",
            patientIdCard: "",
            role: "PATIENT",
            remember: true
        });
        const authMessage = reactive({
            type: "muted",
            text: "请输入账号和密码登录；没有账号可以先注册。"
        });
        const ctForm = reactive({
            patientName: "",
            patientIdCard: "",
            remark: "",
            file: null
        });
        const ctImages = ref([]);
        const ctBusy = ref(false);
        const ctListBusy = ref(false);
        const ctUploadProgress = ref(0);
        const ctSearchText = ref("");
        const ctAppliedSearch = ref("");
        const ctPage = ref(1);
        const ctPageSize = 8;
        const analysisCandidates = ref([]);
        const analysisTasks = ref([]);
        const selectedAnalysisIds = ref([]);
        const analysisSearchText = ref("");
        const analysisAppliedSearch = ref("");
        const analysisPage = ref(1);
        const analysisPageSize = 6;
        const analysisBusy = ref(false);
        const analysisMessage = reactive({
            type: "muted",
            text: ""
        });
        const computeNodeStatus = reactive({
            loading: false,
            status: "checking",
            available: false,
            hostReachable: false,
            serviceReachable: false,
            healthReachable: false,
            baseUrl: "",
            host: "",
            hostAddress: "",
            port: "",
            latencyMs: "",
            healthStatus: "",
            message: "正在检测 Jetson 计算节点状态",
            checkedAt: ""
        });
        let analysisTimer = null;
        const visibleFailedAnalysisTaskIds = new Set();
        const reports = ref([]);
        const selectedReport = ref(null);
        const reportDetailMode = ref("ct");
        const reportContentTab = ref("report");
        const reportBusy = ref(false);
        const reportMessage = reactive({
            type: "muted",
            text: ""
        });
        const reportReviewNoteDraft = ref("");
        const reportReviewBusy = ref(false);
        const showReportReviewModal = ref(false);
        const reportViewerActive = ref(false);
        const reportViewerMessage = ref("");
        const reportViewerOpacity = ref(0.45);
        const reportSurfaceOpacity = ref(0.95);
        const reportViewerFocus = ref("");
        const reportChatMessages = ref([]);
        const reportChatQuestion = ref("");
        const reportChatIncludeContext = ref(false);
        const reportChatBusy = ref(false);
        const reportChatError = ref("");
        const reportChatThinkingText = computed(() => (
            reportChatIncludeContext.value ? "结合报告深度思考中" : "快速思考中"
        ));
        let reportChatAbortController = null;
        let reportSliceViewers = [];
        let reportSurfaceViewer = null;
        let reportTimer = null;
        const embeddedReportViewerWidth = 1280;
        const embeddedReportViewerHeight = 900;
        const defaultFollowUpReason = "术后观察血压波动和症状恢复情况";
        const defaultFollowUpPreparation = "一周血压记录、复查 CT、实验室检查结果";
        const followUps = ref([]);
        const selectedFollowUpDetail = ref(null);
        const followUpBusy = ref(false);
        const followUpMessage = reactive({
            type: "muted",
            text: ""
        });
        const followUpForm = reactive({
            taskId: "",
            followUpDate: "",
            reason: "",
            preparation: ""
        });
        const showFollowUpReportPicker = ref(false);
        const followUpReportSearch = ref("");
        const feedbacks = ref([]);
        const feedbackBusy = ref(false);
        const feedbackSubTab = ref("feedbacks");
        const concernBusyTaskId = ref(null);
        const concernSummaries = reactive({});
        const concernMessage = reactive({
            type: "muted",
            text: ""
        });
        const feedbackMessage = reactive({
            type: "muted",
            text: ""
        });
        const feedbackReplyDrafts = reactive({});
        const ctMessage = reactive({
            type: "muted",
            text: "点击上传 CT 后填写病人信息。"
        });
        const menuItems = [
            { key: "dashboard", label: "工作台", title: "影像分析工作台", icon: "▦" },
            { key: "images", label: "影像管理", title: "影像数据管理", icon: "▣" },
            { key: "analysis", label: "分析任务", title: "智能分析任务", icon: "◎" },
            { key: "reports", label: "诊断报告", title: "报告管理", icon: "▤" },
            { key: "followups", label: "术后回访", title: "术后回访管理", icon: "◇" },
            { key: "feedbacks", label: "患者反馈", title: "患者反馈处理", icon: "⚙" }
        ];

        const currentMenu = computed(() => {
            return menuItems.find((item) => item.key === activeMenu.value) || menuItems[0];
        });

        const publishedReports = computed(() => reports.value.filter((report) => report.patientVisible));
        const selectedFollowUpReport = computed(() => (
            publishedReports.value.find((report) => String(report.taskId) === String(followUpForm.taskId)) || null
        ));
        const filteredPublishedReports = computed(() => {
            const keyword = followUpReportSearch.value.trim().toLowerCase();
            if (!keyword) {
                return publishedReports.value;
            }
            return publishedReports.value.filter((report) => [
                report.patientName,
                report.patientIdCard,
                report.originalFilename,
                report.riskLevel,
                report.createdAt
            ].some((value) => String(value || "").toLowerCase().includes(keyword)));
        });

        const isCtUploadReady = computed(() => {
            return Boolean(
                currentUser.role === "DOCTOR"
                && ctForm.patientName.trim()
                && ctForm.patientIdCard.trim()
                && ctForm.file
                && !ctBusy.value
            );
        });

        function requestActionConfirm(options = {}) {
            if (actionConfirmResolver) {
                actionConfirmResolver(false);
            }
            Object.assign(actionConfirm, {
                visible: true,
                type: options.type || "info",
                title: options.title || "确认操作",
                message: options.message || "确定继续执行该操作吗？",
                detail: options.detail || "",
                confirmText: options.confirmText || "确认",
                cancelText: options.cancelText || "取消"
            });
            return new Promise((resolve) => {
                actionConfirmResolver = resolve;
            });
        }

        function closeActionConfirm(result = false) {
            if (!actionConfirm.visible) {
                return;
            }
            actionConfirm.visible = false;
            const resolver = actionConfirmResolver;
            actionConfirmResolver = null;
            if (resolver) {
                resolver(result);
            }
        }

        function cancelActionConfirm() {
            closeActionConfirm(false);
        }

        function acceptActionConfirm() {
            closeActionConfirm(true);
        }

        const filteredCtImages = computed(() => {
            const keyword = ctAppliedSearch.value.trim().toLowerCase();
            if (!keyword) {
                return ctImages.value;
            }
            return ctImages.value.filter((image) => {
                return [
                    image.patientName,
                    image.patientIdCard
                ].some((value) => String(value || "").toLowerCase().includes(keyword));
            });
        });

        const ctTotalPages = computed(() => {
            return Math.max(1, Math.ceil(filteredCtImages.value.length / ctPageSize));
        });

        const pagedCtImages = computed(() => {
            const start = (ctPage.value - 1) * ctPageSize;
            return filteredCtImages.value.slice(start, start + ctPageSize);
        });

        const ctPageNumbers = computed(() => {
            const total = ctTotalPages.value;
            const maxVisible = 5;
            let start = Math.max(1, ctPage.value - Math.floor(maxVisible / 2));
            let end = Math.min(total, start + maxVisible - 1);
            start = Math.max(1, end - maxVisible + 1);

            const pages = [];
            for (let page = start; page <= end; page += 1) {
                pages.push(page);
            }
            return pages;
        });

        const filteredAnalysisCandidates = computed(() => {
            const keyword = analysisAppliedSearch.value.trim().toLowerCase();
            if (!keyword) {
                return analysisCandidates.value;
            }
            return analysisCandidates.value.filter((item) => {
                return [
                    item.patientName,
                    item.patientIdCard
                ].some((value) => String(value || "").toLowerCase().includes(keyword));
            });
        });

        const analysisTotalPages = computed(() => {
            return Math.max(1, Math.ceil(filteredAnalysisCandidates.value.length / analysisPageSize));
        });

        const pagedAnalysisCandidates = computed(() => {
            const start = (analysisPage.value - 1) * analysisPageSize;
            return filteredAnalysisCandidates.value.slice(start, start + analysisPageSize);
        });

        const analysisPageNumbers = computed(() => {
            const total = analysisTotalPages.value;
            const maxVisible = 5;
            let start = Math.max(1, analysisPage.value - Math.floor(maxVisible / 2));
            let end = Math.min(total, start + maxVisible - 1);
            start = Math.max(1, end - maxVisible + 1);

            const pages = [];
            for (let page = start; page <= end; page += 1) {
                pages.push(page);
            }
            return pages;
        });

        const selectedAnalysisCount = computed(() => selectedAnalysisIds.value.length);

        const allAnalysisSelected = computed(() => {
            return pagedAnalysisCandidates.value.length > 0
                && pagedAnalysisCandidates.value.every((item) => selectedAnalysisIds.value.includes(item.ctImageId));
        });

        const dashboardRecentImages = computed(() => {
            return ctImages.value.slice(0, 5).map((image) => ({
                ...image,
                statusClass: ctStatusClass(image.status)
            }));
        });

        const dashboardRecentTasks = computed(() => {
            return analysisTasks.value.slice(0, 4);
        });

        const dashboardRecentReports = computed(() => {
            return reports.value.slice(0, 3);
        });

        const dashboardRiskSummary = computed(() => {
            const items = [
                { label: "高风险", tone: "high", count: countReportsByRisk("high") },
                { label: "中风险", tone: "mid", count: countReportsByRisk("middle") },
                { label: "低风险", tone: "low", count: countReportsByRisk("low") }
            ];
            const max = Math.max(1, ...items.map((item) => item.count));
            return items.map((item) => ({
                ...item,
                percent: item.count ? Math.max(12, Math.round((item.count / max) * 100)) : 0
            }));
        });

        const dashboardRiskChart = computed(() => {
            const items = [
                { label: "高风险", tone: "high", color: "#d94b5f", count: countReportsByRisk("high") },
                { label: "中风险", tone: "mid", color: "#d99021", count: countReportsByRisk("middle") },
                { label: "低风险", tone: "low", color: "#1aa179", count: countReportsByRisk("low") }
            ];
            const total = items.reduce((sum, item) => sum + item.count, 0);
            let cursor = 0;
            const segments = items.map((item) => {
                const size = total ? (item.count / total) * 360 : 0;
                const start = cursor;
                cursor += size;
                return `${item.color} ${start}deg ${cursor}deg`;
            });
            return {
                items,
                total,
                highPercent: total ? Math.round((items[0].count / total) * 100) : 0,
                background: total ? `conic-gradient(${segments.join(", ")})` : "#e8eef5"
            };
        });

        const dashboardAnalyzedVolumes = computed(() => {
            return reports.value
                .map(reportTumorVolumeNumber)
                .filter((value) => Number.isFinite(value));
        });

        const dashboardVolumeBuckets = computed(() => {
            const buckets = [
                { label: "<2 ml", min: 0, max: 2, count: 0 },
                { label: "2-5 ml", min: 2, max: 5, count: 0 },
                { label: "5-10 ml", min: 5, max: 10, count: 0 },
                { label: ">10 ml", min: 10, max: Number.POSITIVE_INFINITY, count: 0 }
            ];
            dashboardAnalyzedVolumes.value.forEach((volume) => {
                const bucket = buckets.find((item) => volume >= item.min && volume < item.max) || buckets[buckets.length - 1];
                bucket.count += 1;
            });
            const maxCount = Math.max(1, ...buckets.map((item) => item.count));
            return buckets.map((item) => ({
                ...item,
                percent: item.count ? Math.max(16, Math.round((item.count / maxCount) * 100)) : 0
            }));
        });

        const dashboardClinicalKpis = computed(() => {
            const volumes = dashboardAnalyzedVolumes.value;
            const total = reports.value.length;
            const highRiskCount = countReportsByRisk("high");
            const averageVolume = volumes.length
                ? volumes.reduce((sum, value) => sum + value, 0) / volumes.length
                : null;
            const maxVolume = volumes.length ? Math.max(...volumes) : null;
            return [
                {
                    label: "已分析报告",
                    value: total,
                    note: "纳入统计"
                },
                {
                    label: "平均体积",
                    value: averageVolume == null ? "-" : `${formatCompactNumber(averageVolume)} ml`,
                    note: "肿瘤"
                },
                {
                    label: "高风险占比",
                    value: total ? `${Math.round((highRiskCount / total) * 100)}%` : "-",
                    note: `${highRiskCount} 例高风险`
                },
                {
                    label: "最大体积",
                    value: maxVolume == null ? "-" : `${formatCompactNumber(maxVolume)} ml`,
                    note: "样本峰值"
                }
            ];
        });

        const dashboardStats = computed(() => {
            const runningCount = analysisTasks.value.filter((task) => isRunningAnalysisTask(task)).length;
            const completedCtCount = ctImages.value.filter((image) => ctStatusClass(image.status) === "success").length;
            const highRiskCount = countReportsByRisk("high");
            return [
                {
                    label: "CT 病例总数",
                    value: ctImages.value.length,
                    change: `${completedCtCount} 例已完成`
                },
                {
                    label: "待分析病例",
                    value: analysisCandidates.value.length,
                    change: analysisCandidates.value.length ? "可加入队列" : "暂无待处理"
                },
                {
                    label: "活跃任务",
                    value: runningCount,
                    change: runningCount ? `${runningCount} 个活跃任务` : "队列空闲"
                },
                {
                    label: "高风险报告",
                    value: highRiskCount,
                    change: reports.value.length ? `共 ${reports.value.length} 份报告` : "暂无报告"
                }
            ];
        });

        const computeNodeStatusClass = computed(() => {
            if (computeNodeStatus.loading && !computeNodeStatus.checkedAt) {
                return "checking";
            }
            if (computeNodeStatus.available) {
                return "online";
            }
            if (computeNodeStatus.serviceReachable) {
                return "warning";
            }
            if (computeNodeStatus.hostReachable) {
                return "warning";
            }
            return "offline";
        });

        const computeNodeTitle = computed(() => {
            if (computeNodeStatus.loading && !computeNodeStatus.checkedAt) {
                return "正在检测";
            }
            if (computeNodeStatus.available) {
                return "分析节点可用";
            }
            if (computeNodeStatus.serviceReachable) {
                return "端口可连，接口未确认";
            }
            if (computeNodeStatus.hostReachable) {
                return "主机可达，服务未就绪";
            }
            return "分析节点不可用";
        });

        const computeNodeRows = computed(() => [
            {
                label: "节点地址",
                value: computeNodeStatus.host
                    ? `${computeNodeStatus.host}:${computeNodeStatus.port || "-"}`
                    : computeNodeStatus.baseUrl || "-"
            },
            {
                label: "主机 Ping",
                value: computeNodeStatus.hostReachable ? "可达" : "不可达",
                tone: computeNodeStatus.hostReachable ? "ok" : "bad"
            },
            {
                label: "分析服务",
                value: computeNodeStatus.serviceReachable ? "已连接" : "未连接",
                tone: computeNodeStatus.serviceReachable ? "ok" : "bad"
            },
            {
                label: "接口联通",
                value: computeNodeStatus.healthReachable
                    ? "通过"
                    : "失败",
                tone: computeNodeStatus.healthReachable ? "ok" : "bad"
            },
            {
                label: "IP 地址",
                value: computeNodeStatus.hostAddress || "-"
            },
            {
                label: "耗时",
                value: computeNodeStatus.latencyMs ? `${computeNodeStatus.latencyMs} ms` : "-"
            },
            {
                label: "最后检测",
                value: computeNodeStatus.checkedAt || "-"
            }
        ]);

        function switchAuthMode(mode) {
            authMode.value = mode;
            authMessage.type = "muted";
            authMessage.text = mode === "login" ? "请输入账号和密码登录。" : "注册后会自动进入系统。";
        }

        async function apiFetch(url, options = {}) {
            const response = await fetch(url, {
                ...options
            });
            if (response.status === 401) {
                clearAuthState();
                isAuthed.value = false;
            }
            return response;
        }

        async function submitAuth() {
            isBusy.value = true;
            authMessage.type = "muted";
            authMessage.text = "正在提交...";
            try {
                const endpoint = authMode.value === "login" ? "/api/auth/login" : "/api/auth/register";
                const payload = authMode.value === "login"
                    ? { username: authForm.username, password: authForm.password }
                    : {
                        username: authForm.username,
                        password: authForm.password,
                        displayName: authForm.displayName,
                        email: authForm.email,
                        phone: authForm.phone,
                        patientIdCard: authForm.patientIdCard,
                        role: "PATIENT"
                    };
                const result = await postJson(endpoint, payload);
                if (!result.success) {
                    throw new Error(result.message || "操作失败");
                }
                const session = result.data || {};
                Object.assign(currentUser, session.user || {});
                isAuthed.value = true;
                saveAuthState();
                authMessage.type = "success";
                authMessage.text = result.message || "登录成功";
                loadDashboardData();
            } catch (error) {
                authMessage.type = "error";
                authMessage.text = error.message || "网络异常，请稍后再试";
            } finally {
                isBusy.value = false;
            }
        }

        async function postJson(url, body) {
            const isPublicAuth = url === "/api/auth/login" || url === "/api/auth/register";
            const response = await (isPublicAuth ? fetch : apiFetch)(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body)
            });
            const result = await response.json().catch(() => null);
            if (!response.ok) {
                throw new Error(result?.message || "请求失败");
            }
            return result;
        }

        function ctStatusClass(status) {
            const text = String(status || "");
            if (text.includes("完成") || text.includes("已分析")) {
                return "success";
            }
            if (text.includes("分析中") || text.includes("推理") || text.includes("上传") || text.includes("排队")) {
                return "info";
            }
            if (text.includes("失败")) {
                return "warn";
            }
            return "muted";
        }

        function isRunningAnalysisTask(task) {
            const status = String(task?.status || "");
            const stage = String(task?.stage || "");
            if (["已完成", "分析完成", "分析失败"].includes(status) || ["done", "completed", "failed"].includes(stage)) {
                return false;
            }
            return ["排队中", "预处理中", "上传中", "等待 Jetson", "分析中", "后处理中"].some((activeStatus) => status.includes(activeStatus));
        }

        function normalizeRiskBucket(value) {
            const text = String(value || "").trim().toLowerCase();
            if (!text || text === "-") {
                return "unknown";
            }
            if (text.includes("高") || text === "high") {
                return "high";
            }
            if (text.includes("中") || text.includes("moderate") || text.includes("medium") || text.includes("intermediate")) {
                return "middle";
            }
            if (text.includes("低") || text === "low") {
                return "low";
            }
            return "unknown";
        }

        function countReportsByRisk(bucket) {
            return reports.value.filter((report) => normalizeRiskBucket(displayReportRiskLevel(report)) === bucket).length;
        }

        function maskIdCard(value) {
            const text = String(value || "").trim();
            if (text.length <= 8) {
                return text || "-";
            }
            return `${text.slice(0, 4)}****${text.slice(-4)}`;
        }

        async function loadComputeNodeStatus() {
            computeNodeStatus.loading = true;
            try {
                const response = await apiFetch("/api/analysis/node-status");
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "计算节点状态获取失败");
                }
                Object.assign(computeNodeStatus, {
                    ...result.data,
                    loading: false
                });
            } catch (error) {
                Object.assign(computeNodeStatus, {
                    loading: false,
                    status: "offline",
                    available: false,
                    hostReachable: false,
                    serviceReachable: false,
                    healthReachable: false,
                    healthStatus: "",
                    message: error.message || "计算节点状态获取失败",
                    checkedAt: new Date().toLocaleString()
                });
            }
        }

        async function loadDashboardData() {
            if (!isAuthed.value || currentUser.role !== "DOCTOR") {
                return;
            }
            loadComputeNodeStatus();
            await Promise.allSettled([
                loadCtImages(),
                loadAnalysisBoard(true),
                loadReports(true)
            ]);
        }

        async function loadCtImages() {
            if (!currentUser.id || currentUser.role !== "DOCTOR") {
                ctImages.value = [];
                return;
            }
            ctListBusy.value = true;
            try {
                const response = await apiFetch("/api/ct-images");
                const result = await response.json();
                if (!response.ok || !result.success) {
                    throw new Error(result.message || "影像列表加载失败");
                }
                ctImages.value = result.data || [];
                ctPage.value = 1;
            } catch (error) {
                ctMessage.type = "error";
                ctMessage.text = error.message || "影像列表加载失败";
            } finally {
                ctListBusy.value = false;
            }
        }

        async function loadAnalysisBoard(silent = false) {
            if (!isAuthed.value) {
                return;
            }
            if (!currentUser.id || currentUser.role !== "DOCTOR") {
                analysisCandidates.value = [];
                analysisTasks.value = [];
                selectedAnalysisIds.value = [];
                return;
            }
            if (!silent) {
                analysisBusy.value = true;
            }
            try {
                const response = await apiFetch("/api/analysis/board");
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "分析任务加载失败");
                }
                analysisCandidates.value = result.data?.candidates || [];
                analysisTasks.value = visibleAnalysisTasks(result.data?.tasks || [], silent);
                if (analysisPage.value > analysisTotalPages.value) {
                    analysisPage.value = analysisTotalPages.value;
                }
                const candidateIds = new Set(analysisCandidates.value.map((item) => item.ctImageId));
                selectedAnalysisIds.value = selectedAnalysisIds.value.filter((id) => candidateIds.has(id));
            } catch (error) {
                analysisMessage.type = "error";
                analysisMessage.text = error.message || "分析任务加载失败";
            } finally {
                analysisBusy.value = false;
            }
        }

        function searchAnalysisCandidates() {
            analysisAppliedSearch.value = analysisSearchText.value.trim();
            analysisPage.value = 1;
            const candidateIds = new Set(filteredAnalysisCandidates.value.map((item) => item.ctImageId));
            selectedAnalysisIds.value = selectedAnalysisIds.value.filter((id) => candidateIds.has(id));
        }

        function toggleAnalysisCandidate(id) {
            if (selectedAnalysisIds.value.includes(id)) {
                selectedAnalysisIds.value = selectedAnalysisIds.value.filter((item) => item !== id);
                return;
            }
            selectedAnalysisIds.value = [...selectedAnalysisIds.value, id];
        }

        function toggleAllAnalysisCandidates() {
            if (allAnalysisSelected.value) {
                const pageIds = new Set(pagedAnalysisCandidates.value.map((item) => item.ctImageId));
                selectedAnalysisIds.value = selectedAnalysisIds.value.filter((id) => !pageIds.has(id));
                return;
            }
            const selected = new Set(selectedAnalysisIds.value);
            pagedAnalysisCandidates.value.forEach((item) => selected.add(item.ctImageId));
            selectedAnalysisIds.value = [...selected];
        }

        async function submitAnalysisTasks() {
            if (!selectedAnalysisIds.value.length) {
                analysisMessage.type = "error";
                analysisMessage.text = "请先选择要分析的 CT。";
                return;
            }
            analysisBusy.value = true;
            analysisMessage.type = "muted";
            analysisMessage.text = "正在加入分析队列...";
            try {
                const result = await postJson("/api/analysis/tasks", {
                    ctImageIds: selectedAnalysisIds.value,
                    mode: "abdomen",
                    device: "cuda"
                });
                analysisCandidates.value = result.data?.candidates || [];
                analysisTasks.value = visibleAnalysisTasks(result.data?.tasks || [], true);
                analysisPage.value = 1;
                selectedAnalysisIds.value = [];
                analysisMessage.type = "success";
                analysisMessage.text = "已加入分析队列，系统会按顺序逐个提交给 Jetson。";
                startAnalysisPolling();
            } catch (error) {
                analysisMessage.type = "error";
                analysisMessage.text = error.message || "提交失败";
            } finally {
                analysisBusy.value = false;
            }
        }

        function startAnalysisPolling() {
            if (analysisTimer) {
                return;
            }
            loadAnalysisBoard(true);
            analysisTimer = window.setInterval(() => loadAnalysisBoard(true), 3000);
        }

        function stopAnalysisPolling() {
            if (!analysisTimer) {
                return;
            }
            window.clearInterval(analysisTimer);
            analysisTimer = null;
        }

        function visibleAnalysisTasks(tasks, includeNewFailures = false) {
            const activeTaskIds = new Set(analysisTasks.value.map((task) => task.id));
            if (includeNewFailures) {
                tasks.forEach((task) => {
                    if (isFailedAnalysisTask(task) && activeTaskIds.has(task.id)) {
                        visibleFailedAnalysisTaskIds.add(task.id);
                    }
                });
            }
            return tasks.map((task) => ({
                ...task,
                failedReasonPreview: shortAnalysisFailureReason(task.failedReason)
            })).filter((task) => !isFailedAnalysisTask(task) || visibleFailedAnalysisTaskIds.has(task.id));
        }

        function isFailedAnalysisTask(task) {
            return task?.status === "分析失败" || task?.stage === "failed";
        }

        function shortAnalysisFailureReason(reason) {
            const text = String(reason || "").replace(/\s+/g, " ").trim();
            if (!text) {
                return "";
            }
            const runtimeMatch = text.match(/RuntimeError:\s*([^]+?)(?: Traceback|$)/);
            const usefulText = runtimeMatch ? runtimeMatch[1].trim() : text;
            return usefulText.length > 120 ? `${usefulText.slice(0, 120)}...` : usefulText;
        }

        async function loadReports(silent = false) {
            if (!currentUser.id || currentUser.role !== "DOCTOR") {
                reports.value = [];
                selectedReport.value = null;
                return;
            }
            if (!silent) {
                reportBusy.value = true;
            }
            try {
                const response = await apiFetch("/api/reports");
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "报告列表加载失败");
                }
                reports.value = result.data || [];
                if (selectedReport.value && !reports.value.some((item) => item.taskId === selectedReport.value.taskId)) {
                    selectedReport.value = null;
                }
            } catch (error) {
                reportMessage.type = "error";
                reportMessage.text = error.message || "报告列表加载失败";
            } finally {
                reportBusy.value = false;
            }
        }

        async function openReport(report, mode = "ct") {
            closeReportViewer();
            reportDetailMode.value = mode === "report" ? "report" : "ct";
            reportContentTab.value = "report";
            reportBusy.value = true;
            reportMessage.type = "muted";
            reportMessage.text = "";
            try {
                const response = await apiFetch(`/api/reports/${report.taskId}`);
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "报告详情加载失败");
                }
                selectedReport.value = result.data;
                reportReviewNoteDraft.value = result.data?.doctorReviewNote || "";
                await loadReportChatMessages(result.data.taskId);
                if (reportDetailMode.value === "ct" && result.data?.segmentationAvailable) {
                    await nextTick();
                    await toggleReportViewer();
                }
            } catch (error) {
                reportMessage.type = "error";
                reportMessage.text = error.message || "报告详情加载失败";
            } finally {
                reportBusy.value = false;
            }
        }

        function closeReport() {
            closeReportViewer();
            selectedReport.value = null;
            reportChatMessages.value = [];
            reportChatQuestion.value = "";
            reportChatIncludeContext.value = false;
            reportChatError.value = "";
            reportDetailMode.value = "ct";
            reportContentTab.value = "report";
            reportMessage.type = "muted";
            reportMessage.text = "";
            reportReviewNoteDraft.value = "";
            reportReviewBusy.value = false;
            showReportReviewModal.value = false;
        }

        function setReportContentTab(tab) {
            reportContentTab.value = tab === "metrics" ? "metrics" : "report";
        }

        function reportReviewStatusClass(report) {
            return report?.patientVisible ? "success" : "warn";
        }

        function openReportReviewModal() {
            if (!selectedReport.value) {
                return;
            }
            reportReviewNoteDraft.value = selectedReport.value.doctorReviewNote || "";
            showReportReviewModal.value = true;
        }

        function closeReportReviewModal() {
            if (reportReviewBusy.value) {
                return;
            }
            showReportReviewModal.value = false;
        }

        async function publishReportReview() {
            const confirmed = await requestActionConfirm({
                type: "success",
                title: "发布给患者端",
                message: "确认审核通过并发布这份报告吗？",
                detail: "发布后，患者可以在小程序端查看该报告和医生备注。",
                confirmText: "确认发布"
            });
            if (!confirmed) {
                return;
            }
            const saved = await saveReportReview(true);
            if (saved) {
                showReportReviewModal.value = false;
            }
        }

        async function saveReportReview(patientVisible) {
            if (!selectedReport.value || reportReviewBusy.value) {
                return false;
            }
            reportReviewBusy.value = true;
            reportMessage.type = "muted";
            reportMessage.text = "";
            try {
                const response = await apiFetch(`/api/reports/${selectedReport.value.taskId}/review`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        patientVisible,
                        doctorReviewNote: reportReviewNoteDraft.value
                    })
                });
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "审核状态保存失败");
                }
                selectedReport.value = result.data;
                reportReviewNoteDraft.value = result.data?.doctorReviewNote || "";
                reports.value = reports.value.map((item) => (
                    item.taskId === result.data.taskId
                        ? {
                            ...item,
                            patientVisible: result.data.patientVisible,
                            doctorReviewStatus: result.data.doctorReviewStatus,
                            doctorReviewStatusLabel: result.data.doctorReviewStatusLabel,
                            doctorReviewNote: result.data.doctorReviewNote,
                            doctorReviewedAt: result.data.doctorReviewedAt
                        }
                        : item
                ));
                reportMessage.type = "success";
                reportMessage.text = patientVisible ? "已发布给患者端" : "已撤回患者端可见";
                return true;
            } catch (error) {
                reportMessage.type = "error";
                reportMessage.text = error.message || "审核状态保存失败";
                return false;
            } finally {
                reportReviewBusy.value = false;
            }
        }

        async function loadFollowUpPage() {
            await Promise.allSettled([
                loadReports(true),
                loadFollowUps()
            ]);
        }

        async function loadFollowUps() {
            if (!currentUser.id || currentUser.role !== "DOCTOR") {
                followUps.value = [];
                return;
            }
            followUpBusy.value = true;
            followUpMessage.type = "muted";
            followUpMessage.text = "";
            try {
                const response = await apiFetch("/api/care/follow-ups");
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "回访列表加载失败");
                }
                followUps.value = result.data || [];
            } catch (error) {
                followUpMessage.type = "error";
                followUpMessage.text = error.message || "回访列表加载失败";
            } finally {
                followUpBusy.value = false;
            }
        }

        async function openFollowUpReportPicker() {
            showFollowUpReportPicker.value = true;
            followUpReportSearch.value = "";
            if (!reports.value.length) {
                await loadReports(true);
            }
        }

        function closeFollowUpReportPicker() {
            showFollowUpReportPicker.value = false;
        }

        function selectFollowUpReport(report) {
            followUpForm.taskId = report?.taskId || "";
            showFollowUpReportPicker.value = false;
        }

        function openFollowUpDetail(plan) {
            selectedFollowUpDetail.value = plan || null;
        }

        function closeFollowUpDetail() {
            selectedFollowUpDetail.value = null;
        }

        async function createFollowUpPlan() {
            if (!followUpForm.taskId || !followUpForm.followUpDate) {
                followUpMessage.type = "error";
                followUpMessage.text = "请选择报告和复查时间。";
                return;
            }
            const reason = followUpForm.reason.trim() || defaultFollowUpReason;
            const preparation = followUpForm.preparation.trim() || defaultFollowUpPreparation;
            followUpBusy.value = true;
            followUpMessage.type = "muted";
            followUpMessage.text = "正在保存回访计划...";
            try {
                const result = await postJson("/api/care/follow-ups", {
                    taskId: Number(followUpForm.taskId),
                    followUpDate: followUpForm.followUpDate,
                    reason,
                    preparation
                });
                if (!result.success) {
                    throw new Error(result.message || "保存失败");
                }
                followUpMessage.type = "success";
                followUpMessage.text = "回访计划已保存。";
                followUpForm.taskId = "";
                followUpForm.followUpDate = "";
                followUpForm.reason = "";
                followUpForm.preparation = "";
                await loadFollowUps();
            } catch (error) {
                followUpMessage.type = "error";
                followUpMessage.text = error.message || "保存失败";
            } finally {
                followUpBusy.value = false;
            }
        }

        async function updateFollowUpStatus(plan, status) {
            if (!plan || followUpBusy.value) {
                return;
            }
            if (status === "COMPLETED") {
                const confirmed = await requestActionConfirm({
                    type: "success",
                    title: "完成回访",
                    message: "确认将该回访标记为已完成吗？",
                    detail: "完成后该回访将不再作为待处理事项显示。",
                    confirmText: "确认完成"
                });
                if (!confirmed) {
                    return;
                }
            }
            followUpBusy.value = true;
            try {
                const result = await postJson(`/api/care/follow-ups/${encodeURIComponent(plan.id)}/status`, {
                    status
                });
                if (!result.success) {
                    throw new Error(result.message || "保存失败");
                }
                followUps.value = followUps.value.map((item) => item.id === result.data.id ? result.data : item);
                if (selectedFollowUpDetail.value?.id === result.data.id) {
                    selectedFollowUpDetail.value = result.data;
                }
            } catch (error) {
                followUpMessage.type = "error";
                followUpMessage.text = error.message || "保存失败";
            } finally {
                followUpBusy.value = false;
            }
        }

        async function loadFeedbacks() {
            if (!currentUser.id || currentUser.role !== "DOCTOR") {
                feedbacks.value = [];
                return;
            }
            feedbackBusy.value = true;
            feedbackMessage.type = "muted";
            feedbackMessage.text = "";
            try {
                const response = await apiFetch("/api/care/feedbacks");
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "反馈列表加载失败");
                }
                feedbacks.value = result.data || [];
                feedbacks.value.forEach((item) => {
                    feedbackReplyDrafts[item.id] = item.doctorReply || "";
                });
            } catch (error) {
                feedbackMessage.type = "error";
                feedbackMessage.text = error.message || "反馈列表加载失败";
            } finally {
                feedbackBusy.value = false;
            }
        }

        async function loadFeedbackPage() {
            await Promise.allSettled([
                loadFeedbacks(),
                loadReports(true)
            ]);
        }

        async function setFeedbackSubTab(tab) {
            feedbackSubTab.value = tab === "concerns" ? "concerns" : "feedbacks";
            if (feedbackSubTab.value === "concerns" && !reports.value.length) {
                await loadReports(true);
            }
            if (feedbackSubTab.value === "feedbacks" && !feedbacks.value.length) {
                await loadFeedbacks();
            }
        }

        async function analyzePatientConcern(report) {
            if (!report?.taskId || concernBusyTaskId.value) {
                return;
            }
            concernBusyTaskId.value = report.taskId;
            concernMessage.type = "muted";
            concernMessage.text = "正在分析患者担忧...";
            try {
                const response = await apiFetch(`/api/reports/${encodeURIComponent(report.taskId)}/patient-concern-summary`);
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "患者担忧分析失败");
                }
                concernSummaries[report.taskId] = {
                    ...result.data,
                    summary: cleanConcernSummary(result.data?.summary)
                };
                concernMessage.type = "muted";
                concernMessage.text = "";
            } catch (error) {
                concernMessage.type = "error";
                concernMessage.text = error.message || "患者担忧分析失败";
            } finally {
                concernBusyTaskId.value = null;
            }
        }

        function cleanConcernSummary(summary) {
            return String(summary || "")
                .replace(/#{1,6}\s*/g, "")
                .replace(/\*\*/g, "")
                .replace(/^\s*[-*]\s+/gm, "")
                .replace(/^\s*\d+[.)、]\s*/gm, "")
                .replace(/\n{3,}/g, "\n\n")
                .trim();
        }

        async function replyFeedback(feedback) {
            if (!feedback || feedbackBusy.value) {
                return;
            }
            feedbackBusy.value = true;
            feedbackMessage.type = "muted";
            feedbackMessage.text = "正在保存反馈处理结果...";
            try {
                const result = await postJson(`/api/care/feedbacks/${encodeURIComponent(feedback.id)}/reply`, {
                    doctorReply: feedbackReplyDrafts[feedback.id] || "",
                    status: "REPLIED"
                });
                if (!result.success) {
                    throw new Error(result.message || "保存失败");
                }
                feedbacks.value = feedbacks.value.map((item) => item.id === result.data.id ? result.data : item);
                feedbackReplyDrafts[result.data.id] = result.data.doctorReply || "";
                feedbackMessage.type = "success";
                feedbackMessage.text = "已回复患者反馈。";
            } catch (error) {
                feedbackMessage.type = "error";
                feedbackMessage.text = error.message || "保存失败";
            } finally {
                feedbackBusy.value = false;
            }
        }

        async function loadReportChatMessages(taskId, resetState = true) {
            if (resetState) {
                reportChatError.value = "";
                reportChatQuestion.value = "";
            }
            try {
                const response = await apiFetch(`/api/reports/${taskId}/chat`);
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "聊天记录加载失败");
                }
                reportChatMessages.value = result.data || [];
            } catch (error) {
                reportChatMessages.value = [];
            }
            await scrollReportChatToBottom();
        }

        async function scrollReportChatToBottom() {
            await nextTick();
            const list = document.querySelector(".report-chat-messages");
            if (list) {
                list.scrollTop = list.scrollHeight;
            }
        }

        async function sendReportChat() {
            if (reportChatBusy.value) {
                stopReportChat();
                return;
            }
            const question = reportChatQuestion.value.trim();
            if (!question || !selectedReport.value?.taskId) {
                return;
            }
            reportChatBusy.value = true;
            reportChatError.value = "";
            reportChatQuestion.value = "";
            const history = reportChatMessages.value
                .filter((item) => item.role === "user" || item.role === "assistant")
                .map((item) => ({ role: item.role, content: item.content }));
            reportChatMessages.value = [
                ...reportChatMessages.value,
                { role: "user", content: question },
                { role: "assistant", content: "" }
            ];
            await scrollReportChatToBottom();
            const assistantIndex = reportChatMessages.value.length - 1;
            try {
                reportChatAbortController = new AbortController();
                const response = await apiFetch(`/api/reports/${selectedReport.value.taskId}/chat/stream`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/x-ndjson"
                    },
                    body: JSON.stringify({
                        question,
                        history,
                        maxTokens: 1200,
                        includeReportContext: reportChatIncludeContext.value
                    }),
                    signal: reportChatAbortController.signal
                });
                if (!response.ok || !response.body) {
                    const result = await response.json().catch(() => null);
                    throw new Error(result?.message || "AI 对话请求失败");
                }
                await readReportChatStream(response.body, assistantIndex);
                await loadReportChatMessages(selectedReport.value.taskId);
            } catch (error) {
                if (error.name === "AbortError") {
                    reportChatMessages.value[assistantIndex].content = reportChatMessages.value[assistantIndex].content || "已停止生成。";
                    return;
                }
                const errorMessage = error.message || "AI 对话请求失败";
                const partialAnswer = reportChatMessages.value[assistantIndex]?.content || "";
                if (partialAnswer) {
                    reportChatMessages.value[assistantIndex].content = `${partialAnswer}\n\n生成中断，请重试。`;
                } else if (selectedReport.value?.taskId) {
                    await loadReportChatMessages(selectedReport.value.taskId, false);
                }
                reportChatError.value = errorMessage;
                reportChatQuestion.value = question;
                await scrollReportChatToBottom();
            } finally {
                reportChatBusy.value = false;
                reportChatAbortController = null;
            }
        }

        function stopReportChat() {
            if (reportChatAbortController) {
                reportChatAbortController.abort();
            }
            reportChatBusy.value = false;
        }

        function clearReportChat() {
            if (reportChatBusy.value) {
                return;
            }
            reportChatMessages.value = [];
            reportChatError.value = "";
        }

        async function readReportChatStream(body, assistantIndex) {
            const reader = body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";
            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";
                for (const line of lines) {
                    handleReportChatEvent(line, assistantIndex);
                }
            }
            if (buffer.trim()) {
                handleReportChatEvent(buffer, assistantIndex);
            }
        }

        function handleReportChatEvent(line, assistantIndex) {
            if (!line.trim()) {
                return;
            }
            const event = JSON.parse(line);
            if (event.type === "delta") {
                reportChatMessages.value[assistantIndex].content += event.text || "";
                scrollReportChatToBottom();
            } else if (event.type === "done") {
                reportChatMessages.value[assistantIndex].content = event.answer || reportChatMessages.value[assistantIndex].content;
                scrollReportChatToBottom();
            } else if (event.type === "error") {
                throw new Error(event.detail || "AI 对话失败");
            }
        }

        function displayReportRiskLevel(report) {
            const direct = normalizeDisplayValue(report?.riskLevel);
            if (direct) {
                return formatRiskLevel(direct);
            }
            const risk = parseJsonObject(report?.riskJson);
            const summary = parseJsonObject(report?.summaryJson);
            const result = parseJsonObject(report?.resultJson);
            const value = firstValue(
                    risk?.overall_level,
                    risk?.imaging_followup_risk_level,
                    summary?.risk_assessment?.overall_level,
                    summary?.risk_assessment?.imaging_followup_risk_level,
                    result?.risk_assessment?.overall_level,
                    result?.risk_assessment?.imaging_followup_risk_level
            );
            return formatRiskLevel(value);
        }

        function displayReportTumorVolume(report) {
            const direct = normalizeDisplayValue(report?.tumorVolumeMl);
            if (direct) {
                return direct;
            }
            const metrics = parseJsonObject(report?.metricsJson);
            const summary = parseJsonObject(report?.summaryJson);
            const result = parseJsonObject(report?.resultJson);
            const value = firstValue(
                    metrics?.tumor_volume_ml,
                    metrics?.tumor_burden?.tumor_volume_ml,
                    metrics?.tumor_burden?.raw_tumor_volume_ml,
                    summary?.clinical_metrics?.tumor_volume_ml,
                    summary?.clinical_metrics?.tumor_burden?.tumor_volume_ml,
                    result?.clinical_metrics?.tumor_volume_ml,
                    result?.clinical_metrics?.tumor_burden?.tumor_volume_ml
            );
            return formatTumorVolume(value);
        }

        function reportTumorVolumeNumber(report) {
            return parseFirstNumber(displayReportTumorVolume(report));
        }

        function parseFirstNumber(value) {
            const match = String(value || "").match(/-?\d+(?:\.\d+)?/);
            return match ? Number(match[0]) : Number.NaN;
        }

        function parseJsonObject(value) {
            if (!value || typeof value !== "string") {
                return {};
            }
            try {
                const parsed = JSON.parse(value);
                return parsed && typeof parsed === "object" ? parsed : {};
            } catch (error) {
                return {};
            }
        }

        function normalizeDisplayValue(value) {
            const text = value == null ? "" : String(value).trim();
            return text && text !== "-" ? text : "";
        }

        function firstValue(...values) {
            return values.find((value) => value !== undefined && value !== null && String(value).trim() !== "");
        }

        function firstObject(...values) {
            return values.find((value) => (
                value
                && typeof value === "object"
                && !Array.isArray(value)
                && Object.keys(value).length > 0
            )) || {};
        }

        function formatTumorVolume(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return "-";
            }
            return number.toFixed(3).replace(/\.?0+$/, "");
        }

        function formatCompactNumber(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return "-";
            }
            return number.toFixed(number >= 10 ? 1 : 2).replace(/\.?0+$/, "");
        }

        function formatRiskLevel(value) {
            const text = normalizeDisplayValue(value);
            if (!text) {
                return "-";
            }
            const normalized = text.toLowerCase();
            const labels = {
                low: "低风险",
                intermediate: "中风险",
                moderate: "中风险",
                medium: "中风险",
                high: "高风险"
            };
            return labels[normalized] || text;
        }

        const readableMetricLabels = {
            abdomen: "腹部",
            adrenal: "肾上腺",
            adrenal_gland_left: "左肾上腺",
            adrenal_gland_right: "右肾上腺",
            aorta: "主动脉",
            abutment: "贴邻",
            bowel: "肠管",
            catecholamine_secretion_pattern: "儿茶酚胺分泌模式",
            colon: "结肠",
            duodenum: "十二指肠",
            germline_genetic_testing: "胚系遗传检测",
            high: "高",
            iliac_artery_left: "左髂动脉",
            iliac_artery_right: "右髂动脉",
            iliac_vena_left: "左髂静脉",
            iliac_vena_right: "右髂静脉",
            inferior_vena_cava: "下腔静脉",
            intermediate: "中",
            kidney: "肾脏",
            kidney_left: "左肾",
            kidney_right: "右肾",
            ki67_or_pass_or_gapp_score: "Ki-67/PASS/GAPP 评分",
            known_metastasis_or_recurrence_history: "转移或复发病史",
            left: "左侧",
            left_adrenal_region: "左肾上腺区域",
            liver: "肝脏",
            low: "低",
            major_vessel: "大血管",
            moderate: "中等",
            multifocal: "多灶",
            near_10mm: "10mm 内邻近",
            overlap: "重叠",
            pancreas: "胰腺",
            plasma_or_urine_3_methoxytyramine: "血/尿 3-甲氧基酪胺",
            plasma_or_urine_metanephrines: "血/尿变肾上腺素",
            portal_vein_and_splenic_vein: "门静脉/脾静脉",
            right: "右侧",
            right_adrenal_region: "右肾上腺区域",
            sdhb_or_sdhx_status: "SDHB/SDHx 状态",
            separate: "分离",
            solid_organ: "实质器官",
            spleen: "脾脏",
            stomach: "胃",
            symptoms_and_blood_pressure: "症状与血压",
            vertebra: "椎体"
        };

        function reportJsonBundle(report) {
            const metrics = parseJsonObject(report?.metricsJson);
            const summary = parseJsonObject(report?.summaryJson);
            const result = parseJsonObject(report?.resultJson);
            const risk = parseJsonObject(report?.riskJson);
            const clinicalMetrics = firstObject(metrics, summary?.clinical_metrics, result?.clinical_metrics);
            const riskAssessment = firstObject(risk, summary?.risk_assessment, result?.risk_assessment, clinicalMetrics?.risk_assessment);
            return {
                metrics,
                summary,
                result,
                risk,
                clinicalMetrics,
                riskAssessment
            };
        }

        function reportCaseId(report) {
            const { metrics, summary, result } = reportJsonBundle(report);
            const caseId = firstValue(metrics?.case_id, summary?.case_id, result?.case_id);
            if (caseId) {
                return `Case ${caseId}`;
            }
            return report?.taskId ? `Task ${report.taskId}` : "结构化报告";
        }

        function reportSummaryCards(report) {
            const { metrics, summary, result, risk, clinicalMetrics, riskAssessment } = reportJsonBundle(report);
            const tumorBurden = firstObject(metrics?.tumor_burden, clinicalMetrics?.tumor_burden, summary?.tumor_burden, result?.tumor_burden);
            const origin = firstObject(metrics?.origin_assessment, clinicalMetrics?.origin_assessment, result?.origin_assessment);
            const tumorVolume = displayReportTumorVolume(report);
            const followupRisk = formatRiskLevel(firstValue(
                    riskAssessment?.imaging_followup_risk_level,
                    risk?.imaging_followup_risk_level
            ));
            const surgicalRisk = formatRiskLevel(firstValue(
                    riskAssessment?.surgical_complexity_level,
                    risk?.surgical_complexity_level
            ));
            return [
                {
                    label: "综合风险",
                    value: displayReportRiskLevel(report),
                    tone: riskTone(displayReportRiskLevel(report))
                },
                {
                    label: "随访风险",
                    value: followupRisk,
                    tone: riskTone(followupRisk)
                },
                {
                    label: "解剖复杂度",
                    value: surgicalRisk,
                    tone: riskTone(surgicalRisk)
                },
                {
                    label: "肿瘤体积",
                    value: withUnit(tumorVolume, "ml")
                },
                {
                    label: "最大径",
                    value: formatDistance(firstValue(tumorBurden?.max_diameter_mm, clinicalMetrics?.max_diameter_mm))
                },
                {
                    label: "疑似来源",
                    value: formatReadableKey(firstValue(origin?.suspected_origin, riskAssessment?.suspected_origin))
                },
                {
                    label: "邻近肾侧",
                    value: formatReadableKey(firstValue(metrics?.tumor_side_by_nearest_kidney, clinicalMetrics?.tumor_side_by_nearest_kidney, result?.tumor_side_by_nearest_kidney))
                },
                {
                    label: "分割置信度",
                    value: formatReadableKey(firstValue(risk?.segmentation_confidence, metrics?.segmentation_quality?.confidence, clinicalMetrics?.segmentation_quality?.confidence))
                }
            ];
        }

        function reportRiskReasons(report) {
            const { risk } = reportJsonBundle(report);
            const reasons = asArray(risk?.reasons);
            if (reasons.length) {
                return reasons.slice(0, 5).map(formatSentence);
            }
            return markdownListItems(report?.reportMarkdown, "risk reasons").slice(0, 5).map(formatSentence);
        }

        function reportNearestStructures(report) {
            const { metrics, risk, clinicalMetrics } = reportJsonBundle(report);
            const source = asArray(firstValue(risk?.nearest_structures, metrics?.nearest_anatomic_structures, clinicalMetrics?.nearest_anatomic_structures));
            return source.slice(0, 6).map(mapStructureRow);
        }

        function reportMissingClinicalData(report) {
            const { risk } = reportJsonBundle(report);
            const source = asArray(risk?.missing_required_clinical_data);
            const fallback = markdownListItems(report?.reportMarkdown, "missing clinical data");
            return (source.length ? source : fallback).slice(0, 8).map(formatReadableKey);
        }

        function reportLimitations(report) {
            const { risk } = reportJsonBundle(report);
            const source = asArray(risk?.limitations);
            const fallback = markdownListItems(report?.reportMarkdown, "notes");
            return (source.length ? source : fallback).slice(0, 3).map(formatSentence);
        }

        function clinicalTumorMetrics(report) {
            const { metrics, clinicalMetrics } = reportJsonBundle(report);
            const tumorBurden = firstObject(metrics?.tumor_burden, clinicalMetrics?.tumor_burden);
            return [
                { label: "肿瘤体积", value: formatVolume(firstValue(tumorBurden?.tumor_volume_ml, metrics?.tumor_volume_ml, clinicalMetrics?.tumor_volume_ml)) },
                { label: "原始体积", value: formatVolume(firstValue(tumorBurden?.raw_tumor_volume_ml, metrics?.raw_tumor_volume_ml, clinicalMetrics?.raw_tumor_volume_ml)) },
                { label: "最大径", value: formatDistance(tumorBurden?.max_diameter_mm) },
                { label: "等效球径", value: formatDistance(tumorBurden?.equivalent_sphere_diameter_mm) },
                { label: "组件数量", value: formatInteger(firstValue(tumorBurden?.component_count, metrics?.tumor_component_count, clinicalMetrics?.tumor_component_count)) },
                { label: "多灶提示", value: formatBoolean(tumorBurden?.multifocal) }
            ];
        }

        function clinicalOriginAssessment(report) {
            const { metrics, clinicalMetrics } = reportJsonBundle(report);
            const origin = firstObject(metrics?.origin_assessment, clinicalMetrics?.origin_assessment);
            return [
                { label: "疑似来源", value: formatReadableKey(origin?.suspected_origin) },
                { label: "置信度", value: formatReadableKey(origin?.confidence) },
                { label: "邻近肾侧", value: formatReadableKey(firstValue(metrics?.tumor_side_by_nearest_kidney, clinicalMetrics?.tumor_side_by_nearest_kidney)) }
            ];
        }

        function clinicalOriginBasis(report) {
            const { metrics, clinicalMetrics } = reportJsonBundle(report);
            const origin = firstObject(metrics?.origin_assessment, clinicalMetrics?.origin_assessment);
            return asArray(origin?.basis).slice(0, 3).map(formatSentence);
        }

        function clinicalAnchorDistances(report) {
            const { metrics, clinicalMetrics } = reportJsonBundle(report);
            const distances = firstObject(metrics?.anchor_distances_mm, clinicalMetrics?.anchor_distances_mm);
            return Object.entries(distances).map(([name, distance]) => ({
                name: formatReadableKey(name),
                distance: formatDistance(distance)
            }));
        }

        function clinicalNearestStructures(report) {
            const { metrics, clinicalMetrics, risk } = reportJsonBundle(report);
            const source = asArray(firstValue(metrics?.nearest_anatomic_structures, clinicalMetrics?.nearest_anatomic_structures, risk?.nearest_structures));
            return source.slice(0, 8).map(mapStructureRow);
        }

        function clinicalSegmentationQuality(report) {
            const { metrics, clinicalMetrics, risk } = reportJsonBundle(report);
            const quality = firstObject(metrics?.segmentation_quality, clinicalMetrics?.segmentation_quality);
            return [
                { label: "置信度", value: formatReadableKey(firstValue(quality?.confidence, risk?.segmentation_confidence)) },
                { label: "肿瘤体素", value: formatInteger(firstValue(metrics?.tumor_voxels, clinicalMetrics?.tumor_voxels, metrics?.tumor_burden?.tumor_voxels)) },
                { label: "原始体素", value: formatInteger(firstValue(metrics?.raw_tumor_voxels, clinicalMetrics?.raw_tumor_voxels, metrics?.tumor_burden?.raw_tumor_voxels)) }
            ];
        }

        function mapStructureRow(item) {
            const relation = firstValue(item?.distance_category, item?.relation);
            return {
                name: formatReadableKey(item?.name),
                group: formatReadableKey(item?.group),
                distance: formatDistance(firstValue(item?.min_surface_distance_mm, item?.distance_mm)),
                relation: formatReadableKey(relation),
                overlap: formatInteger(item?.overlap_voxels),
                tone: relationTone(relation)
            };
        }

        function asArray(value) {
            if (Array.isArray(value)) {
                return value.filter((item) => item !== undefined && item !== null && String(item).trim() !== "");
            }
            if (value === undefined || value === null || value === "") {
                return [];
            }
            return [value];
        }

        function markdownListItems(markdown, heading) {
            const lines = String(markdown || "").split(/\r?\n/);
            const needle = String(heading || "").toLowerCase();
            const items = [];
            let inSection = false;
            for (const line of lines) {
                const titleMatch = line.match(/^##\s+(.+)$/);
                if (titleMatch) {
                    inSection = titleMatch[1].toLowerCase().includes(needle);
                    continue;
                }
                if (inSection && /^#{1,2}\s+/.test(line)) {
                    break;
                }
                const itemMatch = inSection ? line.match(/^\s*[-*]\s+(.+)$/) : null;
                if (itemMatch) {
                    items.push(stripMarkdownInline(itemMatch[1]));
                }
            }
            return items;
        }

        function stripMarkdownInline(value) {
            return String(value || "").replace(/`/g, "").replace(/\*\*/g, "").trim();
        }

        function formatReadableKey(value) {
            const text = normalizeDisplayValue(value);
            if (!text) {
                return "-";
            }
            const key = text.toLowerCase();
            return readableMetricLabels[key] || text.replace(/_/g, " ");
        }

        function formatSentence(value) {
            const text = normalizeDisplayValue(value);
            if (!text) {
                return "-";
            }
            return text.replace(/[A-Za-z][A-Za-z0-9_]+/g, (token) => readableMetricLabels[token.toLowerCase()] || token);
        }

        function formatNumber(value, digits = 2) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return "-";
            }
            return number.toFixed(digits).replace(/\.?0+$/, "");
        }

        function formatInteger(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return "-";
            }
            return String(Math.round(number));
        }

        function formatDistance(value) {
            const number = formatNumber(value, 2);
            return number === "-" ? "-" : `${number} mm`;
        }

        function formatVolume(value) {
            const number = formatNumber(value, 3);
            return number === "-" ? "-" : `${number} ml`;
        }

        function formatPercent(value) {
            const number = Number(value);
            if (!Number.isFinite(number)) {
                return "-";
            }
            const percent = Math.abs(number) <= 1 ? number * 100 : number;
            return `${formatNumber(percent, 1)}%`;
        }

        function formatBoolean(value) {
            if (value === true || value === "true") {
                return "是";
            }
            if (value === false || value === "false") {
                return "否";
            }
            return "-";
        }

        function withUnit(value, unit) {
            const text = normalizeDisplayValue(value);
            if (!text) {
                return "-";
            }
            return text.toLowerCase().includes(unit.toLowerCase()) ? text : `${text} ${unit}`;
        }

        function riskTone(value) {
            const text = String(value || "").toLowerCase();
            if (text.includes("high") || text.includes("高")) {
                return "danger";
            }
            if (text.includes("intermediate") || text.includes("moderate") || text.includes("medium") || text.includes("中")) {
                return "warn";
            }
            if (text.includes("low") || text.includes("低")) {
                return "good";
            }
            return "";
        }

        function relationTone(value) {
            const text = String(value || "").toLowerCase();
            if (text.includes("overlap") || text.includes("abutment") || text.includes("重叠") || text.includes("贴邻")) {
                return "danger";
            }
            if (text.includes("near") || text.includes("邻近")) {
                return "warn";
            }
            if (text.includes("separate") || text.includes("分离")) {
                return "good";
            }
            return "";
        }

        function renderReportChatContent(content) {
            return renderMarkdown(content || "");
        }

        async function copyReportChatMessage(content, event) {
            const button = event?.currentTarget;
            await copyText(content || "");
            flashButton(button, "已复制");
        }

        async function handleReportChatClick(event) {
            const button = event.target.closest("[data-copy-code]");
            if (!button) {
                return;
            }
            const block = button.closest(".chat-code-block");
            const code = block?.querySelector("code")?.textContent || "";
            await copyText(code);
            flashButton(button, "已复制");
        }

        async function copyText(text) {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
                return;
            }
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
        }

        function flashButton(button, text) {
            if (!button) {
                return;
            }
            const original = button.textContent;
            button.textContent = text;
            window.setTimeout(() => {
                button.textContent = original;
            }, 1200);
        }

        function renderMarkdown(markdown) {
            const codeBlocks = [];
            const escaped = escapeHtml(markdown).replace(/```([A-Za-z0-9_-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
                const index = codeBlocks.length;
                codeBlocks.push({ lang, code });
                return `\n@@CODE_BLOCK_${index}@@\n`;
            });
            const lines = escaped.split(/\r?\n/);
            const output = [];
            let index = 0;
            while (index < lines.length) {
                const line = lines[index];
                if (!line.trim()) {
                    index += 1;
                    continue;
                }
                if (/^@@CODE_BLOCK_\d+@@$/.test(line.trim())) {
                    const blockIndex = Number(line.trim().match(/\d+/)[0]);
                    output.push(renderCodeBlock(codeBlocks[blockIndex]));
                    index += 1;
                    continue;
                }
                if (isMarkdownTable(lines, index)) {
                    const tableLines = [];
                    while (index < lines.length && /^\|.*\|$/.test(lines[index].trim())) {
                        tableLines.push(lines[index]);
                        index += 1;
                    }
                    output.push(renderTable(tableLines));
                    continue;
                }
                if (/^###\s+/.test(line)) {
                    output.push(`<h3>${renderInline(line.replace(/^###\s+/, ""))}</h3>`);
                    index += 1;
                    continue;
                }
                if (/^##\s+/.test(line)) {
                    output.push(`<h2>${renderInline(line.replace(/^##\s+/, ""))}</h2>`);
                    index += 1;
                    continue;
                }
                if (/^#\s+/.test(line)) {
                    output.push(`<h1>${renderInline(line.replace(/^#\s+/, ""))}</h1>`);
                    index += 1;
                    continue;
                }
                if (/^\s*[-*]\s+/.test(line)) {
                    const items = [];
                    while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
                        items.push(`<li>${renderInline(lines[index].replace(/^\s*[-*]\s+/, ""))}</li>`);
                        index += 1;
                    }
                    output.push(`<ul>${items.join("")}</ul>`);
                    continue;
                }
                if (/^\s*\d+\.\s+/.test(line)) {
                    const items = [];
                    while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
                        items.push(`<li>${renderInline(lines[index].replace(/^\s*\d+\.\s+/, ""))}</li>`);
                        index += 1;
                    }
                    output.push(`<ol>${items.join("")}</ol>`);
                    continue;
                }
                const paragraph = [line];
                index += 1;
                while (
                    index < lines.length
                    && lines[index].trim()
                    && !/^#{1,3}\s+/.test(lines[index])
                    && !/^\s*[-*]\s+/.test(lines[index])
                    && !/^\s*\d+\.\s+/.test(lines[index])
                    && !/^@@CODE_BLOCK_\d+@@$/.test(lines[index].trim())
                    && !isMarkdownTable(lines, index)
                ) {
                    paragraph.push(lines[index]);
                    index += 1;
                }
                output.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
            }
            return output.join("");
        }

        function renderInline(text) {
            return String(text || "")
                    .replace(/`([^`]+)`/g, "<code>$1</code>")
                    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
                    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
        }

        function renderCodeBlock(block) {
            return `
                <div class="chat-code-block">
                    <button data-copy-code type="button" aria-label="复制代码">复制代码</button>
                    <pre><code>${block?.code || ""}</code></pre>
                </div>
            `;
        }

        function isMarkdownTable(lines, index) {
            return Boolean(
                    lines[index]
                    && lines[index + 1]
                    && /^\|.*\|$/.test(lines[index].trim())
                    && /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(lines[index + 1].trim())
            );
        }

        function renderTable(lines) {
            const rows = lines.map((line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => renderInline(cell.trim())));
            const head = rows[0] || [];
            const body = rows.slice(2);
            return `
                <div class="chat-table-wrap">
                    <table>
                        <thead><tr>${head.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>
                        <tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
                    </table>
                </div>
            `;
        }

        function escapeHtml(value) {
            return String(value || "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#039;");
        }

        function parseReportLabelMap(report) {
            try {
                return JSON.parse(report.labelMapJson || "{}").label_map || {};
            } catch (error) {
                return {};
            }
        }

        function labelColor(index) {
            const palette = [
                [0, 0, 0],
                [255, 211, 46],
                [255, 181, 5],
                [255, 41, 41],
                [0, 156, 135],
                [31, 201, 163],
                [232, 23, 28],
                [232, 23, 28],
                [51, 92, 242],
                [51, 92, 242],
                [191, 117, 102],
                [161, 102, 89],
                [38, 99, 235],
                [255, 92, 168],
                [0, 194, 214],
                [190, 139, 69],
                [245, 124, 0],
                [34, 197, 94],
                [14, 165, 233],
                [168, 85, 247],
                [236, 72, 153],
                [148, 163, 184],
                [125, 211, 252],
                [196, 181, 253],
                [253, 186, 116],
                [134, 239, 172],
                [251, 113, 133],
                [255, 51, 51]
            ];
            return palette[index % palette.length];
        }

        function buildLabelColormap(labelMap) {
            const labels = Object.keys(labelMap).map(Number).filter(Number.isFinite);
            const maxLabel = Math.max(1, ...labels);
            const cmap = { R: [], G: [], B: [], A: [], I: [] };
            for (let label = 0; label <= maxLabel; label += 1) {
                const color = labelColor(label);
                cmap.R.push(color[0]);
                cmap.G.push(color[1]);
                cmap.B.push(color[2]);
                cmap.A.push(label === 0 ? 0 : 255);
                cmap.I.push(Math.round((label / maxLabel) * 255));
            }
            return cmap;
        }

        async function toggleReportViewer() {
            if (reportViewerActive.value) {
                closeReportViewer();
                return;
            }
            if (!selectedReport.value?.imageAvailable) {
                reportMessage.type = "error";
                reportMessage.text = "缺少原始 CT 图像，无法进行 overlay 显示。";
                return;
            }
            if (!selectedReport.value?.segmentationAvailable) {
                reportMessage.type = "error";
                reportMessage.text = "当前报告没有可显示的 NIfTI 分割结果";
                return;
            }
            reportViewerActive.value = true;
            reportViewerMessage.value = "正在加载 NIfTI 切片和 3D surface...";
            await nextTick();
            fitEmbeddedReportViewerFrame();
            window.addEventListener("resize", resizeReportViewers);
            try {
                const report = selectedReport.value;
                const labelMap = parseReportLabelMap(report);
                const labelColormap = buildLabelColormap(labelMap);
                const { Niivue } = await import("https://unpkg.com/@niivue/niivue@0.57.0/dist/index.js");
                const sliceViews = [
                    { id: "report-axial-canvas", type: "sliceTypeAxial" },
                    { id: "report-sagittal-canvas", type: "sliceTypeSagittal" },
                    { id: "report-coronal-canvas", type: "sliceTypeCoronal" }
                ];

                reportSliceViewers = [];
                for (const view of sliceViews) {
                    const nv = new Niivue({
                        backColor: [0, 0, 0, 1],
                        show3Dcrosshair: false,
                        crosshairWidth: 0,
                        isResizeCanvas: true
                    });
                    await nv.attachTo(view.id);
                    nv.addColormap("ppglLabels", labelColormap);
                    await nv.loadVolumes([
                        {
                            url: report.imageUrl,
                            name: "image.nii.gz",
                            colormap: "gray",
                            opacity: 1.0,
                            cal_min: -200,
                            cal_max: 300
                        },
                        {
                            url: report.segmentationUrl,
                            name: "seg.nii.gz",
                            colormap: "ppglLabels",
                            opacity: reportViewerOpacity.value,
                            cal_min: 0,
                            cal_max: Math.max(1, ...Object.keys(labelMap).map(Number).filter(Number.isFinite))
                        }
                    ]);
                    if (typeof nv[view.type] === "number") {
                        nv.setSliceType(nv[view.type]);
                    }
                    reportSliceViewers.push(nv);
                }

                await loadReportSurfaceViewer(report);
                applyReportViewerOpacity();
                reportViewerMessage.value = "滚轮可浏览切片；3D surface 支持旋转、缩放、平移";
                window.setTimeout(fitReportViewers, 80);
                window.setTimeout(fitReportViewers, 260);
            } catch (error) {
                reportMessage.type = "error";
                reportMessage.text = `${error.name || "Error"}：${error.message || "影像查看器加载失败"}`;
                reportViewerMessage.value = error.message || "影像查看器加载失败";
            }
        }

        function closeReportViewer() {
            window.removeEventListener("resize", resizeReportViewers);
            reportViewerActive.value = false;
            reportViewerMessage.value = "";
            reportViewerFocus.value = "";
            for (const viewer of reportSliceViewers) {
                viewer?.destroy?.();
                viewer?.dispose?.();
            }
            reportSliceViewers = [];
            if (reportSurfaceViewer) {
                reportSurfaceViewer.dispose();
                reportSurfaceViewer = null;
            }
        }

        async function toggleReportViewerFocus(name) {
            reportViewerFocus.value = reportViewerFocus.value === name ? "" : name;
            await nextTick();
            resizeReportViewers();
        }

        function resizeReportViewers() {
            fitEmbeddedReportViewerFrame();
            for (const viewer of reportSliceViewers) {
                viewer?.resizeListener?.();
                viewer?.drawScene?.();
            }
            reportSurfaceViewer?.resize?.();
        }

        function fitReportViewers() {
            fitEmbeddedReportViewerFrame();
            for (const viewer of reportSliceViewers) {
                viewer?.resizeListener?.();
                viewer?.resetView?.();
                viewer?.drawScene?.();
            }
            reportSurfaceViewer?.resize?.();
            reportSurfaceViewer?.reset?.();
        }

        function fitEmbeddedReportViewerFrame() {
            const panel = document.querySelector(".report-3d-panel.is-embedded");
            if (!panel) {
                return;
            }
            const width = Math.max(panel.clientWidth, 1);
            const height = Math.max(panel.clientHeight, 1);
            const scale = Math.min(
                1,
                Math.max(
                    0.05,
                    Math.min(width / embeddedReportViewerWidth, height / embeddedReportViewerHeight)
                )
            );
            panel.style.setProperty("--embedded-viewer-scale", scale.toFixed(4));
        }

        function applyReportViewerOpacity() {
            reportViewerOpacity.value = Math.max(0, Math.min(1, reportViewerOpacity.value));
            for (const viewer of reportSliceViewers) {
                if (typeof viewer.setOpacity === "function") {
                    viewer.setOpacity(1, reportViewerOpacity.value);
                    continue;
                }
                if (viewer.volumes?.[1]) {
                    viewer.volumes[1].opacity = reportViewerOpacity.value;
                    viewer.updateGLVolume?.();
                    viewer.drawScene?.();
                }
            }
        }

        function applyReportSurfaceOpacity() {
            reportSurfaceOpacity.value = Math.max(0.1, Math.min(1, reportSurfaceOpacity.value));
            reportSurfaceViewer?.setOpacity(reportSurfaceOpacity.value);
        }

        async function loadReportSurfaceViewer(report) {
            const surfaceEl = document.getElementById("report-surface-viewer");
            const controlsEl = document.getElementById("report-surface-controls");
            if (!surfaceEl || !controlsEl) {
                return;
            }
            surfaceEl.innerHTML = "";
            controlsEl.innerHTML = "";
            if (!report.meshAvailable) {
                surfaceEl.textContent = "3D surface mesh 尚未生成";
                return;
            }

            const [THREE, loaderModule, controlsModule] = await Promise.all([
                import("https://esm.sh/three@0.160.0"),
                import("https://esm.sh/three@0.160.0/examples/jsm/loaders/GLTFLoader.js"),
                import("https://esm.sh/three@0.160.0/examples/jsm/controls/TrackballControls.js")
            ]);
            const manifestResponse = await apiFetch(report.meshManifestUrl);
            const manifestPayload = manifestResponse.ok ? await manifestResponse.json() : null;
            const manifestMeshes = manifestPayload?.meshes || [];
            const defaultVisibleLabelIds = new Set([1, 2, 3, 12, 13, 14, 27]);

            function surfaceLabelName(name) {
                return String(name || "").replace(/^totalseg:/i, "");
            }

            function surfaceColorForLabel(name, fallbackColor, index) {
                const key = surfaceLabelName(name).toLowerCase();
                const namedColors = {
                    "tumor": [1.0, 0.0, 0.0, 1.0],
                    "aorta": [0.92, 0.82, 0.0, 0.98],
                    "inferior_vena_cava": [0.0, 0.68, 0.18, 0.98],
                    "portal_vein_and_splenic_vein": [0.02, 0.12, 0.82, 0.98],
                    "kidney_left": [0.76, 0.0, 0.74, 0.98],
                    "kidney_right": [0.0, 0.66, 0.74, 0.98],
                    "adrenal_gland_left": [0.95, 0.56, 0.20, 0.98],
                    "adrenal_gland_right": [0.95, 0.56, 0.20, 0.98],
                    "liver": [0.68, 0.62, 0.48, 0.96],
                    "spleen": [0.78, 0.72, 0.58, 0.96],
                    "pancreas": [0.78, 0.45, 0.14, 0.96],
                    "stomach": [0.72, 0.52, 0.34, 0.95],
                    "duodenum": [0.08, 0.88, 1.0, 0.96],
                    "small_bowel": [0.30, 1.0, 0.10, 0.96],
                    "colon": [0.54, 0.28, 0.12, 0.95],
                    "iliopsoas_left": [0.62, 0.52, 0.46, 0.94],
                    "iliopsoas_right": [0.62, 0.52, 0.46, 0.94]
                };
                if (key.startsWith("tumor:") || key.includes("tumor")) {
                    return namedColors.tumor;
                }
                if (key.startsWith("vertebrae_")) {
                    return [0.62, 0.60, 0.54, 0.96];
                }
                if (key.startsWith("iliac_artery")) {
                    return [0.92, 0.82, 0.0, 0.98];
                }
                if (key.startsWith("iliac_vena")) {
                    return [0.0, 0.68, 0.18, 0.98];
                }
                if (namedColors[key]) {
                    return namedColors[key];
                }
                const palette = [
                    [1.0, 0.08, 0.08, 0.97],
                    [0.0, 0.9, 0.12, 0.96],
                    [0.02, 0.78, 1.0, 0.96],
                    [1.0, 0.92, 0.0, 0.97],
                    [0.95, 0.0, 0.95, 0.96],
                    [0.95, 0.56, 0.16, 0.96]
                ];
                const source = fallbackColor || palette[index % palette.length];
                return [source[0], source[1], source[2], Math.max(0.92, source[3] ?? 0.96)];
            }

            const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
            renderer.setClearColor(0x000000, 1);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            renderer.outputColorSpace = THREE.SRGBColorSpace;
            renderer.toneMapping = THREE.NoToneMapping;
            renderer.toneMappingExposure = 0.82;
            surfaceEl.appendChild(renderer.domElement);

            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x000000);
            const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 10000);
            camera.up.set(0, 1, 0);
            const controls = new controlsModule.TrackballControls(camera, renderer.domElement);
            controls.rotateSpeed = 2.6;
            controls.zoomSpeed = 1.1;
            controls.panSpeed = 0.75;
            controls.staticMoving = true;
            controls.dynamicDampingFactor = 0.12;
            controls.mouseButtons = {
                LEFT: THREE.MOUSE.ROTATE,
                MIDDLE: THREE.MOUSE.DOLLY,
                RIGHT: THREE.MOUSE.PAN
            };
            scene.add(new THREE.HemisphereLight(0xffffff, 0x202020, 0.55));
            scene.add(new THREE.AmbientLight(0xffffff, 0.28));
            const light = new THREE.DirectionalLight(0xffffff, 0.72);
            light.position.set(1, 1.6, 1.2);
            scene.add(light);
            const fillLight = new THREE.DirectionalLight(0xb8d4ff, 0.18);
            fillLight.position.set(-1.3, 0.8, -0.6);
            scene.add(fillLight);

            const loader = new loaderModule.GLTFLoader();
            const gltf = await loader.loadAsync(report.meshUrl);
            const root = gltf.scene;
            scene.add(root);

            const meshObjects = [];
            root.traverse((object) => {
                if (!object.isMesh) {
                    return;
                }
                meshObjects.push(object);
            });

            meshObjects.forEach((mesh, index) => {
                const item = manifestMeshes[index] || {};
                mesh.userData.labelName = surfaceLabelName(item.name || mesh.name || `label_${index + 1}`);
                const color = surfaceColorForLabel(mesh.userData.labelName, item.color, index);
                mesh.userData.surfaceColor = color;
                mesh.material = new THREE.MeshLambertMaterial({
                    color: new THREE.Color(color[0], color[1], color[2]),
                    transparent: reportSurfaceOpacity.value < 0.99,
                    opacity: reportSurfaceOpacity.value,
                    depthWrite: reportSurfaceOpacity.value >= 0.85,
                    side: THREE.DoubleSide
                });
                mesh.visible = defaultVisibleLabelIds.has(Number(item.label_id));
            });

            const box = new THREE.Box3().setFromObject(root);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            root.position.sub(center);
            const radius = Math.max(size.length() * 0.5, 1);

            function fitCamera() {
                camera.up.set(0, 1, 0);
                camera.position.set(radius * 0.95, radius * 0.72, radius * 1.65);
                camera.near = Math.max(radius / 100, 0.1);
                camera.far = radius * 12;
                camera.updateProjectionMatrix();
                controls.target.set(0, 0, 0);
                controls.update();
            }

            function resize() {
                const width = Math.max(surfaceEl.clientWidth, 1);
                const height = Math.max(surfaceEl.clientHeight, 1);
                renderer.setSize(width, height, false);
                camera.aspect = width / height;
                camera.updateProjectionMatrix();
                controls.handleResize?.();
            }

            function renderControls() {
                const title = document.createElement("div");
                title.className = "surface-control-title";
                title.textContent = "Label 显示/隐藏";
                controlsEl.appendChild(title);

                const opacityControl = document.createElement("label");
                opacityControl.className = "surface-opacity-control";
                const opacityText = document.createElement("span");
                opacityText.textContent = `Surface 透明度 ${Math.round(reportSurfaceOpacity.value * 100)}%`;
                const opacityInput = document.createElement("input");
                opacityInput.type = "range";
                opacityInput.min = "0.1";
                opacityInput.max = "1";
                opacityInput.step = "0.05";
                opacityInput.value = String(reportSurfaceOpacity.value);
                opacityInput.addEventListener("input", () => {
                    reportSurfaceOpacity.value = Number(opacityInput.value);
                    opacityText.textContent = `Surface 透明度 ${Math.round(reportSurfaceOpacity.value * 100)}%`;
                    applyReportSurfaceOpacity();
                });
                opacityControl.appendChild(opacityText);
                opacityControl.appendChild(opacityInput);
                controlsEl.appendChild(opacityControl);

                meshObjects.forEach((mesh, index) => {
                    const item = manifestMeshes[index] || {};
                    const color = mesh.userData.surfaceColor || surfaceColorForLabel(mesh.userData.labelName, item.color, index);
                    const row = document.createElement("label");
                    row.className = "surface-control-row";
                    const input = document.createElement("input");
                    input.type = "checkbox";
                    input.checked = mesh.visible;
                    input.addEventListener("change", () => {
                        mesh.visible = input.checked;
                    });
                    const swatch = document.createElement("span");
                    swatch.className = "surface-swatch";
                    swatch.style.background = `rgb(${Math.round(color[0] * 255)}, ${Math.round(color[1] * 255)}, ${Math.round(color[2] * 255)})`;
                    const text = document.createElement("span");
                    text.textContent = `${item.label_id ?? index + 1} · ${mesh.userData.labelName}`;
                    row.appendChild(input);
                    row.appendChild(swatch);
                    row.appendChild(text);
                    controlsEl.appendChild(row);
                });
            }

            let animationId = 0;
            function animate() {
                animationId = window.requestAnimationFrame(animate);
                controls.update();
                renderer.render(scene, camera);
            }

            window.addEventListener("resize", resize);
            renderControls();
            resize();
            fitCamera();
            animate();
            reportSurfaceViewer = {
                reset: fitCamera,
                resize,
                setOpacity(value) {
                    meshObjects.forEach((mesh) => {
                        mesh.material.transparent = value < 0.99;
                        mesh.material.opacity = value;
                        mesh.material.depthWrite = value >= 0.85;
                        mesh.material.needsUpdate = true;
                    });
                },
                dispose() {
                    window.cancelAnimationFrame(animationId);
                    window.removeEventListener("resize", resize);
                    controls.dispose();
                    renderer.dispose();
                    surfaceEl.innerHTML = "";
                    controlsEl.innerHTML = "";
                }
            };
            applyReportSurfaceOpacity();
        }

        function resetReportViewer() {
            for (const viewer of reportSliceViewers) {
                viewer?.resetView?.();
            }
            reportSurfaceViewer?.reset();
            resizeReportViewers();
        }

        function startReportPolling() {
            if (reportTimer) {
                return;
            }
            loadReports(true);
            reportTimer = window.setInterval(() => loadReports(true), 5000);
        }

        function stopReportPolling() {
            if (!reportTimer) {
                return;
            }
            window.clearInterval(reportTimer);
            reportTimer = null;
        }

        watch(selectedReport, () => closeReportViewer());

        function searchCtImages() {
            ctAppliedSearch.value = ctSearchText.value.trim();
            ctPage.value = 1;
        }

        function changeCtPage(step) {
            const nextPage = ctPage.value + step;
            if (nextPage < 1 || nextPage > ctTotalPages.value) {
                return;
            }
            ctPage.value = nextPage;
        }

        function goCtPage(page) {
            if (page < 1 || page > ctTotalPages.value) {
                return;
            }
            ctPage.value = page;
        }

        function changeAnalysisPage(step) {
            const nextPage = analysisPage.value + step;
            if (nextPage < 1 || nextPage > analysisTotalPages.value) {
                return;
            }
            analysisPage.value = nextPage;
        }

        function goAnalysisPage(page) {
            if (page < 1 || page > analysisTotalPages.value) {
                return;
            }
            analysisPage.value = page;
        }

        function handleCtFileChange(event) {
            ctForm.file = event.target.files?.[0] || null;
        }

        function openCtUploadModal() {
            showCtUploadModal.value = true;
            ctMessage.type = "muted";
            ctMessage.text = "请填写病人姓名、身份证号并选择 CT 文件。";
        }

        function closeCtUploadModal() {
            if (ctBusy.value) {
                return;
            }
            showCtUploadModal.value = false;
            resetCtForm();
        }

        function resetCtForm() {
            ctForm.patientName = "";
            ctForm.patientIdCard = "";
            ctForm.remark = "";
            ctForm.file = null;
            const fileInput = document.querySelector("#ct-file-input");
            if (fileInput) {
                fileInput.value = "";
            }
            ctUploadProgress.value = 0;
        }

        function uploadCtFormData(formData) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open("POST", "/api/ct-images");
                xhr.upload.onprogress = (event) => {
                    if (!event.lengthComputable) {
                        ctUploadProgress.value = Math.max(ctUploadProgress.value, 35);
                        return;
                    }
                    const percent = Math.round((event.loaded / event.total) * 90);
                    ctUploadProgress.value = Math.max(5, Math.min(percent, 90));
                };
                xhr.onload = () => {
                    let result = null;
                    try {
                        result = JSON.parse(xhr.responseText || "null");
                    } catch (error) {
                        reject(new Error("上传失败"));
                        return;
                    }
                    if (xhr.status < 200 || xhr.status >= 300 || !result?.success) {
                        reject(new Error(result?.message || "上传失败"));
                        return;
                    }
                    ctUploadProgress.value = 100;
                    resolve(result);
                };
                xhr.onerror = () => reject(new Error("上传失败"));
                xhr.send(formData);
            });
        }

        async function uploadCtImage() {
            if (currentUser.role !== "DOCTOR") {
                ctMessage.type = "error";
                ctMessage.text = "只有医生用户可以上传 CT 影像。";
                return;
            }
            if (!isCtUploadReady.value) {
                ctMessage.type = "error";
                ctMessage.text = "请先填写病人姓名、身份证号并选择 CT 文件。";
                return;
            }
            if (!ID_CARD_PATTERN.test(ctForm.patientIdCard.trim())) {
                ctMessage.type = "error";
                ctMessage.text = "身份证号需为 18 位合法格式。";
                return;
            }
            ctBusy.value = true;
            ctUploadProgress.value = 5;
            ctMessage.type = "muted";
            ctMessage.text = "正在上传...";
            try {
                const minProgressTime = new Promise((resolve) => setTimeout(resolve, 1500));
                const formData = new FormData();
                formData.append("patientName", ctForm.patientName);
                formData.append("patientIdCard", ctForm.patientIdCard);
                formData.append("remark", ctForm.remark);
                formData.append("file", ctForm.file);

                const result = await uploadCtFormData(formData);
                await minProgressTime;
                ctMessage.type = "success";
                ctMessage.text = "CT 影像上传成功，状态已设置为未分析。";
                showCtUploadModal.value = false;
                ctImages.value = result.data ? [result.data, ...ctImages.value] : ctImages.value;
                ctPage.value = 1;
                resetCtForm();
            } catch (error) {
                ctMessage.type = "error";
                ctMessage.text = error.message || "上传失败";
            } finally {
                ctBusy.value = false;
            }
        }

        async function deleteCtImage(image) {
            const confirmed = await requestActionConfirm({
                type: "danger",
                title: "删除 CT 记录",
                message: `确定删除 ${image.patientName} 的 CT 记录吗？`,
                detail: "删除后该影像记录会从列表中移除，请确认不是误操作。",
                confirmText: "确认删除"
            });
            if (!confirmed) {
                return;
            }
            try {
                const response = await apiFetch(`/api/ct-images/${image.id}`, {
                    method: "DELETE"
                });
                const result = await response.json().catch(() => null);
                if (!response.ok || !result?.success) {
                    throw new Error(result?.message || "删除失败");
                }
                ctMessage.type = "success";
                ctMessage.text = "影像记录已删除。";
                ctImages.value = ctImages.value.filter((item) => item.id !== image.id);
                if (ctPage.value > ctTotalPages.value) {
                    ctPage.value = ctTotalPages.value;
                }
            } catch (error) {
                ctMessage.type = "error";
                ctMessage.text = error.message || "删除失败";
            }
        }

        async function openLogoutConfirm() {
            const confirmed = await requestActionConfirm({
                type: "info",
                title: "退出当前账号",
                message: "确定要退出当前账号吗？",
                detail: "退出后需要重新登录才能进入系统。",
                confirmText: "确认退出"
            });
            if (confirmed) {
                confirmLogout();
            }
        }

        async function confirmLogout() {
            try {
                await apiFetch("/api/auth/logout", { method: "POST" });
            } catch (error) {
                // Local logout must still succeed when the server is unavailable.
            }
            isAuthed.value = false;
            clearAuthState();
            authForm.password = "";
            authMessage.type = "muted";
            authMessage.text = "已退出登录。";
            ctImages.value = [];
            ctForm.file = null;
            ctForm.patientName = "";
            ctForm.patientIdCard = "";
            ctForm.remark = "";
            showCtUploadModal.value = false;
            ctSearchText.value = "";
            ctAppliedSearch.value = "";
            ctPage.value = 1;
            analysisCandidates.value = [];
            analysisTasks.value = [];
            visibleFailedAnalysisTaskIds.clear();
            selectedAnalysisIds.value = [];
            analysisSearchText.value = "";
            analysisAppliedSearch.value = "";
            analysisPage.value = 1;
            reports.value = [];
            selectedReport.value = null;
            reportChatMessages.value = [];
            reportChatQuestion.value = "";
            reportChatIncludeContext.value = false;
            reportChatError.value = "";
            followUps.value = [];
            selectedFollowUpDetail.value = null;
            followUpForm.taskId = "";
            followUpForm.followUpDate = "";
            followUpForm.reason = "";
            followUpForm.preparation = "";
            followUpReportSearch.value = "";
            showFollowUpReportPicker.value = false;
            feedbacks.value = [];
            feedbackSubTab.value = "feedbacks";
            concernBusyTaskId.value = null;
            Object.keys(concernSummaries).forEach((key) => delete concernSummaries[key]);
            concernMessage.type = "muted";
            concernMessage.text = "";
            stopAnalysisPolling();
            stopReportPolling();
        }

        function saveAuthState() {
            const storage = authForm.remember ? localStorage : sessionStorage;
            const otherStorage = authForm.remember ? sessionStorage : localStorage;
            const payload = {
                id: currentUser.id,
                username: currentUser.username,
                displayName: currentUser.displayName,
                email: currentUser.email,
                phone: currentUser.phone,
                patientIdCard: currentUser.patientIdCard,
                role: currentUser.role,
                roleLabel: currentUser.roleLabel
            };
            storage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload));
            storage.setItem(MENU_STORAGE_KEY, activeMenu.value);
            otherStorage.removeItem(AUTH_STORAGE_KEY);
            otherStorage.removeItem(MENU_STORAGE_KEY);
        }

        function restoreAuthState() {
            const raw = localStorage.getItem(AUTH_STORAGE_KEY) || sessionStorage.getItem(AUTH_STORAGE_KEY);
            if (!raw) {
                return;
            }
            try {
                const user = JSON.parse(raw);
                if (!user?.id || !user?.username) {
                    clearAuthState();
                    return;
                }
                Object.assign(currentUser, user);
                isAuthed.value = true;
                const savedMenu = localStorage.getItem(MENU_STORAGE_KEY) || sessionStorage.getItem(MENU_STORAGE_KEY);
                if (savedMenu && menuItems.some((item) => item.key === savedMenu)) {
                    activeMenu.value = savedMenu;
                }
                authMessage.type = "muted";
                authMessage.text = "已恢复登录状态。";
                if (currentUser.role === "DOCTOR") {
                    loadCtImages();
                }
            } catch (error) {
                clearAuthState();
            }
        }

        function clearAuthState() {
            localStorage.removeItem(AUTH_STORAGE_KEY);
            localStorage.removeItem(MENU_STORAGE_KEY);
            sessionStorage.removeItem(AUTH_STORAGE_KEY);
            sessionStorage.removeItem(MENU_STORAGE_KEY);
        }

        watch(activeMenu, (menu) => {
            if (isAuthed.value) {
                const storage = localStorage.getItem(AUTH_STORAGE_KEY) ? localStorage : sessionStorage;
                storage.setItem(MENU_STORAGE_KEY, menu);
            }
            if (menu === "images") {
                loadCtImages();
            }
            if (menu === "dashboard") {
                loadDashboardData();
            }
            if (menu === "analysis") {
                startAnalysisPolling();
            } else {
                stopAnalysisPolling();
            }
            if (menu === "reports") {
                startReportPolling();
            } else {
                stopReportPolling();
            }
            if (menu === "followups") {
                loadFollowUpPage();
            }
            if (menu === "feedbacks") {
                loadFeedbackPage();
            }
        });

        restoreAuthState();
        if (isAuthed.value && activeMenu.value === "dashboard") {
            loadDashboardData();
        }
        if (isAuthed.value && activeMenu.value === "followups") {
            loadFollowUpPage();
        }
        if (isAuthed.value && activeMenu.value === "feedbacks") {
            loadFeedbackPage();
        }

        return {
            activeMenu,
            authForm,
            authMessage,
            authMode,
            allAnalysisSelected,
            analysisBusy,
            analysisCandidates,
            analysisAppliedSearch,
            analysisMessage,
            analysisPage,
            analysisPageNumbers,
            analysisSearchText,
            analysisTasks,
            analysisTotalPages,
            ctBusy,
            ctForm,
            ctImages,
            ctListBusy,
            ctMessage,
            ctUploadProgress,
            ctAppliedSearch,
            ctPage,
            ctPageNumbers,
            ctSearchText,
            ctTotalPages,
            ctStatusClass,
            changeCtPage,
            changeAnalysisPage,
            clearReportChat,
            closeCtUploadModal,
            closeFollowUpReportPicker,
            closeReportReviewModal,
            clinicalAnchorDistances,
            clinicalNearestStructures,
            clinicalOriginAssessment,
            clinicalOriginBasis,
            clinicalSegmentationQuality,
            clinicalTumorMetrics,
            currentMenu,
            currentUser,
            dashboardClinicalKpis,
            dashboardRiskChart,
            dashboardRecentImages,
            dashboardRecentReports,
            dashboardRecentTasks,
            dashboardRiskSummary,
            dashboardStats,
            dashboardVolumeBuckets,
            analyzePatientConcern,
            concernBusyTaskId,
            concernMessage,
            concernSummaries,
            createFollowUpPlan,
            deleteCtImage,
            displayReportRiskLevel,
            displayReportTumorVolume,
            feedbackBusy,
            feedbackMessage,
            feedbackReplyDrafts,
            feedbackSubTab,
            feedbacks,
            filteredAnalysisCandidates,
            filteredCtImages,
            filteredPublishedReports,
            followUpBusy,
            followUpForm,
            followUpMessage,
            followUpReportSearch,
            followUps,
            goAnalysisPage,
            goCtPage,
            handleCtFileChange,
            handleReportChatClick,
            isCtUploadReady,
            isAuthed,
            isBusy,
            actionConfirm,
            acceptActionConfirm,
            cancelActionConfirm,
            confirmLogout,
            computeNodeRows,
            computeNodeStatus,
            computeNodeStatusClass,
            computeNodeTitle,
            loadCtImages,
            loadDashboardData,
            loadComputeNodeStatus,
            loadFeedbacks,
            loadFeedbackPage,
            loadFollowUpPage,
            loadFollowUps,
            loadReports,
            closeReport,
            closeFollowUpDetail,
            menuItems,
            maskIdCard,
            openReport,
            openCtUploadModal,
            openFollowUpDetail,
            openFollowUpReportPicker,
            openLogoutConfirm,
            openReportReviewModal,
            pagedCtImages,
            pagedAnalysisCandidates,
            publishedReports,
            publishReportReview,
            reportBusy,
            reportCaseId,
            reportChatBusy,
            reportChatError,
            reportChatIncludeContext,
            reportChatMessages,
            reportChatQuestion,
            reportChatThinkingText,
            reportContentTab,
            reportDetailMode,
            reportMessage,
            reportViewerActive,
            reportViewerFocus,
            reportViewerMessage,
            reportViewerOpacity,
            reportLimitations,
            reportMissingClinicalData,
            reportNearestStructures,
            reportRiskReasons,
            reportReviewBusy,
            reportReviewNoteDraft,
            reportReviewStatusClass,
            reportSummaryCards,
            reportSurfaceOpacity,
            reports,
            resetCtForm,
            searchAnalysisCandidates,
            searchCtImages,
            selectedFollowUpReport,
            selectFollowUpReport,
            sendReportChat,
            saveReportReview,
            replyFeedback,
            setReportContentTab,
            setFeedbackSubTab,
            selectedAnalysisCount,
            selectedAnalysisIds,
            selectedFollowUpDetail,
            selectedReport,
            showCtUploadModal,
            showFollowUpReportPicker,
            showReportReviewModal,
            submitAnalysisTasks,
            submitAuth,
            updateFollowUpStatus,
            applyReportViewerOpacity,
            applyReportSurfaceOpacity,
            resetReportViewer,
            renderReportChatContent,
            copyReportChatMessage,
            toggleReportViewerFocus,
            switchAuthMode,
            toggleReportViewer,
            toggleAllAnalysisCandidates,
            toggleAnalysisCandidate,
            uploadCtImage
        };
    }
}).mount("#app");
