<script setup lang="ts">
import { computed } from 'vue'
import { CASE_FLOW_LABEL, type CaseFlowStatus } from '../types'

const props = defineProps<{
  status: string
}>()

const flow = computed(() => props.status as CaseFlowStatus)
const label = computed(() => CASE_FLOW_LABEL[props.status] || props.status || '未知状态')

/** 徽标配色遵循语义：处理中蓝、待受理紫、通过绿、驳回/异常红、结案灰蓝 */
const tone = computed(() => {
  switch (flow.value) {
    case 'submitted':
    case 'analyzing':
      return 'info'
    case 'pending_review':
      return 'brand'
    case 'reviewing':
      return 'warning'
    case 'decided':
    case 'dispensed':
      return 'success'
    case 'rejected':
      return 'danger'
    case 'closed':
      return 'gray'
    default:
      return 'gray'
  }
})
</script>

<template>
  <span :class="['t-badge', tone]" :title="label">{{ label }}</span>
</template>
