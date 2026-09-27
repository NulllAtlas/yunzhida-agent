<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <nav class="nav">
    <RouterLink to="/owner">车主端</RouterLink>
    <RouterLink to="/police">交警端</RouterLink>
    <RouterLink to="/login">登录</RouterLink>
  </nav>
  <main class="main">
    <RouterView />
  </main>
</template>

<style>
body { margin: 0; font-family: system-ui, sans-serif; background: #f5f6f8; color: #1f2328; }
.nav { display: flex; gap: 16px; padding: 12px 20px; background: #fff; border-bottom: 1px solid #e5e6eb; }
.nav a { color: #1f2328; text-decoration: none; }
.nav a.router-link-active { color: #1769e0; font-weight: 600; }
.main { max-width: 960px; margin: 24px auto; padding: 0 16px; }
</style>
