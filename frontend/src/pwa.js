import { ref, computed } from 'vue'

// Установка приложения (PWA).
// Android / Chrome / Edge: браузер присылает beforeinstallprompt → показываем свою кнопку.
// iOS Safari: такого события нет — показываем инструкцию «Поделиться → На экран Домой».
let deferredPrompt = null
const promptReady = ref(false)

export const isStandalone = ref(
  window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
)
export const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  deferredPrompt = e
  promptReady.value = true
})
window.addEventListener('appinstalled', () => {
  deferredPrompt = null
  promptReady.value = false
  isStandalone.value = true
})

export const canInstall = computed(() => !isStandalone.value && (promptReady.value || isIOS))
export const iosHint = ref(false)

export async function installApp() {
  if (deferredPrompt) {
    deferredPrompt.prompt()
    await deferredPrompt.userChoice
    deferredPrompt = null
    promptReady.value = false
  } else if (isIOS) {
    iosHint.value = true
  }
}
