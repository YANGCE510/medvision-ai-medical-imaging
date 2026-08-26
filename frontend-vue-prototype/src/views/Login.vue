<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-mark">PPGL-AI</div>
      <h1>PPGL 智能分割与三维辅助分析系统</h1>
      <p class="subtitle">AI Segmentation & 3D Visualization Platform</p>

      <el-form class="login-form">
        <el-form-item>
          <el-input v-model="username" placeholder="请输入账号" size="large" />
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

        <el-button type="primary" size="large" class="login-button" :loading="submitting" @click="handleLogin">
          登录系统
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '../api/request'

const router = useRouter()

const username = ref('')
const password = ref('')
const submitting = ref(false)

async function handleLogin() {
  if (!username.value.trim() || !password.value) {
    return
  }
  submitting.value = true
  try {
    const response = await request.post('/auth/login', {
      username: username.value.trim(),
      password: password.value
    })
    localStorage.setItem('ppglVueUser', JSON.stringify(response.data?.user || {}))
    await router.push('/dashboard')
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '账号或密码错误')
  } finally {
    submitting.value = false
  }
}
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
  margin-bottom: 32px;
}

.login-form {
  margin-top: 20px;
}

.login-button {
  width: 100%;
}
</style>
