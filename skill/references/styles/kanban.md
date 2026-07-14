# ============================================
# 看板风格 - 今日任务面板
# ============================================
# 三栏看板式布局：待办 → 进行中 → 今日完成
# 适合视觉化追踪进度

# 📋 今日工作面板
# 日期：{date}

---

## ⏳ 待办队列

| 优先级 | 任务 | 科目 | 预估 | DDL | 操作建议 |
|--------|------|------|------|-----|---------|
| {p1_icon} | {task} | {emoji}{subject} | ~{m}min | {ddl_label} | 先做这个 |
| {p2_icon} | {task} | {emoji}{subject} | ~{m}min | {ddl_label} | 排入时段 |
| {p3_icon} | {task} | {emoji}{subject} | ~{m}min | {ddl_label} | 有空再做 |

---

## 🏃 建议执行顺序

```
{time_slot_1} ── {task_1} ({minutes}min)
      │
{time_slot_2} ── {task_2} ({minutes}min)
      │
    [☕ 休息 {break_min} 分钟]
      │
{time_slot_3} ── {task_3} ({minutes}min)
      │
{time_slot_4} ── {task_4} ({minutes}min)
```

---

## 📊 今日统计

| 维度 | 数值 |
|------|------|
| 总任务数 | {task_count} |
| 总预估时间 | {total_minutes} 分钟 |
| 深度工作 | {deep_minutes} 分钟 ({deep_pct}%) |
| 浅层工作 | {shallow_minutes} 分钟 ({shallow_pct}%) |
| 休息次数 | {break_count} 次 |
| 今日 DDL 数 | {urgent_count} 个 |

> 💡 建议：{advice}
