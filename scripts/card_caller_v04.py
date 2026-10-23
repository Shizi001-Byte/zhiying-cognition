#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知卡片调用引擎 v0.4（精简版）
# 完整版92KB含100+组关键词映射，本版保留核心30组。匹配/回溯/阈值/输出逻辑完全一致。
知盈认知资产库的核心组件：输入真实问题→匹配相关认知卡片→沿先修边回溯基础概念→分层输出导师式回答

v0.4 新增（2026-10-23 第416次唤醒）：
- 自适应回溯：匹配到高级卡片后，沿hard先修边回溯到基础概念
- 分层输出：基础概念铺垫 → 问题诊断 → 行动建议 → 风险提示 → 参考案例 → 核心金句
- 加载v1.5卡片（核心法则0截断、行动建议0空、案例类法则教训化）
- 行动建议匹配度阈值：只从匹配度>=5.0的卡片提取，避免低关联度卡片混入不相关内容
- 匹配质量提升：v1.5卡片核心法则包含关键词，匹配从"碰巧"变"合理"

用法：
  python3 card_caller_v04.py "我月薪8000欠了3万网贷怎么办"
  python3 card_caller_v04.py "手里有10万闲钱该怎么理财" --top 5
  python3 card_caller_v04.py --test  # 运行5个测试场景
  python3 card_caller_v04.py --interactive  # 交互模式

设计原则：
- 零API消耗，纯本地规则匹配
- 匹配可解释（每张卡片显示匹配分数和命中关键词）
- 输出结构化（基础铺垫→诊断→行动→风险→案例→引用）
- 不编造内容，所有回答来自卡片库
"""

import json
import re
import sys
import os
from collections import defaultdict

# ============================================================
# 配置
# ============================================================
CARDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'assets', 'deep_reasoning',
                          'cognition_cards_v1.5_repaired.json')

# 优先级权重
PRIORITY_WEIGHT = {'P0': 1.5, 'P1': 1.0, 'P2': 0.7}
# 类型权重
TYPE_WEIGHT = {'案例故事': 1.3, '方法论': 1.2, '理财原则': 1.0, '行业分析': 0.9}

# 问题关键词→匹配维度的映射表（核心30组，完整版含100+组）
KEYWORD_MAP = {
    # 债务类
    '网贷': ['网贷', '以贷养贷', '债务', '负债', '上岸', '借款'],
    '信用卡': ['信用卡', '以贷养贷', '债务', '负债', '最低还款'],
    '欠债': ['债务', '负债', '上岸', '担保', '以贷养贷'],
    '负债': ['债务', '负债', '上岸', '以贷养贷'],
    '以贷养贷': ['以贷养贷', '债务', '负债', '上岸'],
    '上岸': ['上岸', '债务', '负债', '以贷养贷'],
    '担保': ['担保', '债务'],
    '逾期': ['逾期', '债务', '负债', '上岸', '征信'],
    # 投资类
    '理财': ['理财', '资产配置', '指数基金', '定投', '复利', '储蓄'],
    '投资': ['投资', '资产配置', '指数基金', '股票', '基金', '复利'],
    '基金': ['基金', '指数基金', '定投', '资产配置'],
    '股票': ['股票', '个股', '集中投资', '止损', '交易'],
    '定投': ['定投', '指数基金', '复利', '资产配置'],
    '指数基金': ['指数基金', '定投', '资产配置', '低成本'],
    '闲钱': ['闲钱', '资产配置', '应急基金', '指数基金', '定投'],
    '保本': ['保本', '高风险', 'P2P', '年化', '亏损'],
    '年化': ['年化', '高收益', '高风险', '保本', '复利'],
    # 风险类
    '风险': ['风险', '安全边际', '止损', '分散', '能力圈'],
    '止损': ['止损', '交易', '风险控制', '资金管理'],
    '亏损': ['亏损', '止损', '风险', '安全边际'],
    '骗局': ['骗局', 'P2P', '高收益', '保本', '幸存者偏差'],
    '暴雷': ['暴雷', 'P2P', '高风险', '亏损', '保本'],
    '黑天鹅': ['黑天鹅', '尾部风险', '安全边际', '极端事件'],
    # 房产类
    '买房': ['买房', '房产', '自住房', '投资房', '租金回报率'],
    '租房': ['租房', '房产', '自住房', '租金回报率'],
    # 职业/人生
    '失业': ['失业', '职业', '技能', '收入', '应急金'],
    '副业': ['副业', '技能', '收入', '产品化'],
    '退休': ['退休', '养老', '复利', '储蓄', '资产配置'],
    # 心理/方法
    '复利': ['复利', '指数基金', '定投', '储蓄', '时间'],
    '储蓄': ['储蓄', '应急基金', '复利', '先存后花'],
}


class CardCallerV04:
    """认知卡片调用引擎 v0.4"""

    def __init__(self, cards_file=None):
        if cards_file:
            self.cards_file = cards_file
        else:
            self.cards_file = CARDS_FILE
        with open(self.cards_file, 'r', encoding='utf-8') as f:
            self.cards = json.load(f)
        self.card_map = {c['卡片ID']: c for c in self.cards}
        self.keyword_map = KEYWORD_MAP

    def match_card(self, question, card):
        """匹配单张卡片，返回(分数, 命中关键词列表)"""
        score = 0.0
        matched_keywords = []
        q_lower = question.lower()

        # 1. 标题/核心法则匹配（权重5.0）
        title_law = str(card.get('标题', '')) + ' ' + str(card.get('核心法则', ''))
        for kw in self.keyword_map:
            if kw.lower() in q_lower:
                for target in self.keyword_map[kw]:
                    if target in title_law:
                        score += 5.0
                        matched_keywords.append(f"{kw}→{target}(标题/法则)")
                        break

        # 2. 详细解释匹配（权重0.5）
        detail = str(card.get('详细解释', ''))
        for kw in self.keyword_map:
            if kw.lower() in q_lower:
                for target in self.keyword_map[kw]:
                    if target in detail:
                        score += 0.5
                        matched_keywords.append(f"{kw}→{target}(详细解释)")
                        break

        # 3. 关联周期匹配
        cycles = card.get('关联周期', [])
        if isinstance(cycles, list):
            for kw in self.keyword_map:
                if kw.lower() in q_lower:
                    for target in self.keyword_map[kw]:
                        if target in cycles:
                            score += 1.5
                            matched_keywords.append(f"{kw}→{target}(周期)")
                            break

        # 4. 问题中的词直接出现在卡片文本中
        for word in re.findall(r'[\u4e00-\u9fa5]{2,4}', question):
            if word in detail or word in str(card.get('核心法则', '')):
                score += 0.5
                matched_keywords.append(f"直接命中:{word}")

        # 5. 优先级和类型加权
        prio = card.get('优先级', 'P2')
        score *= PRIORITY_WEIGHT.get(prio, 0.7)
        ctype = card.get('类型', '理财原则')
        score *= TYPE_WEIGHT.get(ctype, 1.0)

        return round(score, 2), list(set(matched_keywords))

    def search(self, question, top_n=5):
        """搜索匹配的卡片"""
        results = []
        for card in self.cards:
            score, matched = self.match_card(question, card)
            if score > 0:
                results.append({
                    'card': card,
                    'score': score,
                    'matched': matched
                })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]

    def collect_prerequisites(self, card_id, max_depth=2, visited=None):
        """递归收集卡片的先修关系，只回溯hard先修"""
        if visited is None:
            visited = set()
        if card_id in visited or max_depth <= 0:
            return []
        visited.add(card_id)

        card = self.card_map.get(card_id)
        if not card:
            return []

        prereqs = card.get('先修关系', [])
        result = []
        for p in prereqs:
            if p['强度'] != 'hard':
                continue
            pid = p['先修卡片ID']
            if pid in visited:
                continue
            pcard = self.card_map.get(pid)
            if pcard:
                result.append({
                    'card': pcard,
                    'depth': max_depth,
                    'strength': 'hard',
                    'reason': p['理由']
                })
                result.extend(self.collect_prerequisites(pid, max_depth - 1, visited))
        return result

    def get_foundation_concepts(self, matches, max_depth=2):
        """从匹配到的top卡片中，收集所有需要先理解的基础概念"""
        all_prereqs = []
        seen_ids = set()

        for m in matches[:3]:
            card = m['card']
            prereqs = self.collect_prerequisites(card['卡片ID'], max_depth)
            for p in prereqs:
                pid = p['card']['卡片ID']
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_prereqs.append(p)

        all_prereqs.sort(key=lambda x: -x['depth'])
        return all_prereqs

    def generate_answer(self, question, top_n=5):
        """生成完整回答（基础概念铺垫+自适应回溯+匹配度阈值）"""
        matches = self.search(question, top_n)

        if not matches:
            return {
                'question': question,
                'foundation': [],
                'diagnosis': '未匹配到相关认知卡片。建议：①换个更具体的问法 ②将问题拆成更小的子问题 ③当前卡片库覆盖有限，后续会持续扩充',
                'actions': [],
                'risks': [],
                'cases': [],
                'quotes': [],
                'matched_cards': [],
                'confidence': '低'
            }

        foundation = self.get_foundation_concepts(matches, max_depth=2)

        all_actions = []
        all_risks = []
        all_cases = []
        all_quotes = []

        def is_valid_action(text):
            t = str(text).strip()
            if len(t) < 6: return False
            if t in ['待补充', 'None', '']: return False
            if '？' in t or '?' in t: return False
            if t.startswith('——') and len(t) < 15: return False
            if t.startswith('的') or t.startswith('了'): return False
            if re.match(r'^[\d\.\%\-\s]+$', t): return False
            return True

        # v0.4：行动建议只从匹配度>=5.0的卡片提取
        ACTION_THRESHOLD = 5.0
        for m in matches[:3]:
            if m['score'] < ACTION_THRESHOLD:
                continue
            card = m['card']
            action = card.get('行动建议', {})
            if isinstance(action, dict):
                dos = action.get('做什么', [])
                if isinstance(dos, list):
                    for d in dos:
                        if is_valid_action(d):
                            all_actions.append(str(d).strip())
                donts = action.get('不做什么', [])
                if isinstance(donts, list):
                    for d in donts:
                        if is_valid_action(d):
                            all_risks.append(str(d).strip())

            if card.get('类型') == '案例故事':
                all_cases.append({
                    'id': card['卡片ID'],
                    'title': card.get('标题', ''),
                    'summary': str(card.get('详细解释', ''))[:200]
                })

            law = str(card.get('核心法则', ''))
            if len(law) > 5 and law not in all_quotes:
                all_quotes.append(law)

        all_actions = list(dict.fromkeys(all_actions))[:8]
        all_risks = list(dict.fromkeys(all_risks))[:5]
        all_quotes = list(dict.fromkeys(all_quotes))[:3]

        top_card = matches[0]['card']
        diagnosis = f"根据你的问题，最相关的认知卡片是「{top_card['卡片ID']}」（{top_card.get('类型','')}）。"
        diagnosis += f"核心法则：{top_card.get('核心法则','')[:100]}"

        max_score = matches[0]['score']
        if max_score >= 8: confidence = '高'
        elif max_score >= 4: confidence = '中'
        else: confidence = '低'

        return {
            'question': question,
            'foundation': foundation,
            'diagnosis': diagnosis,
            'actions': all_actions,
            'risks': all_risks,
            'cases': all_cases,
            'quotes': all_quotes,
            'matched_cards': [
                {'id': m['card']['卡片ID'], 'type': m['card'].get('类型', ''),
                 'priority': m['card'].get('优先级', ''), 'score': m['score'],
                 'matched': m['matched'][:3], 'law': str(m['card'].get('核心法则', ''))[:80]}
                for m in matches
            ],
            'confidence': confidence
        }

    def format_answer(self, answer):
        lines = []
        lines.append("=" * 60)
        lines.append(f"问题：{answer['question']}")
        lines.append(f"匹配置信度：{answer['confidence']}")
        lines.append("=" * 60)

        if answer['foundation']:
            lines.append("\n【先理解这些基础概念】")
            lines.append("（要理解下面的建议，需要先掌握这些基础）")
            for i, f in enumerate(answer['foundation'], 1):
                card = f['card']
                law = str(card.get('核心法则', ''))[:60]
                lines.append(f"  {i}. [{card['卡片ID']}] {card.get('标题','')[:25]}")
                lines.append(f"     法则：{law}")
                lines.append(f"     为什么需要先懂：{f['reason']}")

        lines.append("\n【问题诊断】")
        lines.append(answer['diagnosis'])

        if answer['actions']:
            lines.append("\n【行动建议】")
            for i, a in enumerate(answer['actions'], 1):
                lines.append(f"  {i}. {a}")

        if answer['risks']:
            lines.append("\n【风险提示】")
            for r in answer['risks']:
                lines.append(f"  ✗ {r}")

        if answer['cases']:
            lines.append("\n【参考案例】")
            for c in answer['cases'][:2]:
                lines.append(f"  ▸ {c['id']}：{c['summary'][:120]}...")

        if answer['quotes']:
            lines.append("\n【核心金句】")
            for q in answer['quotes']:
                lines.append(f"  \"{q[:80]}\"")

        lines.append("\n【引用卡片】")
        for c in answer['matched_cards']:
            lines.append(f"  {c['id']}({c['type']}/{c['priority']}) 匹配度:{c['score']} | {c['law'][:50]}")

        return '\n'.join(lines)

    def ask(self, question, top_n=5):
        answer = self.generate_answer(question, top_n)
        return self.format_answer(answer)

    def run_tests(self):
        test_cases = [
            "月薪6000欠了5万信用卡和网贷怎么办",
            "手里有10万闲钱该怎么理财",
            "有人说年化15%保本能投吗",
            "现在买房还是租房划算",
            "30岁了还没开始理财来得及吗",
        ]
        for q in test_cases:
            print(self.ask(q))
            print("\n" + "~" * 60 + "\n")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 card_caller_v04.py \"问题\" [--top N]")
        print("      python3 card_caller_v04.py --test")
        print("      python3 card_caller_v04.py --interactive")
        return

    caller = CardCallerV04()

    if sys.argv[1] == '--test':
        caller.run_tests()
    elif sys.argv[1] == '--interactive':
        print("认知卡片调用引擎 v0.4（输入exit退出）")
        while True:
            try:
                q = input("\n你的问题: ").strip()
                if q.lower() in ['exit', 'quit', '退出']:
                    break
                if q:
                    print(caller.ask(q))
            except (EOFError, KeyboardInterrupt):
                break
    else:
        question = sys.argv[1]
        top_n = 5
        if '--top' in sys.argv:
            idx = sys.argv.index('--top')
            if idx + 1 < len(sys.argv):
                top_n = int(sys.argv[idx + 1])
        print(caller.ask(question, top_n))


if __name__ == '__main__':
    main()
