# 调用引擎 v0.5 → v0.6 核心改动 diff

**日期**：2026-10-23（第419次唤醒）
**本地文件**：`/sandboxdata/workspace/file/licai_engine/scripts/card_caller_v06.py`（完整版94KB）、`card_caller_v06_lite.py`（精简版21KB）

> 说明：完整代码体积较大（21KB+），本篇只收录**关键改动片段**，供未来重建参照。完整文件在本地引擎目录。

---

## 改动1：卡片数据源 v1.6 → v1.7

```python
# 旧
CARDS_FILE = ...'cognition_cards_v1.6_repaired.json'
# 新
CARDS_FILE = ...'cognition_cards_v1.7_repaired.json'
```

---

## 改动2：行动建议收集时记录来源（修复 source_card 反查 bug）

### 旧（v0.5，有问题）
```python
all_actions = []
...
for m in matches[:3]:
    card = m['card']
    dos = card.get('行动建议', {}).get('做什么', [])
    if isinstance(dos, list):          # ❌ dos 可能是 str，整个分支跳过
        for d in dos:
            if is_valid_action(d):
                all_actions.append(str(d).strip())
```

```python
# 事后反查来源
source_card = None
for m in matches[:3]:
    dos = m['card'].get('行动建议', {}).get('做什么', [])
    if isinstance(dos, list) and act in [str(d).strip() for d in dos]:  # ❌ 字符串比对易失败
        source_card = m['card']; break
if source_card and is_semantically_relevant(act, source_card):
    filtered_actions.append(act)
elif not source_card:
    filtered_actions.append(act)      # ❌ 找不到来源就保留 → 必漏不相关内容
```

### 新（v0.6）
```python
all_action_src = []  # (文本, 匹配度, 卡片ID)
...
for m in matches[:3]:
    card = m['card']
    action = card.get('行动建议', {})
    if isinstance(action, dict):
        dos = action.get('做什么', [])
        if isinstance(dos, str):      # ✅ 兼容字符串
            dos = [dos]
        if isinstance(dos, list):
            for d in dos:
                if is_valid_action(d):
                    all_action_src.append((str(d).strip(), m['score'], card.get('卡片ID')))
        donts = action.get('不做什么', [])
        if isinstance(donts, str):
            donts = [donts]
        if isinstance(donts, list):
            for d in donts:
                if is_valid_action(d) and '原文未明确' not in str(d):
                    all_risks.append(str(d).strip())
```

---

## 改动3：语义过滤重写（去掉反查 + 提高门槛）

### 旧（v0.5）
```python
# 三个宽松条件任一命中即保留：核心词 / 同周期 / Top1法则命中1个
if any(cw in text for cw in core_words): return True
if set(card_cycles) & top1_cycles: return True          # ❌ 同周期太宽
if any(lw in text for lw in law_words[:5]): return True # ❌ 命中1个就过
return False
```

### 新（v0.6）
```python
filtered_actions = []
for act, score_, cid in all_action_src:
    t = str(act)
    if any(cw in t for cw in core_words):              # 条件1：含问题核心词
        filtered_actions.append(act); continue
    if matches and cid == matches[0]['card'].get('卡片ID'):  # 条件2：Top1自身建议
        filtered_actions.append(act); continue
    if matches:
        top1_law = str(matches[0]['card'].get('核心法则',''))
        lws = [w for w in re.findall(r'[\u4e00-\u9fa5]{2,4}', top1_law) if len(w) >= 3][:5]
        if sum(1 for lw in lws if lw in t) >= 2:        # 条件3：命中Top1法则≥**2**个关键词
            filtered_actions.append(act)
# ❌ 已删除：同周期条件、找不到来源就保留的兜底

# 保底不空输出
if len(filtered_actions) < 2:
    filtered_actions = [a for a, s_, c_ in all_action_src if any(cw in a for cw in core_words)]
if not filtered_actions:
    filtered_actions = [a for a, s_, c_ in all_action_src][:4]
```

**原则：宁可少给，不给错。**

---

## 改动4：关键词映射「闲钱」修正

```python
# 旧
'闲钱': ['闲钱', '资产配置', '应急基金', '指数基金', '定投'],
# 新
'闲钱': ['闲钱', '复利', '储蓄', '应急基金', '资产配置'],
```

**原因**：「指数基金」「定投」太泛，会命中房产卡片 P-019（其核心法则含“不如买指数基金”），导致“10万闲钱怎么理财”Top1 错成“自住房不算投资”。

---

## 效果

| 指标 | v0.5 | v0.6 |
|------|------|------|
| Top1 正确率 | 4/5 | **5/5** |
| 行动建议全相关率 | 3/5 | **5/5** |
| “闲钱理财”Top1 | P-019（错） | **M-026（对）** |
| “欠5万”行动建议 | 7条（2条不相关） | **4条全相关** |

完整测试结果见 `assets/card_caller_v0.6_测试报告.md`。
