<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-mark">PPGL-AI</div>
      <h1>PPGL 智能分割与三维辅助分析系统</h1>
      <p class="subtitle">
        {{ setupRequired ? '首次使用，请创建第一个医生账号' : 'AI Segmentation & 3D Visualization Platform' }}
      </p>

      <el-alert
        v-if="setupRequired"
        class="setup-alert"
        title="初始化完成后，该入口会自动关闭"
        type="info"
        :closable="false"
        show-icon
      />

      <el-form v-if="!checkingSetup" class="login-form" @submit.prevent="handleSubmit">
        <el-form-item v-if="setupRequired">
          <el-input v-model="displayName" placeholder="医生姓名" size="large" maxlength="80" />
        </el-form-item>

        <el-form-item>
          <el-input v-model="username" placeholder="请输入账号" size="large" maxlength="32" />
        </el-form-item>

        <el-form-item v-if="setupRequired">
          <el-input v-model="phone" placeholder="手机号" size="large" maxlength="11" />
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="password"
            placeholder="请输入密码"
            type="password"
            size="large"
            show-password
          />
        </el-form-item>

        <el-form-item v-if="setupRequired">
          <el-input
            v-model="confirmPassword"
            placeholder="请再次输入密码"
            type="password"
            size="large"
            show-password
          />
        </el-form-item>

        <el-button
          native-type="submit"
          type="primary"
          size="large"
          class="login-button"
          :loading="submitting"
        >
          {{ setupRequired ? '创建医生账号并进入系统' : '登录系统' }}
        </el-button>
      </el-form>

      <div v-else class="checking-text">正在检查系统状态...</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '../api/request'

const router = useRouter()

const username = ref('')
const password = ref('')
const displayName = ref('')
const phone = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const checkingSetup = ref(true)
const setupRequired = ref(false)

function saveSessionAndEnter(response) {
  localStorage.setItem('ppglVueUser', JSON.stringify(response.data?.user || {}))
  return router.push('/dashboard')
}

async function loadSetupStatus() {
  checkingSetup.value = true
  try {
    const response = await request.get('/auth/setup-status')
    setupRequired.value = Boolean(response.data?.setupRequired)
  } catch (error) {
    setupRequired.value = false
    ElMessage.error(error?.response?.data?.message || '无法连接业务后端，请确认服务已经启动')
  } finally {
    checkingSetup.value = false
  }
}

async function handleSubmit() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }

  if (setupRequired.value) {
    if (!displayName.value.trim() || !phone.value.trim()) {
      ElMessage.warning('请填写医生姓名和手机号')
      return
    }
    if (password.value !== confirmPassword.value) {
      ElMessage.warning('两次输入的密码不一致')
      return
    }
  }

  submitting.value = true
  try {
    const response = setupRequired.value
      ? await request.post('/auth/setup', {
          username: username.value.trim(),
          password: password.value,
          displayName: displayName.value.trim(),
          phone: phone.value.trim()
        })
      : await request.post('/auth/login', {
          username: username.value.trim(),
          password: password.value
        })

    await saveSessionAndEnter(response)
  } catch (error) {
    const fallback = setupRequired.value ? '初始化失败，请检查填写内容' : '账号或密码错误'
    ElMessage.error(error?.response?.data?.message || fallback)
    if (error?.response?.status === 409) {
      await loadSetupStatus()
    }
  } finally {
    submitting.value = false
  }
}

onMounted(loadSetupStatus)
</script>

<style scoped>
.login-page {
  height: 100vh;
  background:
    linear-gradient(90deg, rgba(32, 224, 196, 0.055) 1px, transparent 1px),
    linear-gradient(180deg, rgba(106, 169, 255, 0.045) 1px, transparent 1px),
    linear-gradient(135deg, rgba(32, 224, 196, 0.12), transparent 36%),
    #0b1724;
  background-size: 42px 42px, 42px 42px, auto, auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-card {
  width: 460px;
  padding: 38px;
  background: rgba(8, 23, 36, 0.86);
  border: 1px solid rgba(93, 235, 219, 0.24);
  border-radius: 8px;
  box-shadow: 0 26px 70px rgba(0, 0, 0, 0.42), 0 0 32px rgba(32, 224, 196, 0.12);
  text-align: center;
  backdrop-filter: blur(18px);
}

.login-mark {
  width: fit-content;
  margin: 0 auto 18px;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(32, 224, 196, 0.12);
  border: 1px solid rgba(93, 235, 219, 0.28);
  color: #b9f8f1;
  font-weight: 800;
}

.login-card h1 {
  font-size: 24px;
  margin-bottom: 8px;
  color: var(--ppgl-text);
}

.subtitle {
  color: var(--ppgl-muted);
  margin-bottom: 24px;
}

.setup-alert {
  margin-bottom: 20px;
  text-align: left;
}

.login-form {
  margin-top: 20px;
}

.login-button {
  width: 100%;
}

.checking-text {
  padding: 28px 0 12px;
  color: var(--ppgl-muted);
}
</style>
