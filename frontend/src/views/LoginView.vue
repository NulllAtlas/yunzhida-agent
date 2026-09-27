<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const role = ref('owner')
const username = ref('')
const password = ref('')

function submit() {
  router.push(role.value === 'owner' ? '/owner' : '/police')
}
</script>

<template>
  <section class="card login">
    <h2>登录 RoadMind</h2>
    <label>角色
      <select v-model="role">
        <option value="owner">车主</option>
        <option value="police">交警</option>
      </select>
    </label>
    <label>用户名 <input v-model="username" /></label>
    <label>密码 <input v-model="password" type="password" /></label>
    <button @click="submit">登录</button>
  </section>
</template>

<style scoped>
.login { max-width: 360px; margin: 40px auto; }
label { display: block; margin-bottom: 12px; }
input, select { width: 100%; padding: 8px; box-sizing: border-box; }
button { margin-top: 12px; padding: 8px 16px; border: 0; background: #1769e0; color: #fff; border-radius: 6px; cursor: pointer; }
</style>
