const { buildPatientReport } = require("./report-format");

const API_BASE_URL = "http://127.0.0.1:8080";
const USER_STORAGE_KEY = "ppglPatientUser";
const SEEN_FOLLOW_UP_KEY = "ppglSeenFollowUps";
const SEEN_FEEDBACK_REPLY_KEY = "ppglSeenFeedbackReplies";
const FOLLOW_UP_TAB_INDEX = 1;
const FEEDBACK_TAB_INDEX = 2;

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}${path}`,
      method: options.method || "GET",
      data: options.data || {},
      header: {
        "content-type": "application/json"
      },
      success(res) {
        const body = res.data || {};
        if (res.statusCode >= 200 && res.statusCode < 300 && body.success !== false) {
          resolve(body);
          return;
        }
        reject(new Error(body.message || `请求失败：${res.statusCode}`));
      },
      fail(error) {
        reject(new Error(error.errMsg || "网络连接失败"));
      }
    });
  });
}

function saveCurrentUser(user) {
  wx.setStorageSync(USER_STORAGE_KEY, user);
}

function getCurrentUser() {
  return wx.getStorageSync(USER_STORAGE_KEY) || null;
}

function clearCurrentUser() {
  wx.removeStorageSync(USER_STORAGE_KEY);
  wx.removeTabBarBadge({ index: FOLLOW_UP_TAB_INDEX });
  wx.removeTabBarBadge({ index: FEEDBACK_TAB_INDEX });
}

function requirePatientUserId() {
  const user = getCurrentUser();
  if (!user || !user.id) {
    throw new Error("请先登录");
  }
  return user.id;
}

function userScopedKey(baseKey) {
  const user = getCurrentUser();
  return `${baseKey}:${user && user.id ? user.id : "guest"}`;
}

function readSeenIds(baseKey) {
  const raw = wx.getStorageSync(userScopedKey(baseKey));
  return new Set(Array.isArray(raw) ? raw.map((item) => String(item)) : []);
}

function writeSeenIds(baseKey, ids) {
  wx.setStorageSync(userScopedKey(baseKey), Array.from(ids));
}

function unreadFollowUps(followUps) {
  const seen = readSeenIds(SEEN_FOLLOW_UP_KEY);
  return (followUps || []).filter((item) => (
    item && item.id && !item.latestSubmission && item.status !== "COMPLETED" && !seen.has(String(item.id))
  ));
}

function unreadFeedbackReplies(feedbacks) {
  const seen = readSeenIds(SEEN_FEEDBACK_REPLY_KEY);
  return (feedbacks || []).filter((item) => (
    item && item.id && item.status === "REPLIED" && item.doctorReply && !seen.has(String(item.id))
  ));
}

function setTabBadge(index, count) {
  const text = count > 99 ? "99+" : String(count);
  if (count > 0) {
    wx.setTabBarBadge({ index, text });
    return;
  }
  wx.removeTabBarBadge({ index });
}

function markFollowUpsSeen(followUps) {
  const seen = readSeenIds(SEEN_FOLLOW_UP_KEY);
  (followUps || []).forEach((item) => {
    if (item && item.id && !item.latestSubmission && item.status !== "COMPLETED") {
      seen.add(String(item.id));
    }
  });
  writeSeenIds(SEEN_FOLLOW_UP_KEY, seen);
}

function markFeedbackRepliesSeen(feedbacks) {
  const seen = readSeenIds(SEEN_FEEDBACK_REPLY_KEY);
  (feedbacks || []).forEach((item) => {
    if (item && item.id && item.status === "REPLIED" && item.doctorReply) {
      seen.add(String(item.id));
    }
  });
  writeSeenIds(SEEN_FEEDBACK_REPLY_KEY, seen);
}

async function refreshCareTabBadges(options = {}) {
  try {
    const [followUps, feedbacks] = await Promise.all([
      options.followUps ? Promise.resolve(options.followUps) : getAllFollowUps(),
      options.feedbacks ? Promise.resolve(options.feedbacks) : getFeedbacks()
    ]);
    setTabBadge(FOLLOW_UP_TAB_INDEX, unreadFollowUps(followUps).length);
    setTabBadge(FEEDBACK_TAB_INDEX, unreadFeedbackReplies(feedbacks).length);
  } catch (error) {
    wx.removeTabBarBadge({ index: FOLLOW_UP_TAB_INDEX });
    wx.removeTabBarBadge({ index: FEEDBACK_TAB_INDEX });
  }
}

async function login(account, password) {
  const result = await request("/api/auth/login", {
    method: "POST",
    data: {
      username: account,
      password
    }
  });
  saveCurrentUser(result.data);
  return result.data;
}

async function register(form) {
  const result = await request("/api/auth/register", {
    method: "POST",
    data: {
      username: form.username,
      password: form.password,
      displayName: form.displayName,
      phone: form.phone,
      patientIdCard: form.patientIdCard,
      role: "PATIENT"
    }
  });
  saveCurrentUser(result.data);
  return result.data;
}

async function getReports() {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/reports?patientUserId=${encodeURIComponent(patientUserId)}`);
  return (result.data || []).map(buildPatientReport);
}

async function getReport(taskId) {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/reports/${encodeURIComponent(taskId)}?patientUserId=${encodeURIComponent(patientUserId)}`);
  return buildPatientReport(result.data || {});
}

async function getFollowUps(taskId) {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/care/reports/${encodeURIComponent(taskId)}/follow-ups?patientUserId=${encodeURIComponent(patientUserId)}`);
  return result.data || [];
}

async function getAllFollowUps() {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/care/follow-ups?patientUserId=${encodeURIComponent(patientUserId)}`);
  return result.data || [];
}

async function submitFollowUp(planId, form) {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/care/follow-ups/${encodeURIComponent(planId)}/submit?patientUserId=${encodeURIComponent(patientUserId)}`, {
    method: "POST",
    data: {
      symptoms: form.symptoms || [],
      bloodPressure: form.bloodPressure,
      heartRate: form.heartRate,
      treatmentStatus: form.treatmentStatus,
      newExamResults: form.newExamResults,
      patientNote: form.patientNote
    }
  });
  return result.data;
}

async function submitFeedback(taskId, question) {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/care/reports/${encodeURIComponent(taskId)}/feedbacks?patientUserId=${encodeURIComponent(patientUserId)}`, {
    method: "POST",
    data: { question }
  });
  return result.data;
}

async function getFeedbacks() {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/care/feedbacks?patientUserId=${encodeURIComponent(patientUserId)}`);
  return result.data || [];
}

async function getChatHistory(taskId) {
  const patientUserId = requirePatientUserId();
  const result = await request(`/api/patient/reports/${encodeURIComponent(taskId)}/chat?patientUserId=${encodeURIComponent(patientUserId)}`);
  return result.data || [];
}

async function sendChatMessage(taskId, message, history) {
  const patientUserId = requirePatientUserId();
  const compactHistory = (history || [])
    .filter((item) => item && item.role && item.content)
    .map((item) => ({
      role: item.role,
      content: item.content
    }))
    .slice(-2);
  const result = await request(`/api/patient/reports/${encodeURIComponent(taskId)}/chat?patientUserId=${encodeURIComponent(patientUserId)}`, {
    method: "POST",
    data: {
      question: message,
      history: compactHistory,
      maxTokens: 800
    }
  });
  return {
    role: "assistant",
    content: result.data && result.data.reply ? result.data.reply : ""
  };
}

module.exports = {
  login,
  register,
  getCurrentUser,
  clearCurrentUser,
  getReports,
  getReport,
  getFollowUps,
  getAllFollowUps,
  submitFollowUp,
  submitFeedback,
  getFeedbacks,
  markFollowUpsSeen,
  markFeedbackRepliesSeen,
  refreshCareTabBadges,
  getChatHistory,
  sendChatMessage
};
