# 测试数据说明

本目录包含生活助手 Skill 的测试数据集，覆盖排程与饮食两大功能模块。所有数据为虚构示例，展示 Skill 的数据格式与结构，不含真实用户信息。

## 数据文件清单

| 文件 | 模块 | 说明 |
|------|------|------|
| `sample_base.json` | 共享 | 用户基本信息（性别/身高/忌口/口味/作息/身份关键词） |
| `sample_current.json` | 共享 | 当前活跃模式（diet_mode + schedule_mode） |
| `sample_tasks_input.json` | 排程 | 测试用任务列表 + 历史耗时数据 |
| `sample_diet_profile.json` | 饮食 | 饮食模式档案（体重/目标/预算/运动） |
| `sample_diet_logs.json` | 饮食 | 近期饮食记录（含 AI 评估） |
| `sample_health.json` | 饮食 | 临时身体状况（嗓子疼场景） |
| `sample_taste.json` | 饮食 | 口味偏好学习数据 |
| `sample_canteen.json` | 饮食 | 食堂窗口映射数据 |
| `sample_weight.json` | 饮食 | 体重追踪数据 |
| `sample_cycle.json` | 饮食 | 生理期历史记录（周期从实际间隔计算，非固定默认值） |

## 示例用户画像

**用户名**：示例用户（虚构）
**身份**：学生（由"作业""实验"关键词自动推断）
**作息**：正常型（7:30起床 / 23:00入睡）
**饮食模式**：增肌期
**排程模式**：学期模式
**忌口**：海鲜过敏
**口味**：酸+甜

> ⚠️ 以上为虚构示例数据，仅展示 Skill 数据格式。实际使用时，新用户数据由 AI 冷启动流程自动采集。

## 使用方式

### 排程模块测试
```bash
python skill/scripts/scheduler.py --input data/sample_tasks_input.json --format table
python skill/scripts/scheduler.py --input data/sample_tasks_input.json --format json
python skill/scripts/scheduler.py --input data/sample_tasks_input.json --format weekly --mode weekly
python skill/scripts/scheduler.py --input data/sample_tasks_input.json --mode top3
```

### 拆解引擎测试
```bash
python skill/scripts/task_breakdown.py --input data/sample_tasks_input.json --format text
python skill/scripts/task_breakdown.py --input data/sample_tasks_input.json --format json
```

### 饮食模块测试
```bash
# 需设置环境变量 GEMINI_API_KEY
python skill/scripts/diet_manager.py recommend 示例用户
python skill/scripts/diet_manager.py record 示例用户 "番茄炒蛋+米饭+花生米"
python skill/scripts/diet_manager.py data 示例用户
python skill/scripts/diet_manager.py weekly 示例用户
```
