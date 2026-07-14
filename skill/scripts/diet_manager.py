#!/usr/bin/env python3
"""AI饮食管家 v3.0 - 结构为主卡路里为辅(Python标准库+免费Gemini API)
环境变量: GEMINI_API_KEY (https://aistudio.google.com/apikey 免费获取)
数据存储: D:/课堂/uwuza/.life-data/ (与任务排程Skill共享)
"""
import json, os, sys, base64, urllib.request, datetime

KEY = os.environ.get("GEMINI_API_KEY", "")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={KEY}"
ROOT = "D:/课堂/uwuza/.life-data"


def llm(prompt, img=None):
    parts = [{"text": prompt}]
    if img and os.path.exists(img):
        with open(img, "rb") as f:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read()).decode()}})
    req = urllib.request.Request(URL, data=json.dumps({"contents": [{"parts": parts}]}).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"]


def _p(user, f, mode=None):
    if mode:
        return os.path.join(ROOT, "users", user, "diet", "modes", mode, f)
    if f in ("base.json", "current.json", "ACTIVE_USER"):
        return os.path.join(ROOT, "users", user, f)
    return os.path.join(ROOT, "users", user, "diet", f)


def load(user, f, mode=None):
    p = _p(user, f, mode)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def save(user, f, data, mode=None):
    p = _p(user, f, mode)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def cur_mode(user):
    c = load(user, "current.json")
    return c.get("diet_mode", c.get("mode", "稳定期"))


def season():
    m = datetime.date.today().month
    return "春夏秋冬"[(m % 12 + 3) // 3 - 1]


def ctx(user):
    mode = cur_mode(user)
    return mode, load(user, "base.json"), load(user, "profile.json", mode), load(user, "logs.json", mode)


def setup(user):
    print("=== AI饮食管家首次设置 ===\n第一层(必问):")
    r = input("1.忌口/过敏/身体状况(无则回车): ").strip()
    mode = input("2.模式(减脂期/增肌期/稳定期/省钱): ").strip() or "稳定期"
    b = {"restrictions": r, "tastes": "", "canteen": "", "gender": "", "height": "", "health_perm": ""}
    save(user, "base.json", b)
    c = load(user, "current.json"); c["diet_mode"] = mode
    save(user, "current.json", c)
    print(f"\n✅ 必问项已保存！模式:{mode}\n第二层(自然时机问,现在可跳过):")
    b["height"] = input("身高(cm): ").strip() or "?"
    b["gender"] = input("性别(男/女): ").strip() or "?"
    b["canteen"] = input("食堂窗口: ").strip() or "普通"
    b["tastes"] = input("口味(辣/甜/酸/咸/清淡): ").strip() or "不限"
    p = {"weight": input("体重(kg): ").strip() or "?", "goal": mode,
         "budget": input("日预算(元): ").strip() or "不限", "exercise": "不规律"}
    save(user, "base.json", b); save(user, "profile.json", p, mode)
    print(f"\n✅ {user} 档案完整保存！模式: {mode}")


def switch(user, args):
    mode = args[0] if args else input("切换到(减脂期/增肌期/稳定期/省钱): ").strip()
    c = load(user, "current.json"); c["diet_mode"] = mode
    save(user, "current.json", c)
    if not load(user, "profile.json", mode):
        p = {"weight": input(f"{mode}下体重kg: ").strip() or "?", "goal": mode,
             "budget": input("日预算元: ").strip() or "不限", "exercise": "不规律"}
        save(user, "profile.json", p, mode)
    print(f"🔄 已切换到 {mode}")


def recommend(user):
    mode, base, prof, logs = ctx(user)
    taste, canteen = load(user, "taste.json"), load(user, "canteen.json")
    wt, cy, hl = load(user, "weight.json"), load(user, "cycle.json"), load(user, "health.json", mode)
    # 尝试读取排程作息数据用于联动
    sched_base = {}; sp = os.path.join(ROOT, "users", user, "schedule", "current.json")
    if os.path.exists(sp): sched_base = json.load(open(sp, encoding="utf-8"))
    sched_mode = sched_base.get("schedule_mode", "")
    today = str(datetime.date.today())
    prompt = f"""你是大学食堂营养师，推荐下一餐。
核心理念：结构为主，卡路里为辅。日常看食物结构，隐形热量陷阱必须揭示(附参照物：半份米饭≈120卡/一顿午餐≈600卡)。
用户:{base.get('height','?')}cm {prof.get('weight','?')}kg {base.get('gender','')}
模式:{mode} 目标:{prof.get('goal','健康')}
预算:{prof.get('budget','不限')}元 忌口:{base.get('restrictions','无')}
身体状况(永久):{base.get('health_perm','无')} 身体状况(临时):{json.dumps(hl,ensure_ascii=False) or '无'}
口味:{base.get('tastes','不限')} 食堂:{base.get('canteen','普通')} 运动:{prof.get('exercise','不规律')}
季节:{season()} 排程模式:{sched_mode}
今日已吃:{json.dumps(logs.get(today,[]),ensure_ascii=False) or '无'}
近期:{json.dumps(list(logs.values())[-5:],ensure_ascii=False) or '无'}
口味学习:{json.dumps(taste,ensure_ascii=False) or '初期'} 窗口映射:{json.dumps(canteen,ensure_ascii=False) or '初期'}
体重趋势:{json.dumps(wt,ensure_ascii=False) or '无'}
生理期:{json.dumps(cy,ensure_ascii=False) if base.get('gender')=='女' else '不适用'}
推荐1-2选项+理由。偏好调整≠品类切换。如果用户说不想吃某类，只调优先级不删品类。"""
    print(llm(prompt))


def record(user, args):
    mode = cur_mode(user); base = load(user, "base.json"); logs = load(user, "logs.json", mode)
    hl = load(user, "health.json", mode)
    img, meal = None, " ".join(args) if args else input("吃了什么(或图片路径): ").strip()
    if os.path.exists(meal): img, meal = meal, "（看图识别）"
    prompt = f"""营养师评估这顿饭。核心理念：结构为主，卡路里为辅。
餐食:{meal} 用户:{base.get('gender','')} 模式:{mode}
忌口:{base.get('restrictions','无')} 身体状况(临时):{json.dumps(hl,ensure_ascii=False) or '无'} 季节:{season()}
评估要求:
1.目标-relative评分(1-10):这顿对当前模式(减脂/增肌/稳定/省钱)来说合不合理
2.好的地方:1句话
3.缺什么:1句话
4.下次怎么补:食堂可执行动作(如"晚餐自选窗口加清炒西兰花")
5.隐形热量陷阱检测:花生/沙拉酱/奶茶/油炸等看着不多但热量高的→揭示+参照物(半份米饭≈120卡)
6.如果有过敏/身体状况冲突→立刻优先报出
简短，不每顿报卡路里，只揭示陷阱。"""
    result = llm(prompt, img)
    logs.setdefault(str(datetime.date.today()), []).append(
        {"meal": meal, "eval": result, "time": datetime.datetime.now().strftime("%H:%M")})
    save(user, "logs.json", logs, mode)
    print(f"📋 {result}\n✅ 已记录到{mode}")


def weight(user, args):
    w = args[0] if args else input("体重kg: ").strip()
    d = load(user, "weight.json"); d[str(datetime.date.today())] = float(w)
    save(user, "weight.json", d); print(f"⚖️ {w}kg 已记录")


def cycle(user, args):
    d = args[0] if args else str(datetime.date.today())
    data = load(user, "cycle.json"); data.setdefault("periods", []).append(d)
    save(user, "cycle.json", data); print(f"🌸 生理期{d}已记录，下次自动推算")


def data(user):
    mode = cur_mode(user)
    print(json.dumps({"base": load(user, "base.json"), "diet_mode": mode,
        "profile": load(user, "profile.json", mode), "logs": load(user, "logs.json", mode),
        "taste": load(user, "taste.json"), "canteen": load(user, "canteen.json"),
        "weight": load(user, "weight.json"), "cycle": load(user, "cycle.json"),
        "health": load(user, "health.json", mode)}, ensure_ascii=False, indent=2))


def report(user):
    mode, base, prof, logs = ctx(user)
    if not logs: print("暂无记录，先 record 几餐。"); return
    wt = load(user, "weight.json"); taste = load(user, "taste.json")
    prompt = f"""营养师写叙事式周报。核心理念：结构为主，卡路里为辅。
近期饮食:{json.dumps(logs,ensure_ascii=False)}
{base.get('gender','')} 模式:{mode} 目标:{prof.get('goal','健康')} 预算:{prof.get('budget','不限')}
食堂:{base.get('canteen','普通')} 体重:{json.dumps(wt,ensure_ascii=False)} 口味学习:{json.dumps(taste,ensure_ascii=False)}
周报格式:
1.3句话narrative(整体如何+最大问题+预算情况)
2.热量趋势(日均粗估+参照物+超标日+超标原因)
3.模式检测(周末放飞/压力进食/低碳水陷阱/蛋白质不足等)
4.口味学习总结(最爱菜品+新发现)
5.下周3条行动项(食堂可执行的具体动作)
6.不记仇:永远"还不错,XX可以更好",不指责"""
    print(llm(prompt))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    user = sys.argv[2] if len(sys.argv) > 2 else "default"
    rest = sys.argv[3:]
    if cmd == "help":
        print("生活助手-饮食模块 v3.0\n数据路径: D:/课堂/uwuza/.life-data/\n用法: python diet_manager.py <命令> <用户> [参数]\n"
              "  setup <用户>           首次设置\n  recommend <用户>       推荐下顿\n"
              "  record <用户> '吃了啥'  记录一餐(可传图片)\n  weight <用户> <kg>    记录体重\n"
              "  cycle <用户> [日期]    记录生理期\n  switch <用户> <模式>   切换模式\n"
              "  data <用户>            导出数据\n  weekly <用户>         叙事式周报\n\n"
              "核心理念: 结构为主,卡路里为辅\n环境变量: GEMINI_API_KEY\n"
              "与任务排程Skill共享数据: .life-data/users/{用户}/base.json")
    else:
        {"setup": setup, "recommend": recommend, "record": lambda u, a: record(u, a),
         "weight": weight, "cycle": cycle, "switch": switch, "data": lambda u, a: data(u),
         "weekly": lambda u, a: report(u)}.get(cmd, lambda u, a: print(f"未知命令:{cmd}"))(user, rest)


if __name__ == "__main__":
    main()
