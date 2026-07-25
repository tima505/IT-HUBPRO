<template>
  <transition name="fade">
    <div v-if="modelValue" class="modal-backdrop" @mousedown.self="close">
      <transition name="pop" appear>
        <div class="modal" :class="{ wide }">
          <div class="row between" style="margin-bottom: 18px">
            <div>
              <div class="eyebrow" v-if="eyebrow">{{ eyebrow }}</div>
              <h2 class="h2" style="margin-top: 4px">{{ title }}</h2>
            </div>
            <button class="btn ghost sm icon-close" @click="close"><Icon name="close" :size="16" /></button>
          </div>
          <slot />
        </div>
      </transition>
    </div>
  </transition>
</template>

<script setup>
import { watch, onUnmounted } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  modelValue: Boolean,
  title: String,
  eyebrow: String,
  wide: Boolean,
})
const emit = defineEmits(['update:modelValue'])
function close() {
  emit('update:modelValue', false)
}

function onKey(e) {
  if (e.key === 'Escape') close()
}
// вешаем слушатель Escape только пока окно открыто
watch(() => props.modelValue, (open) => {
  if (open) document.addEventListener('keydown', onKey)
  else document.removeEventListener('keydown', onKey)
})
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>
