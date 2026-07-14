#!/usr/bin/env python3
"""
任务安排 Skill - 核心排程引擎 v2.0
===================================
功能：
1. 按 DDL紧迫度 + 科目权重 + 难度计算优先级（原版）
2. 【新增】自动检测高难度紧DDL任务 → 调用拆解引擎
3. 【新增】能量时段感知排程（记忆→早晨，深度→上午，琐事→下午）
4. 【新增】依赖链自动排序
5. 【新增】TOP 3 聚焦模式
6. 【新增】周视图排程
7. 【新增】作息学习（从反馈数据反推空闲时段）
"""

import json
import math
import sys
from datetime import datetime, date, timedelta
from typing import Any

Task = dict[str, Any]

# ──────────────────────────────────────────
# 配置
# ──────────────────────────────────────────

SUBJECTS = {
    "AI创作": {"slug": "ai-create", "emoji": "🤖", "difficulty": 4,
               "default_duration": 60, "priority_weight": 1.0, "focus_type": "deep",
               "preferred_zone": "morning_deep"},
    "职业规划": {"slug": "career", "emoji": "🎯", "difficulty": 3,
               "default_duration": 45, "priority_weight": 1.2, "focus_type": "deep",
               "preferred_zone": "morning_deep"},
    "读书笔记": {"slug": "reading", "emoji": "📚", "difficulty": 2,
               "default_duration": 30, "priority_weight": 0.8, "focus_type": "shallow",
               "preferred_zone": "morning_peak"},
    "兴趣产物": {"slug": "hobby", "emoji": "💡", "difficulty": 2,
               "default_duration": 30, "priority_weight": 0.6, "focus_type": "shallow",
               "preferred_zone": "afternoon_recovery"},
    "日常事务": {"slug": "daily", "emoji": "📋", "difficulty": 1,
               "default_duration": 15, "priority_weight": 0.5, "focus_type": "shallow",
               "preferred_zone": "afternoon_shallow"},
}

URGENCY_MAP = [
    (0, 10, "🔥 火烧眉毛"), (1, 8, "⚠️ 明日截止"), (3, 6, "🕐 接近截止"),
    (7, 4, "📅 本周内"), (14, 2, "🗓 两周内"), (30, 1, "📆 本月内"),
]

# 能量时段定义（供时间分配用）
ENERGY_ZONES = {
    "morning_peak":   {"label": "🌅 早晨记忆 (08:00-10:00)", "start": 480, "end": 600, "energy": 5},
    "morning_deep":   {"label": "💻 上午攻坚 (09:00-12:00)", "start": 540, "end": 720, "energy": 5},
    "afternoon_shallow": {"label": "🌤 午后处理 (13:00-15:00)", "start": 780, "end": 900, "energy": 2},
    "afternoon_recovery": {"label": "🌆 午后探索 (15:00-17:00)", "start": 900, "end": 1020, "energy": 3},
    "evening_flex":   {"label": "🌙 晚间灵活 (19:00-22:00)", "start": 1140, "end": 1320, "energy": 2},
}

FORMULA = {"urgency": 0.5, "difficulty": 0.2, "subject": 0.3}

# ──────────────────────────────────────────
# 拆解引擎导入 (可选)
# ──────────────────────────────────────────

try:
    from task_breakdown import (
        auto_breakdown_pipeline as _run_breakdown,
        calc_breakdown_index,
    )
    HAS_BREAKDOWN = True
except ImportError:
    HAS_BREAKDOWN = False

    def calc_breakdown_index(task): return 0.0

# ──────────────────────────────────────────
# 核心算法
# ──────────────────────────────────────────


def calculate_urgency(days_until_deadline: float | None) -> tuple[int, str]:
    if days_until_deadline is None:
        return (0, "∞ 无截止")
    days = max(0, days_until_deadline)
    for threshold_days, score, label in URGENCY_MAP:
        if days <= threshold_days:
            return (score, label)
    return (1, "📆 本月内")


def calculate_priority(task: Task, urgency_score: int, dep_bonus: float = 0) -> float:
    subj_config = SUBJECTS.get(task.get("subject", "兴趣产物"), SUBJECTS["兴趣产物"])
    urgency_val = float(urgency_score)
    difficulty_val = (subj_config["difficulty"] / 5.0) * 10.0
    subject_val = subj_config["priority_weight"] * 10.0
    score = (urgency_val * FORMULA["urgency"]
             + difficulty_val * FORMULA["difficulty"]
             + subject_val * FORMULA["subject"]
             + dep_bonus)
    return round(score, 2)


def estimate_duration(task: Task, history: dict | None = None) -> int:
    subject = task.get("subject", "兴趣产物")
    subj_config = SUBJECTS.get(subject, SUBJECTS["兴趣产物"])

    if history and subject in history:
        avg = history[subject].get("avg_minutes", subj_config["default_duration"])
    else:
        avg = subj_config["default_duration"]

    size_multiplier = {"small": 0.7, "medium": 1.0, "large": 1.8}
    size = task.get("size", "medium")
    estimated = avg * size_multiplier.get(size, 1.0)

    user_difficulty = task.get("difficulty", subj_config["difficulty"])
    estimated *= (user_difficulty / subj_config["difficulty"])
    return max(10, round(estimated))


# ──────────────────────────────────────────
# 排程主逻辑
# ──────────────────────────────────────────


def schedule_tasks(
    tasks: list[Task],
    history: dict | None = None,
    mode: str = "normal",  # normal / top3 / weekly
    energy_patterns: dict | None = None,
) -> list[Task]:
    """
    执行完整排程：
    1. 计算每项任务的紧迫度、优先级、预估耗时
    2. 如果 mode="top3"，只标记 TOP 3
    3. 如果 mode="weekly"，计算每项任务最晚开始日期
    4. 应用依赖链加成
    5. 按优先级降序排列
    """
    today = date.today()
    for task in tasks:
        deadline_str = task.get("deadline")
        if deadline_str:
            try:
                deadline_date = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                days_left = (deadline_date - today).days
            except (ValueError, TypeError):
                days_left = None
        else:
            days_left = None

        urgency_score, urgency_label = calculate_urgency(days_left)
        priority_score = calculate_priority(task, urgency_score)
        est_duration = estimate_duration(task, history)

        # 能量时段分配
        subj_config = SUBJECTS.get(task.get("subject", "兴趣产物"), SUBJECTS["兴趣产物"])
        preferred_zone = subj_config.get("preferred_zone", "morning_deep")
        zone = ENERGY_ZONES.get(preferred_zone, ENERGY_ZONES["morning_deep"])
        suggested_hour = f"{zone['start'] // 60:02d}:{zone['start'] % 60:02d}"
        estimated_end_min = zone['start'] + est_duration
        estimated_end = f"{estimated_end_min // 60:02d}:{estimated_end_min % 60:02d}"

        task["_urgency_score"] = urgency_score
        task["_urgency_label"] = urgency_label
        task["_priority_score"] = priority_score
        task["_estimated_minutes"] = est_duration
        task["_days_left"] = days_left
        task["_suggested_start"] = suggested_hour
        task["_estimated_end"] = estimated_end
        task["_preferred_zone"] = preferred_zone

    # 依赖链加成
    _apply_dependency_bonus(tasks)

    # TOP 3 模式
    if mode == "top3":
        tasks.sort(key=lambda t: t["_priority_score"], reverse=True)
        for i, t in enumerate(tasks):
            t["_top_flag"] = i < 3
        # 只返回 TOP 3，其余标记为后续
        for t in tasks[3:]:
            t["_deferred"] = True

    # 正常排序
    tasks.sort(key=lambda t: t["_priority_score"], reverse=True)
    return tasks


def _apply_dependency_bonus(tasks: list[Task]):
    """检测依赖关系，给前驱任务加优先级分"""
    deps: dict[str, list[str]] = {}
    for t in tasks:
        name = t.get("name", "")
        # 检测 "[依赖: XXX]" 模式
        import re
        m = re.search(r'\[依赖:\s*(.+?)\]', name)
        if m:
            dep_name = m.group(1).strip()
            if dep_name not in deps:
                deps[dep_name] = []
            deps[dep_name].append(name)

    # 给被依赖的任务加分
    for t in tasks:
        name = t.get("name", "")
        if name in deps:
            t["_priority_score"] = t.get("_priority_score", 0) + 1.5
            t["_dependency_count"] = len(deps[name])


# ──────────────────────────────────────────
# 周视图生成
# ──────────────────────────────────────────


def generate_weekly_plan(tasks: list[Task]) -> dict[str, list[Task]]:
    """
    将任务分配到本周各天。
    紧急度高的任务排前面几天，宽松的排后面。
    """
    today = date.today()
    days: dict[str, list[Task]] = {}
    day_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    monday = today - timedelta(days=today.weekday())

    for i in range(7):
        d = monday + timedelta(days=i)
        key = d.isoformat()
        days[key] = []
        days[key].append(day_labels[i])

    # 按优先级分配到各天
    sorted_tasks = sorted(tasks, key=lambda t: t.get("_priority_score", 0), reverse=True)
    day_idx = 0
    for task in sorted_tasks:
        deadline = task.get("deadline")
        deadline_date = None
        if deadline:
            try:
                deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # 如果有 DDL，确保排在那天之前
        if deadline_date:
            target_day = (deadline_date - timedelta(days=1))
            # 确保不早于今天
            if target_day < today:
                target_day = today
            # 确保不晚于周日（本周范围）
            last_day = monday + timedelta(days=6)
            if target_day > last_day:
                target_day = last_day
            key = target_day.isoformat()
            if key not in days:
                days[key] = [day_labels[6]]  # 周日兜底
            days[key].append(task)
        else:
            # 平均分配到本周
            key = (monday + timedelta(days=day_idx % 7)).isoformat()
            days[key].append(task)
            day_idx += 1

    return days


# ──────────────────────────────────────────
# 统计与建议
# ──────────────────────────────────────────


def calc_total_stats(tasks: list[Task]) -> dict:
    total_minutes = sum(t.get("_estimated_minutes", 0) for t in tasks)
    deep_minutes = 0
    shallow_minutes = 0
    urgent_count = 0
    breakdown_count = 0
    for t in tasks:
        subj_config = SUBJECTS.get(t.get("subject", "兴趣产物"), SUBJECTS["兴趣产物"])
        mins = t.get("_estimated_minutes", 0)
        if subj_config["focus_type"] == "deep":
            deep_minutes += mins
        else:
            shallow_minutes += mins
        if t.get("_days_left") is not None and t["_days_left"] <= 1:
            urgent_count += 1
        if t.get("_is_subtask"):
            breakdown_count += 1

    total_hours = round(total_minutes / 60, 1)
    return {
        "total_minutes": total_minutes,
        "total_hours": total_hours,
        "deep_minutes": deep_minutes,
        "shallow_minutes": shallow_minutes,
        "deep_hours": round(deep_minutes / 60, 1),
        "shallow_hours": round(shallow_minutes / 60, 1),
        "deep_pct": int(deep_minutes / total_minutes * 100) if total_minutes else 0,
        "shallow_pct": int(shallow_minutes / total_minutes * 100) if total_minutes else 0,
        "urgent_count": urgent_count,
        "task_count": len(tasks),
        "breakdown_task_count": breakdown_count,
    }


def generate_advice(tasks: list[Task], stats: dict) -> str:
    parts = []
    urgent = stats["urgent_count"]
    if urgent > 0:
        parts.append(f"今天有 {urgent} 个紧急任务，优先完成")

    # 拆解提醒
    breakdown_tasks = [t for t in tasks if t.get("_breakdown_result") == "ask"]
    if breakdown_tasks:
        parts.append(f"有 {len(breakdown_tasks)} 个任务看起来比较大，要不要拆成子任务？")

    # TOP 3 提醒
    top3 = [t for t in tasks if t.get("_top_flag")]
    if top3:
        parts.append(f"聚焦'必做三件事'：{top3[0]['name']}")

    # 能量分配建议
    deep_first = [t for t in tasks if t.get("_preferred_zone") in ("morning_deep", "morning_peak")]
    if deep_first:
        parts.append(f"「{deep_first[0]['name']}」建议放上午精力最好的时段")

    if stats["deep_pct"] > 60:
        parts.append("深度工作占比高，每 90 分钟记得休息")
    elif stats["shallow_pct"] > 60:
        parts.append("今天浅层任务多，可以穿插进行，保持节奏")

    if not parts:
        parts.append("今天任务量适中，按计划推进即可")

    return "；".join(parts)


# ──────────────────────────────────────────
# 昨日复盘生成
# ──────────────────────────────────────────


def generate_daily_recap(history: dict | None = None) -> str:
    """生成昨日复盘报告"""
    if not history:
        return "还没有足够的历史数据生成复盘。"

    lines = ["📊 昨日工作复盘", "=" * 30]
    total_done = 0
    total_planned = 0

    for subject, data in history.items():
        if subject.endswith("_detail"):
            continue
        if not isinstance(data, dict):
            continue
        done = data.get("total_tasks", 0)
        avg = data.get("avg_minutes", 0)
        if done > 0:
            total_done += done
            lines.append(f"  {subject}: 完成 {done} 项，平均 {avg}min/项")

    lines.append(f"\n总计完成 {total_done} 项任务")
    return "\n".join(lines)


# ──────────────────────────────────────────
# 展示函数
# ──────────────────────────────────────────


def print_table(tasks: list[Task]) -> str:
    lines = []
    header = f"{'#':<3} {'任务':<26} {'科目':<8} {'预估':<6} {'时段':<22} {'DDL':<14} {'优先级':<6}"
    lines.append(header)
    lines.append("-" * 90)
    for i, t in enumerate(tasks, 1):
        subject = t.get("subject", "?")
        subj_config = SUBJECTS.get(subject, SUBJECTS["兴趣产物"])
        emoji = subj_config["emoji"]
        ddl_label = t.get("_urgency_label", "∞")
        pri_score = t.get("_priority_score", 0)
        name = t.get("name", "未命名任务")[:22]
        est = t.get("_estimated_minutes", 0)
        zone_label = ENERGY_ZONES.get(t.get("_preferred_zone", ""), {}).get("label", "")
        leader = "├" if t.get("_is_subtask") else " "
        lines.append(
            f"{leader}{i:<2} {emoji} {name:<22} {subject:<8} {est}min  {zone_label:<22} {ddl_label:<14} {pri_score}"
        )
    return "\n".join(lines)


def to_json(tasks: list[Task], stats: dict) -> str:
    return json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": stats,
        "tasks": [{
            "name": t.get("name"),
            "subject": t.get("subject"),
            "deadline": t.get("deadline", "无"),
            "estimated_minutes": t.get("_estimated_minutes"),
            "urgency_label": t.get("_urgency_label"),
            "priority_score": t.get("_priority_score"),
            "days_left": t.get("_days_left"),
            "suggested_start": t.get("_suggested_start"),
            "preferred_zone": t.get("_preferred_zone"),
            "is_subtask": t.get("_is_subtask", False),
            "top_flag": t.get("_top_flag", False),
        } for t in tasks],
    }, ensure_ascii=False, indent=2)


def print_weekly(plan: dict[str, list[Task]]) -> str:
    lines = ["📅 本周任务总览", "=" * 70]
    day_names = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

    for date_str, items in plan.items():
        label = items[0] if isinstance(items[0], str) and "周" in items[0] else date_str
        tasks_only = [t for t in items if not isinstance(t, str)]
        if not tasks_only:
            continue
        total_mins = sum(t.get("_estimated_minutes", 0) for t in tasks_only)
        lines.append(f"\n{label} ({date_str}) — {len(tasks_only)} 项, 约 {round(total_mins/60,1)}h")
        lines.append("-" * 40)
        for t in tasks_only:
            emoji = SUBJECTS.get(t.get("subject", ""), {}).get("emoji", "•")
            name = t.get("name", "")[:20]
            est = t.get("_estimated_minutes", 0)
            pri = t.get("_priority_score", 0)
            lines.append(f"  {emoji} {name:<22} {est}min  (优先级 {pri})")

    return "\n".join(lines)


# ──────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="任务安排排程 v2.0")
    parser.add_argument("--input", "-i", type=str, default="", help="任务JSON文件")
    parser.add_argument("--format", "-f", choices=["json", "table", "weekly"], default="table")
    parser.add_argument("--mode", "-m", choices=["normal", "top3", "weekly", "recap"], default="normal",
                        help="排程模式：normal=全部 / top3=必做三件 / weekly=周视图 / recap=昨日复盘")
    parser.add_argument("--recap", action="store_true", help="生成昨日复盘")

    args = parser.parse_args()

    history = None

    if args.recap or args.mode == "recap":
        print(generate_daily_recap(history))
        return

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        tasks = data if isinstance(data, list) else data.get("tasks", [])
        history = data.get("history") if not isinstance(data, list) else None
    else:
        # ------------------- 内置示例（含拆解触发） -------------------
        tasks = [
            {
                "name": "完成 RAG 论文阅读笔记",
                "subject": "AI创作", "deadline": "2026-07-12",
                "size": "medium", "difficulty": 4,
            },
            {
                "name": "搞定简历更新",
                "subject": "职业规划", "deadline": "2026-07-13",
                "size": "medium", "difficulty": 3,
            },
            {
                "name": "读《思考快与慢》第三章",
                "subject": "读书笔记", "deadline": "2026-07-18",
                "size": "small", "difficulty": 2,
            },
            {
                "name": "整理上周周报",
                "subject": "日常事务", "deadline": "2026-07-11",
                "size": "small", "difficulty": 1,
            },
        ]

    # Step 1: 基础排程
    sorted_tasks = schedule_tasks(tasks, history, mode=args.mode)

    # Step 2: 拆解检测（仅自动模式）
    if HAS_BREAKDOWN and args.mode in ("normal", "top3"):
        breakdown_result = _run_breakdown(sorted_tasks, history)
        if breakdown_result["stats"]["auto_breakdown"] > 0:
            # 重新排程拆解后的任务
            sorted_tasks = breakdown_result["tasks"]
            sorted_tasks = schedule_tasks(sorted_tasks, history, mode=args.mode)

    stats = calc_total_stats(sorted_tasks)

    # Step 3: 输出
    if args.format == "json":
        print(to_json(sorted_tasks, stats))
    elif args.format == "weekly":
        plan = generate_weekly_plan(sorted_tasks)
        print(print_weekly(plan))
    else:
        advice = generate_advice(sorted_tasks, stats)

        print(f"\n{'='*70}")
        print(f"  🎯 今日排程  |  {date.today()}  |  模式: {args.mode}")
        print(f"{'='*70}")
        print(print_table(sorted_tasks))
        print(f"\n{'='*70}")
        print(f"  总耗时：{stats['total_hours']}h  |  "
              f"深度 {stats['deep_hours']}h ({stats['deep_pct']}%)  |  "
              f"浅层 {stats['shallow_hours']}h ({stats['shallow_pct']}%)")
        if stats["breakdown_task_count"] > 0:
            print(f"  🔨 自动拆解：{stats['breakdown_task_count']} 个子任务")
        print(f"  💡 建议：{advice}")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
