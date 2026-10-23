#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知卡片调用引擎 v0.5（精简版）
知盈认知资产库核心组件：输入问题→匹配卡片→先修边回溯基础概念→语义过滤→分层输出

v0.5 新增（第417次唤醒）：
- 加载v1.6卡片（24张标题修复+15张行动建议修复，标题0异常）
- 语义关联度二次过滤：行动建议必须包含问题核心词或与Top1同周期
- 行动建议完整率大幅提升（场景2从1条→7条）

v0.4 新增：加载v1.5卡片+行动建议匹配度阈值5.0
v0.3 新增：自适应回溯（hard先修边递归，max_depth=2）+分层输出

用法：python3 card_caller_v05.py "问题" | --test | --interactive
"""
import json, re, sys, os

CARDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'assets', 'deep_reasoning', 'cognition_cards_v1.6_repaired.json')
PRIORITY_WEIGHT = {'P0': 1.5, 'P1': 1.0, 'P2': 0.7}
TYPE_WEIGHT = {'案例故事': 1.3, '方法论': 1.2, '理财原则': 1.0, '行业分析': 0.9}

KEYWORD_MAP = {
    '网贷': ['网贷', '以贷养贷', '债务', '负债', '上岸', '借款'],
    '信用卡': ['信用卡', '以贷养贷', '债务', '负债', '最低还款'],
    '欠债': ['债务', '负债', '上岸', '担保', '以贷养贷'],
    '负债': ['债务', '负债', '上岸', '以贷养贷'],
    '以贷养贷': ['以贷养贷', '债务', '负债', '上岸'],
    '上岸': ['上岸', '债务', '负债', '以贷养贷'],
    '担保': ['担保', '债务'],
    '逾期': ['逾期', '债务', '负债', '上岸', '征信'],
    '理财': ['理财', '资产配置', '指数基金', '定投', '复利', '储蓄'],
    '投资': ['投资', '资产配置', '指数基金', '股票', '基金', '复利'],
    '基金': ['基金', '指数基金', '定投', '资产配置'],
    '股票': ['股票', '个股', '集中投资', '止损', '交易'],
    '定投': ['定投', '指数基金', '复利', '资产配置'],
    '指数基金': ['指数基金', '定投', '资产配置', '低成本'],
    '闲钱': ['闲钱', '资产配置', '应急基金', '指数基金', '定投'],
    '保本': ['保本', '高风险', 'P2P', '年化', '亏损'],
    '年化': ['年化', '高收益', '高风险', '保本', '复利'],
    '风险': ['风险', '安全边际', '止损', '分散', '能力圈'],
    '止损': ['止损', '交易', '风险控制', '资金管理'],
    '亏损': ['亏损', '止损', '风险', '安全边际'],
    '骗局': ['骗局', 'P2P', '高收益', '保本', '幸存者偏差'],
    '暴雷': ['暴雷', 'P2P', '高风险', '亏损', '保本'],
    '黑天鹅': ['黑天鹅', '尾部风险', '安全边际', '极端事件'],
    '买房': ['买房', '房产', '自住房', '投资房', '租金回报率'],
    '租房': ['租房', '房产', '自住房', '租金回报率'],
    '失业': ['失业', '职业', '技能', '收入', '应急金'],
    '副业': ['副业', '技能', '收入', '产品化'],
    '退休': ['退休', '养老', '复利', '储蓄', '资产配置'],
    '复利': ['复利', '指数基金', '定投', '储蓄', '时间'],
    '储蓄': ['储蓄', '应急基金', '复利', '先存后花'],
}

class CardCallerV05:
    def __init__(self, cards_file=None):
        self.cards_file = cards_file or CARDS_FILE
        with open(self.cards_file, 'r', encoding='utf-8') as f:
            self.cards = json.load(f)
        self.card_map = {c['卡片ID']: c for c in self.cards}

    def match_card(self, question, card):
        score = 0.0
        matched = []
        q = question.lower()
        title_law = str(card.get('标题', '')) + ' ' + str(card.get('核心法则', ''))
        detail = str(card.get('详细解释', ''))
        cycles = card.get('关联周期', [])
        for kw in KEYWORD_MAP:
            if kw.lower() in q:
                for target in KEYWORD_MAP[kw]:
                    if target in title_law:
                        score += 5.0; matched.append(f"{kw}→{target}(法则)"); break
                    if target in detail:
                        score += 0.5; matched.append(f"{kw}→{target}(解释)"); break
                    if isinstance(cycles, list) and target in cycles:
                        score += 1.5; matched.append(f"{kw}→{target}(周期)"); break
        for word in re.findall(r'[\u4e00-\u9fa5]{2,4}', question):
            if word in detail or word in str(card.get('核心法则', '')):
                score += 0.5; matched.append(f"直接:{word}")
        score *= PRIORITY_WEIGHT.get(card.get('优先级', 'P2'), 0.7)
        score *= TYPE_WEIGHT.get(card.get('类型', '理财原则'), 1.0)
        return round(score, 2), list(set(matched))

    def search(self, question, top_n=5):
        results = []
        for card in self.cards:
            score, matched = self.match_card(question, card)
            if score > 0:
                results.append({'card': card, 'score': score, 'matched': matched})
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]

    def collect_prerequisites(self, card_id, max_depth=2, visited=None):
        if visited is None: visited = set()
        if card_id in visited or max_depth <= 0: return []
        visited.add(card_id)
        card = self.card_map.get(card_id)
        if not card: return []
        result = []
        for p in card.get('先修关系', []):
            if p['强度'] != 'hard': continue
            pid = p['先修卡片ID']
            if pid in visited: continue
            pcard = self.card_map.get(pid)
            if pcard:
                result.append({'card': pcard, 'depth': max_depth, 'reason': p['理由']})
                result.extend(self.collect_prerequisites(pid, max_depth - 1, visited))
        return result

    def get_foundation_concepts(self, matches, max_depth=2):
        all_prereqs = []; seen = set()
        for m in matches[:3]:
            for p in self.collect_prerequisites(m['card']['卡片ID'], max_depth):
                pid = p['card']['卡片ID']
                if pid not in seen:
                    seen.add(pid); all_prereqs.append(p)
        all_prereqs.sort(key=lambda x: -x['depth'])
        return all_prereqs

    def generate_answer(self, question, top_n=5):
        matches = self.search(question, top_n)
        if not matches:
            return {'question': question, 'foundation': [], 'diagnosis': '未匹配到相关卡片',
                    'actions': [], 'risks': [], 'cases': [], 'quotes': [], 'matched_cards': [], 'confidence': '低'}
        foundation = self.get_foundation_concepts(matches, 2)
        all_actions, all_risks, all_cases, all_quotes = [], [], [], []

        def is_valid(text):
            t = str(text).strip()
            return len(t) >= 6 and t not in ['待补充', 'None', ''] and '？' not in t and '?' not in t \
                and not (t.startswith('——') and len(t) < 15) and not t.startswith('的') \
                and not re.match(r'^[\d\.\%\-\s]+$', t)

        ACTION_THRESHOLD = 5.0
        for m in matches[:3]:
            if m['score'] < ACTION_THRESHOLD: continue
            card = m['card']
            action = card.get('行动建议', {})
            if isinstance(action, dict):
                for d in action.get('做什么', []) or []:
                    if is_valid(d): all_actions.append(str(d).strip())
                for d in action.get('不做什么', []) or []:
                    if is_valid(d): all_risks.append(str(d).strip())
            if card.get('类型') == '案例故事':
                all_cases.append({'id': card['卡片ID'], 'summary': str(card.get('详细解释', ''))[:200]})
            law = str(card.get('核心法则', ''))
            if len(law) > 5 and law not in all_quotes: all_quotes.append(law)

        # v0.5：语义关联度二次过滤
        stop_words = {'什么','怎么','怎么办','为什么','如何','可以','应该','现在','这个','那个','一个','没有','不是','还是','就是','觉得','知道','时候','自己','大家','我们','你们','他们'}
        core_words = [w for w in re.findall(r'[\u4e00-\u9fa5]{2,4}', question) if w not in stop_words]
        top1_cycles = set(matches[0]['card'].get('关联周期', []) or [])
        top1_law_words = [w for w in re.findall(r'[\u4e00-\u9fa5]{2,4}', str(matches[0]['card'].get('核心法则', ''))) if len(w) >= 3][:5]

        def is_relevant(act, src_card):
            text = str(act)
            if any(cw in text for cw in core_words): return True
            if src_card and set(src_card.get('关联周期', []) or []) & top1_cycles: return True
            if any(lw in text for lw in top1_law_words): return True
            return False

        filtered = []
        for act in all_actions:
            src = None
            for m in matches[:3]:
                c = m['card']
                a = c.get('行动建议', {})
                if isinstance(a, dict) and act in [str(d).strip() for d in (a.get('做什么', []) or [])]:
                    src = c; break
            if src and is_relevant(act, src): filtered.append(act)
            elif not src: filtered.append(act)
        if len(filtered) < 2:
            filtered = [a for a in all_actions if any(cw in str(a) for cw in core_words)] or all_actions[:4]

        all_actions = list(dict.fromkeys(filtered))[:8]
        all_risks = list(dict.fromkeys(all_risks))[:5]
        all_quotes = list(dict.fromkeys(all_quotes))[:3]

        top_card = matches[0]['card']
        diagnosis = f"最相关卡片「{top_card['卡片ID']}」（{top_card.get('类型','')}）。法则：{top_card.get('核心法则','')[:100]}"
        confidence = '高' if matches[0]['score'] >= 8 else ('中' if matches[0]['score'] >= 4 else '低')
        return {'question': question, 'foundation': foundation, 'diagnosis': diagnosis,
                'actions': all_actions, 'risks': all_risks, 'cases': all_cases, 'quotes': all_quotes,
                'matched_cards': [{'id': m['card']['卡片ID'], 'type': m['card'].get('类型',''),
                    'priority': m['card'].get('优先级',''), 'score': m['score'],
                    'law': str(m['card'].get('核心法则',''))[:80]} for m in matches],
                'confidence': confidence}

    def format_answer(self, ans):
        lines = ["=" * 60, f"问题：{ans['question']}", f"置信度：{ans['confidence']}", "=" * 60]
        if ans['foundation']:
            lines.append("\n【先理解这些基础概念】")
            for i, f in enumerate(ans['foundation'], 1):
                c = f['card']
                lines.append(f"  {i}. [{c['卡片ID']}] {c.get('标题','')[:25]}")
                lines.append(f"     法则：{str(c.get('核心法则',''))[:60]}")
                lines.append(f"     为什么先懂：{f['reason']}")
        lines.append("\n【问题诊断】" + ans['diagnosis'])
        if ans['actions']:
            lines.append("\n【行动建议】")
            for i, a in enumerate(ans['actions'], 1): lines.append(f"  {i}. {a}")
        if ans['risks']:
            lines.append("\n【风险提示】")
            for r in ans['risks']: lines.append(f"  ✗ {r}")
        if ans['cases']:
            lines.append("\n【参考案例】")
            for c in ans['cases'][:2]: lines.append(f"  ▸ {c['id']}：{c['summary'][:120]}...")
        if ans['quotes']:
            lines.append("\n【核心金句】")
            for q in ans['quotes']: lines.append(f'  "{q[:80]}"')
        lines.append("\n【引用卡片】")
        for c in ans['matched_cards']: lines.append(f"  {c['id']}({c['type']}/{c['priority']}) 匹配度:{c['score']} | {c['law'][:50]}")
        return '\n'.join(lines)

    def ask(self, question, top_n=5): return self.format_answer(self.generate_answer(question, top_n))

    def run_tests(self):
        for q in ["月薪6000欠了5万信用卡和网贷怎么办", "手里有10万闲钱该怎么理财",
                  "有人说年化15%保本能投吗", "现在买房还是租房划算", "30岁了还没开始理财来得及吗"]:
            print(self.ask(q)); print("\n" + "~" * 60 + "\n")

def main():
    if len(sys.argv) < 2:
        print('用法: python3 card_caller_v05.py "问题" | --test | --interactive'); return
    caller = CardCallerV05()
    if sys.argv[1] == '--test': caller.run_tests()
    elif sys.argv[1] == '--interactive':
        print("认知卡片调用引擎 v0.5（输入exit退出）")
        while True:
            try:
                q = input("\n你的问题: ").strip()
                if q.lower() in ['exit','quit','退出']: break
                if q: print(caller.ask(q))
            except (EOFError, KeyboardInterrupt): break
    else:
        print(caller.ask(sys.argv[1]))

if __name__ == '__main__': main()
