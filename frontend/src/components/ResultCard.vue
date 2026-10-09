<template>
  <div class="card">
    <div class="card-head">
      <h3>AI 判定结果</h3>
      <span :class="['conf-badge', confLevel]">{{ result.confidence }}% 置信</span>
    </div>

    <p class="fault">{{ result.fault }}</p>

    <div class="block">
      <p class="block-title">责任认定</p>
      <p class="resp">{{ result.responsibility }}</p>
      <p v-if="result.red_light" class="red-light">
        <span class="mini-tag">闯红灯</span>{{ result.red_light }}
      </p>
    </div>

    <!-- 责任占比条 -->
    <div v-if="result.parties.length" class="block">
      <p class="block-title">责任占比</p>
      <div v-for="p in result.parties" :key="p.party" class="ratio-row">
        <span class="ratio-name">{{ p.party }}</span>
        <div class="ratio-track">
          <div class="ratio-fill" :style="{ width: p.ratio + '%' }"></div>
        </div>
        <span class="ratio-val">{{ p.ratio }}%</span>
      </div>
    </div>

    <!-- 各车辆理由分条 -->
    <div v-for="p in result.parties" :key="'r-' + p.party" class="block">
      <p class="block-title">{{ p.party }} · 认定理由</p>
      <ul class="reasons">
        <li v-for="(r, i) in p.reasons" :key="i">
          <span class="li-dot"></span>
          <span>{{ r }}</span>
        </li>
      </ul>
    </div>

    <!-- 法条依据 -->
    <div v-if="result.laws.length" class="block">
      <p class="block-title">法条依据</p>
      <ul class="laws">
        <li v-for="(l, i) in result.laws" :key="i" class="law">
          <span class="clause">{{ l.clause }}</span>
          <span class="law-summary">{{ l.summary }}</span>
        </li>
      </ul>
    </div>

    <!-- 事故车辆识别框 -->
    <div v-if="result.keyframes?.length" class="block">
      <p class="block-title">事故车辆识别框（{{ result.keyframes.length }} 帧）</p>
      <div class="keyframes">
        <figure v-for="(k, i) in result.keyframes" :key="i" class="kframe">
          <img :src="k.url" :alt="k.caption" loading="lazy" />
          <figcaption>{{ k.caption }}</figcaption>
        </figure>
      </div>
    </div>

    <!-- 现场照片证据 -->
    <div v-if="result.photos?.length" class="block">
      <p class="block-title">现场照片证据（{{ result.photos.length }} 张）</p>
      <ul class="photos">
        <li v-for="(p, i) in result.photos" :key="i" class="photo">
          <span class="photo-name">{{ p.name }}</span>
          <span class="photo-sum">检出 {{ p.summary }} · 信号灯 {{ p.trafficLight }}</span>
          <span v-if="p.note" class="photo-note">{{ p.note }}</span>
        </li>
      </ul>
    </div>

    <p v-if="result.note" class="note">
      <span class="note-ic">ℹ️</span>{{ result.note }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AIResult } from '../types'

const props = defineProps<{ result: AIResult }>()

const confLevel = computed(() => {
  if (props.result.confidence >= 80) return 'high'
  if (props.result.confidence >= 60) return 'mid'
  return 'low'
})
</script>

<style scoped>
.card { text-align: left; }

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.card-head h3 {
  font-size: var(--font-16);
  font-weight: 800;
  color: var(--ink-900);
}
.conf-badge {
  font-size: var(--font-12);
  font-weight: 700;
  padding: 3px 10px;
  border-radius: var(--radius-full);
}
.conf-badge.high { background: var(--success-bg); color: var(--success); }
.conf-badge.mid { background: var(--warning-bg); color: var(--warning); }
.conf-badge.low { background: var(--danger-bg); color: var(--danger); }

.fault {
  font-size: var(--font-15);
  color: var(--ink-700);
  line-height: 1.7;
  margin-bottom: 18px;
  padding: 12px 14px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.block { margin-bottom: 18px; }
.block-title {
  font-size: var(--font-13);
  font-weight: 700;
  color: var(--ink-500);
  margin-bottom: 8px;
  letter-spacing: 0.2px;
}
.resp {
  font-size: var(--font-18);
  color: var(--ink-900);
  font-weight: 800;
  line-height: 1.5;
}
.red-light { display: inline-flex; align-items: center; gap: 8px; margin-top: 6px; font-size: var(--font-14); color: var(--ink-700); }
.mini-tag {
  font-size: var(--font-12);
  color: var(--danger);
  background: var(--danger-bg);
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-weight: 600;
}

.ratio-row { display: flex; align-items: center; gap: 12px; margin-bottom: 9px; }
.ratio-name { width: 96px; flex-shrink: 0; font-size: var(--font-13); font-weight: 600; color: var(--ink-700); }
.ratio-track { flex: 1; height: 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.ratio-fill {
  height: 100%;
  background: var(--gradient-brand);
  border-radius: 6px;
  transition: width 0.4s ease;
}
.ratio-val { width: 44px; text-align: right; font-size: var(--font-13); font-weight: 800; color: var(--ink-900); font-variant-numeric: tabular-nums; }

.reasons, .laws, .photos { display: grid; gap: 8px; }
.reasons li {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  font-size: var(--font-14);
  color: var(--ink-700);
  line-height: 1.6;
}
.li-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  margin-top: 8px;
  border-radius: 50%;
  background: var(--brand-500);
}

.law {
  padding: 11px 14px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand-500);
  border-radius: var(--radius-sm);
}
.clause { display: block; font-weight: 700; color: var(--ink-900); font-size: var(--font-14); }
.law-summary { color: var(--ink-500); font-size: var(--font-13); line-height: 1.6; }

.photo-name { font-weight: 700; color: var(--ink-900); }
.photo-sum { color: var(--ink-500); }
.photo-note { display: block; color: var(--ink-400); font-size: var(--font-12); }
.photos li { font-size: var(--font-13); color: var(--ink-700); line-height: 1.7; }

.keyframes { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.kframe { margin: 0; }
.kframe img {
  width: 100%;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.kframe figcaption { font-size: var(--font-12); color: var(--ink-500); margin-top: 6px; }

.note {
  margin-top: 8px;
  padding: 12px 14px;
  border-top: 1px dashed var(--border);
  font-size: var(--font-12);
  color: var(--ink-400);
  line-height: 1.7;
  display: flex;
  gap: 8px;
}
.note-ic { flex-shrink: 0; }
</style>
