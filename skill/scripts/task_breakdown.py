#!/usr/bin/env python3
"""
任务安排 Skill - 自动拆解引擎
==============================
功能：
1. 计算拆解指数（难度+步骤模糊度+时间紧迫）
2. 根据科目选择拆解骨架
3. 生成可执行的子任务列表
4. 子任务继承父任务属性 + 按历史速度分配耗时
"""

import json
import math
import re
from datetime import date, datetime
from typing import Any

Task = dict[str, Any]

# ──────────────────────────────────────────
# 科目拆解模板定义
# ──────────────────────────────────────────

BREAKDOWN_TEMPLATES = {
    "AI创作": {
        "steps": [
            {"name": "前置学习", "ratio": 0.15},
            {"name": "方案设计", "ratio": 0.20},
            {"name": "核心实现", "ratio": 0.35},
            {"name": "测试验证", "ratio": 0.15},
            {"name": "整理输出", "ratio": 0.15},
        ],
        "fill_template": lambda topic, step: step["name"],
    },
    "职业规划": {
        "steps": [
            {"name": "素材收集", "ratio": 0.20},
            {"name": "框架梳理", "ratio": 0.20},
            {"name": "内容撰写", "ratio": 0.30},
            {"name": "修改润色", "ratio": 0.15},
            {"name": "最终定稿", "ratio": 0.15},
        ],
        "fill_template": lambda topic, step: step["name"],
    },
    "读书笔记": {
        "steps": [
            {"name": "速读浏览", "ratio": 0.15},
            {"name": "精读标记", "ratio": 0.30},
            {"name": "摘录整理", "ratio": 0.20},
            {"name": "归纳总结", "ratio": 0.20},
            {"name": "输出笔记", "ratio": 0.15},
        ],
        "fill_template": lambda topic, step: step["name"],
    },
    "兴趣产物": {
        "steps": [
            {"name": "灵感构思", "ratio": 0.20},
            {"name": "快速原型", "ratio": 0.30},
            {"name": "打磨优化", "ratio": 0.30},
            {"name": "整理记录", "ratio": 0.20},
        ],
        "fill_template": lambda topic, step: step["name"],
    },
    "日常事务": {
        "steps": [
            {"name": "全面收集", "ratio": 0.20},
            {"name": "优先级分类", "ratio": 0.15},
            {"name": "逐一处理", "ratio": 0.45},
            {"name": "核对归档", "ratio": 0.20},
        ],
        "fill_template": lambda topic, step: step["name"],
    },
}

# ──────────────────────────────────────────
# 模糊度关键词（全局）
# ──────────────────────────────────────────

VAGUENESS_WORDS = [
    (9, ["搞定", "研究", "完成", "弄好", "搞", "弄", "处理", "收拾"]),
    (6, ["学习", "做", "准备", "看", "写", "搭建", "实现", "实验"]),
    (2, ["整理", "阅读", "修改", "回复", "检查", "归档", "删除"]),
]

SUBJECT_DIFFICULTY = {
    "AI创作": 4, "职业规划": 3, "读书笔记": 2, "兴趣产物": 2, "日常事务": 1,
}


# ──────────────────────────────────────────
# 核心函数
# ──────────────────────────────────────────


def extract_topic(task_name: str) -> str:
    """从任务名中提取"主题"部分"""
    # 去掉开头的动词
    for prefix in [
        "完成", "实现", "搞定", "准备", "学习", "阅读", "看",
        "写", "整理", "做", "处理", "搭建", "研究", "弄",
    ]:
        if task_name.startswith(prefix):
            return task_name[len(prefix):].strip()
    # 去掉"的XXX"
    for suffix in ["的任务", "的工作", "的事情", "的作业", "的项目"]:
        if task_name.endswith(suffix):
            return task_name[: -len(suffix)].strip()
    return task_name


def calc_vagueness_score(task_name: str) -> int:
    """计算步骤模糊度分数 (0-10)"""
    max_score = 0
    for score, words in VAGUENESS_WORDS:
        for w in words:
            if w in task_name:
                max_score = max(max_score, score)
    return max_score


def calc_difficulty_score(task: Task) -> float:
    """计算难度得分 (0-10)"""
    subject = task.get("subject", "兴趣产物")
    base = SUBJECT_DIFFICULTY.get(subject, 2)

    # 如果用户标注了具体难度，使用用户标注
    user_diff = task.get("difficulty")
    if user_diff and isinstance(user_diff, (int, float)) and 1 <= user_diff <= 5:
        base = user_diff

    return (base / 5.0) * 10.0


def calc_urgency_score(task: Task) -> float:
    """计算时间紧迫得分 (0-10)"""
    deadline_str = task.get("deadline")
    if not deadline_str:
        return 0

    try:
        d = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        days_left = (d - date.today()).days
    except (ValueError, TypeError):
        return 0

    if days_left <= 0:
        return 10
    elif days_left <= 1:
        return 8
    elif days_left <= 3:
        return 6
    elif days_left <= 7:
        return 4
    elif days_left <= 14:
        return 2
    elif days_left <= 30:
        return 1
    return 0


def calc_breakdown_index(task: Task) -> float:
    """计算拆解指数 (0-10)，≥7自动拆，≥5问用户"""
    diff_score = calc_difficulty_score(task) * 0.40
    vague_score = calc_vagueness_score(task.get("name", "")) * 0.35
    urgency_score = calc_urgency_score(task) * 0.25

    return round(diff_score + vague_score + urgency_score, 2)


def detect_breakdown_needed(
    tasks: list[Task],
    auto_threshold: float = 7.0,
    ask_threshold: float = 5.0,
) -> dict[str, list[Task]]:
    """
    检测哪些任务需要拆解。
    返回: {"auto": [需要自动拆解的任务], "ask": [需要询问的任务], "skip": [不拆的任务]}
    """
    result: dict[str, list[Task]] = {"auto": [], "ask": [], "skip": []}

    for task in tasks:
        # 已经是子任务不重复拆
        if task.get("_is_subtask"):
            result["skip"].append(task)
            continue

        index = calc_breakdown_index(task)
        task["_breakdown_index"] = index

        if index >= auto_threshold:
            result["auto"].append(task)
            task["_breakdown_result"] = "auto"
        elif index >= ask_threshold:
            result["ask"].append(task)
            task["_breakdown_result"] = "ask"
        else:
            result["skip"].append(task)
            task["_breakdown_result"] = "skip"

    return result


def break_down_task(
    task: Task,
    history: dict | None = None,
) -> list[Task]:
    """将一个任务拆解为子任务列表"""
    subject = task.get("subject", "兴趣产物")
    template = BREAKDOWN_TEMPLATES.get(subject, BREAKDOWN_TEMPLATES["兴趣产物"])
    topic = extract_topic(task.get("name", ""))
    total_est = task.get("_estimated_minutes", 60)
    deadline = task.get("deadline")

    subtasks = []
    for i, step in enumerate(template["steps"]):
        sub_est = max(10, round(total_est * step["ratio"]))

        # 如果有历史速度，做速度修正
        if history and subject in history:
            hist_avg = history[subject].get("avg_minutes", 30)
            factor = hist_avg / 30.0
            sub_est = max(10, round(sub_est * factor))

        sub_name = f"{step['name']}：{task['name']}"

        subtask = {
            "name": sub_name,
            "subject": subject,
            "deadline": deadline if template["steps"].index(step) < len(template["steps"]) - 1 else deadline,
            "size": "small",
            "_is_subtask": True,
            "_parent_task": task.get("name"),
            "_step_name": step["name"],
            "_estimated_minutes": sub_est,
            "_sub_order": i,
            "_top_flag": task.get("_top_flag", False),
        }
        subtasks.append(subtask)

    return subtasks


def auto_breakdown_pipeline(
    tasks: list[Task],
    history: dict | None = None,
    threshold_auto: float = 7.0,
    threshold_ask: float = 5.0,
) -> dict:
    """
    完整拆解流水线:
    1. 检测哪些任务需要拆
    2. 自动拆解
    3. 返回拆解后的完整任务列表 + 询问列表
    """
    classified = detect_breakdown_needed(tasks, threshold_auto, threshold_ask)

    new_tasks: list[Task] = []
    task_ask: list[dict] = []

    # 自动拆解
    for task in classified["auto"]:
        broken = break_down_task(task, history)
        new_tasks.extend(broken)
        task_ask.append({
            "original_name": task.get("name"),
            "subject": task.get("subject"),
            "breakdown_index": task.get("_breakdown_index"),
            "decision": "auto",
            "subtasks": [s["name"] for s in broken],
        })

    # 跳过不拆的
    new_tasks.extend(classified["skip"])

    # 待询问的保持原样，不做拆解
    new_tasks.extend(classified["ask"])

    return {
        "tasks": new_tasks,
        "ask_list": classified["ask"],
        "action_log": task_ask,
        "stats": {
            "total_original": len(tasks),
            "auto_breakdown": len(classified["auto"]),
            "pending_ask": len(classified["ask"]),
            "skipped": len(classified["skip"]),
        },
    }


# ──────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────


def main():
    import argparse

    parser = argparse.ArgumentParser(description="自动拆解引擎")
    parser.add_argument("--input", "-i", type=str, help="任务 JSON 文件路径")
    parser.add_argument("--format", "-f", choices=["json", "text"], default="text")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        tasks = data if isinstance(data, list) else data.get("tasks", [])
        history = data.get("history") if not isinstance(data, list) else None
    else:
        # 内置示例
        tasks = [
            {
                "name": "完成 RAG 论文阅读笔记",
                "subject": "AI创作",
                "deadline": "2026-07-12",
                "size": "medium",
                "difficulty": 4,
                "_estimated_minutes": 60,
            },
            {
                "name": "搞定简历更新",
                "subject": "职业规划",
                "deadline": "2026-07-13",
                "size": "medium",
                "difficulty": 3,
                "_estimated_minutes": 45,
            },
            {
                "name": "整理上周周报",
                "subject": "日常事务",
                "deadline": "2026-07-11",
                "size": "small",
                "difficulty": 1,
                "_estimated_minutes": 15,
            },
        ]
        history = None

    result = auto_breakdown_pipeline(tasks, history)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  自动拆解分析报告  |  {date.today()}")
        print(f"{'='*60}")

        print(f"\n📊 概览: {result['stats']['total_original']} 个任务 → "
              f"自动拆解 {result['stats']['auto_breakdown']} 个, "
              f"待询问 {result['stats']['pending_ask']} 个, "
              f"跳过 {result['stats']['skipped']} 个\n")

        for log in result["action_log"]:
            print(f"🔨 自动拆解 [{log['subject']}]: {log['original_name']}")
            print(f"   拆解指数: {log['breakdown_index']}")
            for s in log["subtasks"]:
                print(f"   ├ {s}")
            print()

        for task in result["ask_list"]:
            idx = task.get("_breakdown_index", "?")
            print(f"❓ 待询问 [{task.get('subject')}]: {task.get('name')} (指数: {idx})")

        print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
