#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知卡片调用引擎 v0.2
知盈认知资产库的核心组件：输入真实问题→匹配相关认知卡片→组合成完整回答

用法：
  python3 card_caller.py "我月薪8000欠了3万网贷怎么办"
  python3 card_caller.py "手里有10万闲钱该怎么理财" --top 5
  python3 card_caller.py --test  # 运行测试场景
  python3 card_caller.py --interactive  # 交互模式

设计原则：
- 零API消耗，纯本地规则匹配
- 匹配可解释（每张卡片显示匹配分数和命中关键词）
- 输出结构化（诊断→行动→风险→案例→引用）
- 不编造内容，所有回答来自卡片库
"""

import json
import re
import sys
import os

# ============================================================
# 配置
# ============================================================
CARDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'assets', 'deep_reasoning',
                          'cognition_cards_v1.2_content_filled.json')

# 问题关键词→匹配维度的映射表
KEYWORD_MAP = {
    # 债务类
    '网贷': ['网贷', '以贷养贷', '债务', '负债', '上岸', '借款', '贷款'],
    '信用卡': ['信用卡', '以贷养贷', '债务', '负债', '最低还款'],
    '欠债': ['债务', '负债', '上岸', '担保', '以贷养贷'],
    '负债': ['债务', '负债', '上岸', '以贷养贷'],
    '还钱': ['债务', '负债', '上岸', '雪崩法', '协商'],
    '担保': ['担保', '债务'],
    '以贷养贷': ['以贷养贷', '债务', '负债', '上岸'],
    '上岸': ['上岸', '债务', '负债', '以贷养贷'],
    '协商': ['协商', '债务', '负债', '上岸'],
    '逾期': ['逾期', '债务', '负债', '上岸', '征信'],
    '征信': ['征信', '逾期', '债务'],
    '房贷': ['房贷', '房产', '债务', '租金回报率'],
    '车贷': ['车贷', '债务', '负债'],
    # 投资类
    '理财': ['理财', '资产配置', '指数基金', '定投', '复利', '储蓄'],
    '投资': ['投资', '资产配置', '指数基金', '股票', '基金', '复利'],
    '基金': ['基金', '指数基金', '定投', '资产配置'],
    '股票': ['股票', '个股', '集中投资', '止损', '止盈', '交易'],
    '炒股': ['股票', '交易', '止损', '止盈', '技术分析'],
    '定投': ['定投', '指数基金', '复利', '资产配置'],
    '指数基金': ['指数基金', '定投', '资产配置', '低成本'],
    '闲钱': ['闲钱', '资产配置', '应急基金', '指数基金', '定投'],
    '存钱': ['储蓄', '应急基金', '复利', '先存后花'],
    '储蓄': ['储蓄', '应急基金', '复利', '先存后花'],
    '保本': ['保本', '高风险', 'P2P', '年化', '亏损'],
    '高收益': ['高收益', '高风险', '年化', '保本', 'P2P'],
    '年化': ['年化', '高收益', '高风险', '保本', '复利'],
    '分红': ['股息', '分红', '高股息', '现金流'],
    '股息': ['股息', '分红', '高股息', '现金流'],
    'REITs': ['REITs', '不动产', '租金', '分红'],
    '黄金': ['黄金', '避险', '美元', '通胀'],
    '比特币': ['比特币', '加密货币', '高风险', '投机'],
    '加密货币': ['加密货币', '比特币', '高风险', '投机'],
    # 风险类
    '风险': ['风险', '安全边际', '止损', '分散', '能力圈'],
    '止损': ['止损', '交易', '风险控制', '资金管理'],
    '止盈': ['止盈', '交易', '再平衡', '资产配置'],
    '亏损': ['亏损', '止损', '风险', '安全边际', '损失厌恶'],
    '亏钱': ['亏损', '止损', '风险', '安全边际'],
    '被骗': ['骗局', 'P2P', '高收益', '保本', '内幕交易'],
    '骗局': ['骗局', 'P2P', '高收益', '保本', '幸存者偏差'],
    '暴雷': ['暴雷', 'P2P', '高风险', '亏损', '保本'],
    'P2P': ['P2P', '暴雷', '高收益', '保本', '亏损'],
    '杠杆': ['杠杆', '风险', '爆仓', '交易'],
    '爆仓': ['爆仓', '杠杆', '止损', '风险'],
    '黑天鹅': ['黑天鹅', '杠铃策略', '风险', '应急基金'],
    '危机': ['危机', '黑天鹅', '杠铃策略', '应急基金', '抄底'],
    '抄底': ['抄底', '危机', '黑天鹅', '应急基金', '现金'],
    # 房产类
    '买房': ['房产', '自住房', '投资房', '租金回报率', '房贷'],
    '房子': ['房产', '自住房', '投资房', '租金回报率'],
    '房价': ['房产', '房价', '租金回报率', '政策'],
    '租房': ['租房', '自住房', '房产', '消费'],
    '租金': ['租金', '租金回报率', '房产', 'REITs'],
    # 职业/收入类
    '失业': ['失业', '应急基金', '职业发展', '收入'],
    '工资': ['工资', '收入', '先存后花', '储蓄'],
    '收入': ['收入', '工资', '副业', '职业发展', '现金流'],
    '副业': ['副业', '收入', '职业发展', '短视频'],
    '转行': ['转行', '职业发展', '收入', '技能'],
    '短视频': ['短视频', '副业', '收入', '内容创作'],
    '自由职业': ['自由职业', '收入', '副业', '职业发展'],
    # 人生阶段类
    '退休': ['退休', '养老', '长期储蓄', '复利', '401k'],
    '养老': ['养老', '退休', '长期储蓄', '复利', '高股息'],
    '30岁': ['30岁', '种一棵树', '开始', '复利', '来得及'],
    '40岁': ['40岁', '开始', '资产配置', '退休规划', '种一棵树'],
    '来得及': ['种一棵树', '开始', '30岁', '40岁', '现在'],
    '结婚': ['结婚', '财务安全', '保险', '资产配置'],
    '孩子': ['孩子', '教育金', '保险', '财务安全'],
    '保险': ['保险', '先保险后投资', '风险转移', '财务安全'],
    # 宏观/周期类
    '通胀': ['通胀', '复利', '现金贬值', '黄金', '资产配置'],
    '贬值': ['贬值', '通胀', '汇率', '美元', '现金'],
    '汇率': ['汇率', '美元', '人民币', '海外资产'],
    '美元': ['美元', '汇率', '人民币', '海外资产', '黄金'],
    '人民币': ['人民币', '汇率', '美元', '贬值'],
    '降息': ['降息', '政策', '美元', '房贷', '债券'],
    '加息': ['加息', '美元', '政策', '汇率'],
    '政策': ['政策', '教培', '反垄断', '三道红线', '分散'],
    '经济': ['经济', '周期', '产业', '政策', '债务'],
    '周期': ['周期', '产业', '债务', '政策', '康波'],
    '衰退': ['衰退', '危机', '黑天鹅', '应急基金', '现金'],
    '泡沫': ['泡沫', '羊群效应', '崩盘', '止损', '估值'],
    # 心理/行为类
    '焦虑': ['焦虑', '心理账户', '损失厌恶', '应急基金', '财务安全'],
    '恐惧': ['恐惧', '损失厌恶', '羊群效应', '止损'],
    '贪婪': ['贪婪', '羊群效应', '高收益', '止损', '止盈'],
    '心态': ['心态', '损失厌恶', '心理账户', '长期持有', '交易心理'],
    '坚持': ['坚持', '定投', '复利', '长期持有', '耐心'],
    '耐心': ['耐心', '定投', '复利', '长期持有', '高频交易'],
    # 方法论类
    '资产配置': ['资产配置', '股债比例', '指数基金', '再平衡'],
    '分散': ['分散', '资产配置', '集中投资', '不要把鸡蛋放一个篮子'],
    '集中': ['集中投资', '费雪', '能力圈', '5-10只'],
    '能力圈': ['能力圈', '只投你懂的', '集中投资', '费雪'],
    '复利': ['复利', '定投', '指数基金', '长期持有', '巴比伦'],
    '安全边际': ['安全边际', '估值', '风险', '止损'],
    '长期': ['长期', '复利', '定投', '指数基金', '耐心'],
    '短线': ['短线', '交易', '高频交易', '止损', '技术分析'],
    '交易': ['交易', '止损', '止盈', '资金管理', '技术分析'],
    '估值': ['估值', '安全边际', 'PE', '止盈', '好价格'],
}

PRIORITY_WEIGHT = {'P0': 1.5, 'P1': 1.0, 'P2': 0.7}
TYPE_WEIGHT = {'案例故事': 1.3, '方法论': 1.2, '理财原则': 1.0, '行业分析': 0.9}


class CardCaller:
    def __init__(self, cards_file=None):
        self.cards_file = cards_file or CARDS_FILE
        self.cards = self._load_cards()
        self.keyword_map = KEYWORD_MAP

    def _load_cards(self):
        with open(self.cards_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def match_card(self, question, card):
        score = 0.0
        matched = []
        q = question.lower()
        # 1. 标题/核心法则匹配（权重最高5.0）
        for field in ['标题', '核心法则']:
            text = str(card.get(field, ''))
            for kw in self.keyword_map:
                if kw.lower() in q:
                    for target in self.keyword_map[kw]:
                        if target in text:
                            score += 5.0
                            matched.append(f"{kw}→{target}({field})")
                            break
        # 2. 详细解释匹配（权重0.5）
        detail = str(card.get('详细解释', ''))
        for kw in self.keyword_map:
            if kw.lower() in q:
                for target in self.keyword_map[kw]:
                    if target in detail:
                        score += 0.5
                        matched.append(f"{kw}→{target}(详细解释)")
                        break
        # 3. 关联周期匹配（权重1.5）
        cycles = card.get('关联周期', [])
        if isinstance(cycles, list):
            for kw in self.keyword_map:
                if kw.lower() in q:
                    for target in self.keyword_map[kw]:
                        if target in cycles:
                            score += 1.5
                            matched.append(f"{kw}→{target}(周期)")
                            break
        # 4. 直接命中
        for word in re.findall(r'[\u4e00-\u9fa5]{2,4}', question):
            if word in detail or word in str(card.get('核心法则', '')):
                score += 0.5
                matched.append(f"直接命中:{word}")
        # 5. 加权
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

    def generate_answer(self, question, top_n=5):
        matches = self.search(question, top_n)
        if not matches:
            return {'question': question, 'diagnosis': '未匹配到相关认知卡片',
                    'actions': [], 'risks': [], 'cases': [], 'quotes': [],
                    'matched_cards': [], 'confidence': '低'}

        def is_valid(text):
            t = str(text).strip()
            if len(t) < 6 or t in ['待补充', 'None', '']: return False
            if '？' in t or '?' in t: return False
            if t.startswith('——') and len(t) < 15: return False
            if t.startswith('的') or t.startswith('了'): return False
            if re.match(r'^[\d\.\%\-\s]+$', t): return False
            return True

        actions, risks, cases, quotes = [], [], [], []
        for m in matches[:3]:
            card = m['card']
            action = card.get('行动建议', {})
            if isinstance(action, dict):
                for d in action.get('做什么', []):
                    if is_valid(d): actions.append(str(d).strip())
                for d in action.get('不做什么', []):
                    if is_valid(d): risks.append(str(d).strip())
            if card.get('类型') == '案例故事':
                cases.append({'id': card['卡片ID'], 'summary': str(card.get('详细解释', ''))[:200]})
            law = str(card.get('核心法则', ''))
            if len(law) > 5 and law not in quotes: quotes.append(law)

        actions = list(dict.fromkeys(actions))[:8]
        risks = list(dict.fromkeys(risks))[:5]
        quotes = list(dict.fromkeys(quotes))[:3]
        top = matches[0]['card']
        diagnosis = f"最相关卡片「{top['卡片ID']}」（{top.get('类型','')}）。{top.get('核心法则','')[:100]}"
        confidence = '高' if matches[0]['score'] >= 8 else ('中' if matches[0]['score'] >= 4 else '低')
        return {
            'question': question, 'diagnosis': diagnosis, 'actions': actions,
            'risks': risks, 'cases': cases, 'quotes': quotes,
            'matched_cards': [{'id': m['card']['卡片ID'], 'type': m['card'].get('类型',''),
                'priority': m['card'].get('优先级',''), 'score': m['score'],
                'law': str(m['card'].get('核心法则',''))[:80]} for m in matches],
            'confidence': confidence
        }

    def format_answer(self, a):
        lines = ['=' * 60, f"问题：{a['question']}", f"匹配置信度：{a['confidence']}", '=' * 60]
        lines.append('\n【问题诊断】'); lines.append(a['diagnosis'])
        if a['actions']:
            lines.append('\n【行动建议】')
            for i, x in enumerate(a['actions'], 1): lines.append(f"  {i}. {x}")
        if a['risks']:
            lines.append('\n【风险提示】')
            for x in a['risks']: lines.append(f"  ✗ {x}")
        if a['cases']:
            lines.append('\n【参考案例】')
            for c in a['cases'][:2]: lines.append(f"  ▸ {c['id']}：{c['summary'][:120]}...")
        if a['quotes']:
            lines.append('\n【核心金句】')
            for q in a['quotes']: lines.append(f'  "{q[:80]}"')
        lines.append('\n【引用卡片】')
        for c in a['matched_cards']:
            lines.append(f"  {c['id']}({c['type']}/{c['priority']}) 匹配度:{c['score']} | {c['law'][:50]}")
        lines.append('\n' + '=' * 60)
        lines.append('知盈认知卡片调用引擎 v0.2 | 所有建议来自认知卡片库，不构成投资建议')
        lines.append('=' * 60)
        return '\n'.join(lines)


TEST_SCENARIOS = [
    '我月薪6000欠了5万信用卡和网贷怎么办',
    '手里有10万闲钱该怎么理财',
    '年化15%保本的理财产品能投吗',
    '现在适合买房还是租房',
    '30岁了还没开始理财来得及吗',
]

def run_tests():
    caller = CardCaller()
    print('知盈认知卡片调用引擎 v0.2 — 测试运行\n')
    for i, s in enumerate(TEST_SCENARIOS, 1):
        print(f"\n{'#'*60}\n测试场景 {i}/{len(TEST_SCENARIOS)}\n{'#'*60}")
        print(caller.format_answer(caller.generate_answer(s, top_n=5)))

def main():
    if len(sys.argv) < 2:
        print('用法：python3 card_caller.py "问题" | --test | --interactive')
        return
    arg = sys.argv[1]
    if arg == '--test': run_tests(); return
    if arg == '--interactive':
        caller = CardCaller()
        print('交互模式（exit退出）')
        while True:
            try:
                q = input('问题：').strip()
                if q.lower() in ['exit', 'quit', '退出']: break
                if q: print(caller.format_answer(caller.generate_answer(q)))
            except (EOFError, KeyboardInterrupt): break
        return
    top_n = 5
    if '--top' in sys.argv:
        idx = sys.argv.index('--top')
        if idx + 1 < len(sys.argv): top_n = int(sys.argv[idx + 1])
    caller = CardCaller()
    print(caller.format_answer(caller.generate_answer(arg, top_n=top_n)))

if __name__ == '__main__':
    main()
