<template>
  <transition name="fade">
    <!-- закрывается только крестиком (или кнопками внутри окна): клик мимо и Esc не теряют введённое -->
    <div v-if="modelValue" class="modal-backdrop">
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
import Icon from './Icon.vue'

defineProps({
  modelValue: Boolean,
  title: String,
  eyebrow: String,
  wide: Boolean,
})
const emit = defineEmits(['update:modelValue'])
function close() {
  emit('update:modelValue', false)
}
</script>
