<template>
  <div ref="chartEl" :style="{ width: '100%', height: height }"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' },
})

const chartEl = ref(null)
let chart = null
let observer = null

function render() {
  if (!chart || !props.option) return
  // echarts 对部分“空配置”非法(如 radar 无 indicator 却有数据)会抛内部异常,这里兜底避免中断页面
  try {
    chart.setOption(props.option, true)
  } catch (err) {
    console.warn('[EChart] setOption 失败,已跳过本次渲染:', err)
  }
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  render()
  window.addEventListener('resize', resize)
  if (window.ResizeObserver) {
    observer = new ResizeObserver(resize)
    observer.observe(chartEl.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.option, render, { deep: true })
</script>
