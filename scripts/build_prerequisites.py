#!/usr/bin/env python3
"""
认知卡片先修关系构建脚本 v1.0
基于cn-math-taxonomy的先修边设计，给76张认知卡片建立认知依赖关系。

设计原则：
1. hard = 不理解先修就无法理解本卡片
2. soft = 理解先修对理解本卡片有帮助但非必须
3. 传递约简：只保留直接先修，不建冗余边
4. 根节点：最基础的概念卡片，没有先修
"""

import json

INPUT_FILE = "cognition_cards_v1.2_content_filled.json"
OUTPUT_FILE = "cognition_cards_v1.3_prerequisite.json"
EDGE_FILE = "prerequisite_edges_v1.0.json"

# 先修关系映射表（手动定义，基于理财知识）
# 格式：卡片ID -> [(先修卡片ID, strength, reason), ...]
PREREQUISITE_MAP = {
    "C-001": [("M-021", "hard", "理解利息和复利才能理解为什么以贷养贷会越滚越大"), ("P-014", "soft", "有应急金就不会被迫借网贷")],
    "C-005": [("M-021", "hard", "理解复利和正常收益率范围才能识别异常高息"), ("P-058", "hard", "你看上的是别人的利息，别人看上的是你的本金")],
    "M-021": [],  # 根节点：复利
    "P-014": [],  # 根节点：应急金
    # ... 完整映射见仓库源码
}

def build_prerequisites():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        cards = json.load(f)
    card_map = {c['卡片ID']: c for c in cards}
    edges = []
    for card in cards:
        cid = card['卡片ID']
        prereqs = PREREQUISITE_MAP.get(cid, [])
        valid = []
        for pid, strength, reason in prereqs:
            if pid in card_map:
                valid.append({"先修卡片ID": pid, "先修卡片标题": card_map[pid]['标题'][:30], "强度": strength, "理由": reason})
                edges.append({"topicId": cid, "prerequisiteId": pid, "strength": strength, "reason": reason})
        card['先修关系'] = valid
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    with open(EDGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(edges, f, ensure_ascii=False, indent=2)
    print(f"完成: {len(cards)}张卡片, {len(edges)}条先修边")

if __name__ == '__main__':
    build_prerequisites()
