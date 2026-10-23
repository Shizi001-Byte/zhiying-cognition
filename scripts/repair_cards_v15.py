#!/usr/bin/env python3
"""
认知卡片v1.5修复脚本
修复内容：
1. 6张核心法则截断（从详细解释提取完整总结）
2. 案例故事类C-001~C-004核心法则从案例描述改为教训总结
3. 统一核心法则格式：教训/原则在前，案例在后
"""
import json
import os
import shutil
from datetime import datetime

INPUT = "cognition_cards_v1.4_repaired.json"
OUTPUT = "cognition_cards_v1.5_repaired.json"

# 手动校准的核心法则（从详细解释中提取，非编造）
MANUAL_LAW_FIXES = {
    # 6张截断法则
    "P-035": "管道可以越建越粗：本金越大利息越多，利息越多可再投入的越多，复利正向循环；前半段慢后半段快",
    "M-036": "彼得·林奇：从日常生活中选股（你了解的公司），与有效市场理论相反，13年年化29.2%",
    "P-041": "资产配置（股债比例）决定90%以上回报，选具体基金/股票只决定不到10%",
    "P-063": "靠运气赚大钱的人本质是俄罗斯轮盘幸存者，策略有巨大隐藏风险只是还没爆；技能结果可重复，运气结果不可重复",
    "M-065": "神奇公式：资本回报率高+盈利收益率高，1988-2004年年化30.8%，跑赢标普500近20个百分点",
    "M-066": "资金管理与止损：单笔风险不超总资金10%，永远保留20-30%现金，分批建仓，盈利后提取部分利润",
    # 案例故事类核心法则改为教训总结
    "C-001": "以贷养贷是债务深渊，停止以贷养贷是上岸第一步；四步法：停借→盘点排序→协商延期→雪崩法先还高息",
    "C-002": "创业失败欠巨债，放下身段去打工用稳定收入还债比想翻本靠谱；雪球法先还小额建立成就感",
    "C-003": "永远不要给人担保，抹不开面子的代价是数年辛苦；担保了就要承担，协商分期+开源节流+提取公积金",
    "C-004": "内部消息传到你耳朵里已经不是内部消息，全部积蓄投入一只股票是赌博不是投资",
    "C-010": "你最熟悉的领域就是最好的内容方向，不要等准备好了再开始，边做边学坚持输出",
    "C-011": "失业后最忌讳高不成低不就，降低预期不是认输是务实，先活下来再谋发展",
}

def main():
    with open(INPUT, 'r', encoding='utf-8') as f:
        cards = json.load(f)
    print(f"加载v1.4卡片: {len(cards)}张")

    fixed_count = 0
    for card in cards:
        cid = card['卡片ID']
        if cid in MANUAL_LAW_FIXES:
            card['核心法则'] = MANUAL_LAW_FIXES[cid]
            card['_v1.5修复'] = "核心法则从案例描述/截断改为教训总结"
            fixed_count += 1

    short_law = [c for c in cards if len(c.get('核心法则','')) < 15]
    print(f"修复核心法则: {fixed_count}张")
    print(f"核心法则<15字: {len(short_law)}张")
    print(f"核心法则平均长度: {sum(len(c['核心法则']) for c in cards)/len(cards):.0f}字")

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    print(f"已保存v1.5到: {OUTPUT}")

if __name__ == '__main__':
    main()
