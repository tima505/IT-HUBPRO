<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
  <transition name="toast">
    <div v-if="toast" class="toast" role="alert" @click="toast = ''">{{ toast }}</div>
  </transition>
</template>

<script setup>
import { toast } from './api'
</script>

<style>
.toast {
  position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 100;
  max-width: min(520px, calc(100vw - 32px)); padding: 12px 18px;
  background: var(--bad-bg); color: var(--bad-fg); border-radius: var(--radius-sm);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .25); font-weight: 500; cursor: pointer;
}
.toast-enter-active, .toast-leave-active { transition: opacity .25s ease, transform .25s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 12px); }
</style>
