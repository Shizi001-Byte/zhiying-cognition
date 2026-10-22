#!/usr/bin/env python3
"""
知盈金融翻译官 v0.3.1 - 系统1判断层
先判断再翻译：用规则+关键词+正则快速判断文本类型、涉及周期、利好利空倾向
不调用大模型，快、结构化、不幻觉

v0.3.1改进：
- 加入正则概念匹配（"存款准备金率下调"→降准概念）
- 否定词改用正则匹配（"取消.*限购"→利好）
- 加入文本类型→默认涉及周期映射
- 加强利好利空评分规则
"""
import re
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple

# ============================================================
# 正则概念匹配（解决"存款准备金率下调"没匹配"降准"的问题）
# ============================================================
REGEX_CONCEPTS = [
    # (正则模式, 概念标签, 涉及周期列表, 利好利空分数)
    # 分数参考API评分规则（P4_352）：短期1-3个月对低收入工薪群体的直接影响
    (r"存款准备金.*?(下调|降低|降准)", "降准", ["债务周期", "政策周期"], 2.0),
    (r"降准", "降准", ["债务周期", "政策周期"], 2.0),
    (r"(降息|利率.*?(下调|降低|下降))", "降息", ["债务周期", "政策周期"], 2.5),
    (r"加息|利率.*?(上调|提高|上升)", "加息", ["债务周期", "政策周期"], -2.5),
    (r"MLF.*?(下调|降低|降息)|中期借贷便利.*?(下调|降低)", "MLF降息", ["债务周期", "政策周期"], 2.0),
    (r"LPR.*?(下调|降低)|贷款市场报价利率.*?(下调|降低)", "LPR下调", ["债务周期", "政策周期"], 2.5),
    (r"逆回购.*?(放量|增加|扩大)|公开市场.*?(投放|净投放)", "流动性投放", ["债务周期", "政策周期"], 1.0),
    (r"逆回购.*?(回笼|减少|收紧)|公开市场.*?(回笼|净回笼)", "流动性回笼", ["债务周期", "政策周期"], -1.0),
    (r"取消.*?(限购|限贷)|全面.*?放开.*?(限购|限贷)", "取消限购限贷", ["政策周期", "产业周期"], 0.5),
    (r"放松.*?(限购|限贷)|放宽.*?(限购|限贷)", "放松限购限贷", ["政策周期", "产业周期"], 0.5),
    (r"首付.*?(降低|下调|下降)|首套房.*?首付", "降首付", ["债务周期", "政策周期"], 1.0),
    (r"房贷利率.*?(下调|降低|下降)", "房贷利率下调", ["债务周期", "政策周期"], 2.5),
    (r"减税|降税|减免.*?税", "减税", ["政策周期"], 3.0),
    (r"专项债|特别国债", "财政发力", ["政策周期"], 1.0),
    (r"CPI.*?(上涨|上升|走高)|通胀", "通胀", ["政策周期"], -1.5),
    (r"CPI.*?(下降|走低|回落)|通缩", "物价回落", ["政策周期", "产业周期"], 0.5),
    (r"PMI.*?(高于|大于|超过).*?50|制造业.*?扩张", "制造业扩张", ["产业周期"], 2.0),
    (r"PMI.*?(低于|小于|不足).*?50|制造业.*?收缩", "制造业收缩", ["产业周期"], -2.0),
    (r"失业率.*?(上升|上涨|提高|升至|走高)|就业.*?压力", "就业压力", ["人口周期", "产业周期"], -4.0),
    (r"房价.*?(下跌|下降|走低)|楼市.*?降温", "房价下跌", ["债务周期", "产业周期"], -1.0),
    (r"房价.*?(上涨|上升|走高)|楼市.*?回暖", "房价上涨", ["产业周期"], -2.0),
    (r"美联储.*?加息|联邦基金利率.*?(上调|提高)", "美联储加息", ["美元周期"], -1.0),
    (r"美联储.*?降息|联邦基金利率.*?(下调|降低)", "美联储降息", ["美元周期"], 1.0),
    (r"人民币.*?(贬值|走弱)|汇率.*?(承压|下跌)", "人民币贬值", ["美元周期"], 0.5),
    (r"人民币.*?(升值|走强)|汇率.*?(回升|上涨)", "人民币升值", ["美元周期"], -0.5),
    (r"监管.*?(处罚|罚款|严查|整治)|立案调查", "监管处罚", ["政策周期"], 1.0),
    (r"产业.*?补贴|补贴.*?政策|政府补贴", "产业补贴", ["产业周期", "政策周期"], 1.0),
]

# ============================================================
# 文本类型→默认涉及周期映射（解决"降准没触发政策周期"的问题）
# ============================================================
TYPE_DEFAULT_CYCLES = {
    "货币政策": ["债务周期", "政策周期"],
    "财政政策": ["政策周期"],
    "经济数据": ["产业周期"],
    "监管政策": ["政策周期"],
    "产业政策": ["产业周期", "政策周期"],
    "国际新闻": ["美元周期"],
}

# ============================================================
# 关键词词典
# ============================================================

# 文本类型关键词（按优先级排序，命中即分类）
TEXT_TYPE_KEYWORDS = {
    "货币政策": [
        "降准", "降息", "存款准备金", "MLF", "中期借贷便利", "LPR", "贷款市场报价利率",
        "逆回购", "公开市场", "社融", "社会融资", "M2", "货币供应", "央行",
        "流动性", "利率", "再贷款", "再贴现", "SLF", "常备借贷便利",
        "货币政策", "稳健的货币", "适度宽松", "降息降准", "加息",
    ],
    "财政政策": [
        "财政", "赤字", "专项债", "地方债", "国债", "减税", "退税", "降费",
        "财政支出", "转移支付", "补贴", "政府投资", "基建", "特别国债",
        "财政政策", "积极财政", "紧缩财政", "预算", "三公经费",
    ],
    "经济数据": [
        "CPI", "居民消费价格", "PPI", "工业生产者", "GDP", "国内生产总值",
        "PMI", "采购经理指数", "失业率", "调查失业率", "进出口", "贸易顺差",
        "贸易逆差", "社零", "社会消费品零售", "工业增加值", "固定资产投资",
        "房地产投资", "制造业投资", "居民收入", "人均可支配", "经济数据",
        "同比增长", "环比增长", "增速", "涨幅", "跌幅",
    ],
    "监管政策": [
        "证监会", "银保监会", "金融监管", "监管", "处罚", "罚款", "立案",
        "合规", "备案", "审批", "准入", "牌照", "风控", "资本充足率",
        "资管新规", "理财新规", "互联网金融", "反洗钱", "消费者保护",
    ],
    "产业政策": [
        "新能源", "光伏", "风电", "储能", "电动车", "新能源汽车", "芯片",
        "半导体", "集成电路", "人工智能", "AI", "大模型", "制造业",
        "高端制造", "专精特新", "小巨人", "产业政策", "产业升级", "转型",
        "房地产", "楼市", "房价", "限购", "限贷", "保交楼",
    ],
    "国际新闻": [
        "美联储", "美元", "美债", "美股", "汇率", "人民币汇率", "外汇",
        "贸易战", "关税", "制裁", "地缘", "战争", "冲突", "原油",
        "黄金", "大宗商品", "全球", "国际", "外资", "北向资金",
    ],
}

# 周期触发词
CYCLE_TRIGGERS = {
    "债务周期": [
        "债务", "杠杆", "信贷", "社融", "贷款", "违约", "破产", "去杠杆",
        "加杠杆", "资产负债表", "负债", "还本付息", "债务率", "杠杆率",
        "信用扩张", "信用收缩", "影子银行", "非标", "城投债",
        "降准", "降息", "存款准备金", "MLF", "LPR", "流动性", "利率",
        "逆回购", "再贷款", "再贴现", "宽信用", "紧信用", "融资成本",
    ],
    "政策周期": [
        "央行", "财政部", "降准", "降息", "财政", "监管", "政治局",
        "两会", "中央经济工作会议", "国务院", "政策", "调控", "刺激",
        "宽松", "收紧", "转向", "观察期", "货币政策", "财政政策",
        "产业政策", "监管政策",
    ],
    "美元周期": [
        "美元", "美联储", "美债", "汇率", "外汇", "加息", "降息",
        "资本流动", "外资", "北向", "人民币贬值", "人民币升值",
        "美元指数", "美债收益率", "全球流动性",
    ],
    "产业周期": [
        "行业", "产能", "出清", "转型", "新兴", "衰退", "技术迭代",
        "产业升级", "供给侧", "需求侧", "库存", "景气度", "龙头",
        "集中度", "渗透率", "替代", "颠覆",
    ],
    "人口周期": [
        "人口", "出生", "死亡", "老龄化", "劳动力", "退休", "养老",
        "生育率", "出生率", "人口红利", "人口负增长", "少子化",
        "农民工", "就业人口", "劳动年龄",
    ],
    "康波周期": [
        "技术革命", "长周期", "康波", "萧条", "繁荣", "衰退", "复苏",
        "第五波", "第六波", "信息技术", "新能源革命", "通用技术",
        "范式转移", "产业革命",
    ],
}

# 利好利空关键词（带权重）
SENTIMENT_KEYWORDS = {
    # 强利好（+3）
    "strong_positive": [
        ("降准", 3), ("降息", 3), ("全面降准", 3), ("大幅降息", 3),
        ("减税降费", 3), ("大规模刺激", 3), ("万亿级", 3),
        ("取消限购", 3), ("取消限贷", 3), ("全面放开", 3),
    ],
    # 中等利好（+2）
    "medium_positive": [
        ("宽松", 2), ("支持", 2), ("鼓励", 2), ("补贴", 2),
        ("优惠", 2), ("减免", 2), ("下调", 2), ("注入流动性", 2),
        ("稳增长", 2), ("扩内需", 2), ("促消费", 2), ("保就业", 2),
        ("专项债", 2), ("特别国债", 2), ("降首付", 2), ("降利率", 2),
    ],
    # 轻微利好（+1）
    "weak_positive": [
        ("适度宽松", 1), ("灵活适度", 1), ("合理充裕", 1),
        ("结构性支持", 1), ("定向降准", 1), ("优化", 1),
        ("改善", 1), ("回升", 1), ("回暖", 1), ("复苏", 1),
    ],
    # 强利空（-3）
    "strong_negative": [
        ("加息", -3), ("全面收紧", -3), ("大幅加税", -3),
        ("严厉监管", -3), ("全面限制", -3), ("禁令", -3),
        ("债务危机", -3), ("系统性风险", -3), ("崩盘", -3),
        ("暴雷", -3), ("违约潮", -3), ("金融危机", -3),
    ],
    # 中等利空（-2）
    "medium_negative": [
        ("收紧", -2), ("监管加强", -2), ("处罚", -2), ("罚款", -2),
        ("限制", -2), ("打压", -2), ("去杠杆", -2), ("缩表", -2),
        ("加息预期", -2), ("通胀", -2), ("滞胀", -2), ("衰退", -2),
        ("失业率上升", -2), ("房价下跌", -2), ("断供", -2),
        ("限购", -2), ("限贷", -2), ("提高首付", -2),
    ],
    # 轻微利空（-1）
    "weak_negative": [
        ("边际收紧", -1), ("谨慎", -1), ("观望", -1), ("下行", -1),
        ("放缓", -1), ("回落", -1), ("降温", -1), ("调整", -1),
        ("承压", -1), ("压力", -1), ("挑战", -1), ("风险", -1),
    ],
}

# ============================================================
# 判断层核心类
# ============================================================

@dataclass
class JudgmentResult:
    """系统1判断层输出结果"""
    text_type: str = "未知"
    text_type_confidence: float = 0.0
    cycles_involved: Dict[str, bool] = field(default_factory=dict)
    cycles_detail: Dict[str, str] = field(default_factory=dict)
    sentiment_score: float = 0.0  # -5到+5，对底层人
    sentiment_label: str = "中性"
    confidence: float = 0.0
    key_terms: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self):
        return asdict(self)

    def to_markdown(self) -> str:
        """转成Markdown格式，传给系统2翻译层"""
        lines = ["## 系统1判断结果（快速预分析）", ""]
        lines.append(f"**文本类型**：{self.text_type}（置信度{self.text_type_confidence:.0%}）")
        lines.append("")
        lines.append("**涉及周期**：")
        for cycle, involved in self.cycles_involved.items():
            if involved:
                detail = self.cycles_detail.get(cycle, "")
                lines.append(f"- {cycle}：涉及（{detail}）")
            else:
                lines.append(f"- {cycle}：不涉及")
        lines.append("")
        lines.append(f"**利好利空倾向**：{self.sentiment_label}（评分{self.sentiment_score:+.1f}/+5，对底层人）")
        lines.append(f"**判断置信度**：{self.confidence:.0%}")
        if self.key_terms:
            lines.append(f"**命中关键词**：{', '.join(self.key_terms[:15])}")
        lines.append("")
        lines.append(f"**一句话概括**：{self.summary}")
        lines.append("")
        return "\n".join(lines)


class System1Judger:
    """系统1判断层：用规则+关键词快速判断"""

    def __init__(self):
        self.text_type_keywords = TEXT_TYPE_KEYWORDS
        self.cycle_triggers = CYCLE_TRIGGERS
        self.sentiment_keywords = SENTIMENT_KEYWORDS

    def judge(self, text: str) -> JudgmentResult:
        """对输入文本做全面判断"""
        result = JudgmentResult()

        # 0. 正则概念匹配（先于关键词匹配，解决"存款准备金率下调"没匹配"降准"的问题）
        regex_concepts = self._match_regex_concepts(text)
        regex_cycles = set()
        regex_sentiment = 0.0
        for concept in regex_concepts:
            regex_cycles.update(concept["cycles"])
            regex_sentiment += concept["sentiment"]
            result.key_terms.append(concept["label"])

        # 1. 判断文本类型
        result.text_type, result.text_type_confidence, type_terms = self._judge_text_type(text)
        result.key_terms.extend(type_terms)

        # 2. 判断涉及周期（关键词触发 + 正则概念 + 文本类型默认映射）
        result.cycles_involved, result.cycles_detail, cycle_terms = self._judge_cycles(text)
        result.key_terms.extend(cycle_terms)
        # 合并正则概念匹配的周期
        for cycle in regex_cycles:
            if cycle in result.cycles_involved:
                if not result.cycles_involved[cycle]:
                    result.cycles_involved[cycle] = True
                    result.cycles_detail[cycle] = f"正则概念匹配：{', '.join(c['label'] for c in regex_concepts if cycle in c['cycles'])}"
        # 文本类型→默认周期映射
        default_cycles = TYPE_DEFAULT_CYCLES.get(result.text_type, [])
        for cycle in default_cycles:
            if cycle in result.cycles_involved and not result.cycles_involved[cycle]:
                result.cycles_involved[cycle] = True
                if not result.cycles_detail.get(cycle):
                    result.cycles_detail[cycle] = f"文本类型默认关联（{result.text_type}）"

        # 3. 判断利好利空（关键词 + 正则概念 + 否定词处理）
        keyword_sentiment, sentiment_label, sentiment_terms = self._judge_sentiment(text)
        result.key_terms.extend(sentiment_terms)
        # 合并正则概念的情感分（正则概念优先，因为更准确）
        total_sentiment = regex_sentiment * 1.5 + keyword_sentiment * 0.5  # 正则权重更高
        result.sentiment_score = max(-5.0, min(5.0, total_sentiment))
        if result.sentiment_score >= 3:
            result.sentiment_label = "明显利好"
        elif result.sentiment_score >= 1:
            result.sentiment_label = "偏利好"
        elif result.sentiment_score > -1:
            result.sentiment_label = "中性"
        elif result.sentiment_score > -3:
            result.sentiment_label = "偏利空"
        else:
            result.sentiment_label = "明显利空"

        # 4. 计算总体置信度
        type_weight = 0.3
        cycle_weight = 0.3
        sentiment_weight = 0.2
        regex_weight = 0.2  # 正则匹配命中增加置信度
        cycle_count = sum(1 for v in result.cycles_involved.values() if v)
        cycle_conf = min(cycle_count / 3.0, 1.0)
        sentiment_conf = 1.0 if abs(result.sentiment_score) >= 2 else 0.6 if abs(result.sentiment_score) >= 1 else 0.3
        regex_conf = min(len(regex_concepts) / 2.0, 1.0) if regex_concepts else 0.0
        result.confidence = (
            result.text_type_confidence * type_weight +
            cycle_conf * cycle_weight +
            sentiment_conf * sentiment_weight +
            regex_conf * regex_weight
        )

        # 5. 生成一句话概括
        result.summary = self._generate_summary(result)

        # 去重关键词
        result.key_terms = list(dict.fromkeys(result.key_terms))[:20]

        return result

    def _match_regex_concepts(self, text: str) -> List[Dict]:
        """正则概念匹配：把"存款准备金率下调"等匹配为"降准"概念"""
        matches = []
        for pattern, label, cycles, sentiment in REGEX_CONCEPTS:
            if re.search(pattern, text):
                matches.append({
                    "label": label,
                    "cycles": cycles,
                    "sentiment": sentiment,
                    "pattern": pattern
                })
        return matches

    def _judge_text_type(self, text: str) -> Tuple[str, float, List[str]]:
        """判断文本类型"""
        scores = {}
        all_terms = []
        for ttype, keywords in self.text_type_keywords.items():
            hits = [kw for kw in keywords if kw in text]
            if hits:
                # 加权：命中数量+关键词特异性
                score = len(hits) * 1.0 + sum(2.0 for kw in hits if len(kw) >= 4)
                scores[ttype] = score
                all_terms.extend(hits)

        if not scores:
            return "其他", 0.2, all_terms

        # 取最高分
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        total = sum(scores.values())
        confidence = min(best_score / total * 1.5, 1.0)  # 归一化，上限1.0

        return best_type, confidence, all_terms

    def _judge_cycles(self, text: str) -> Tuple[Dict[str, bool], Dict[str, str], List[str]]:
        """判断涉及哪些周期"""
        involved = {}
        detail = {}
        all_terms = []
        for cycle, triggers in self.cycle_triggers.items():
            hits = [kw for kw in triggers if kw in text]
            if hits:
                involved[cycle] = True
                detail[cycle] = f"命中{len(hits)}个关键词：{', '.join(hits[:5])}"
                all_terms.extend(hits)
            else:
                involved[cycle] = False
                detail[cycle] = ""
        return involved, detail, all_terms

    def _judge_sentiment(self, text: str) -> Tuple[float, str, List[str]]:
        """判断利好利空倾向（对底层人），-5到+5。处理否定词翻转。"""
        total_score = 0
        all_terms = []

        # 否定词模式：前面有这些词时，后面的利空词翻转为利好，利好词翻转为利空
        negation_prefixes = ["取消", "放松", "解除", "放宽", "废除", "停止", "不再", "豁免", "放开"]
        intensify_prefixes = ["收紧", "加强", "严格", "扩大", "加码", "升级", "严查", "整治"]

        # 先收集所有关键词及其位置
        keyword_hits = []  # (keyword, weight, position)
        for category, kw_list in self.sentiment_keywords.items():
            for kw, weight in kw_list:
                pos = text.find(kw)
                if pos >= 0:
                    keyword_hits.append((kw, weight, pos))

        # 按位置排序，逐个处理
        for kw, weight, pos in keyword_hits:
            # 检查前面2-4个字是否有否定词或加强词
            prefix_area = text[max(0, pos-4):pos]

            flipped = False
            for neg in negation_prefixes:
                if neg in prefix_area:
                    # 否定词：利空翻利好，利好翻利空
                    weight = -weight
                    all_terms.append(f"{neg}{kw}(翻转)")
                    flipped = True
                    break
            if not flipped:
                for inten in intensify_prefixes:
                    if inten in prefix_area:
                        # 加强词：利空更利空，利好更利好（权重×1.5）
                        weight = weight * 1.5
                        all_terms.append(f"{inten}{kw}(加强)")
                        flipped = True
                        break
            if not flipped:
                all_terms.append(kw)

            total_score += weight

        # 归一化到-5到+5
        normalized = max(-5.0, min(5.0, total_score / 3.0))

        # 标签
        if normalized >= 3:
            label = "明显利好"
        elif normalized >= 1:
            label = "偏利好"
        elif normalized > -1:
            label = "中性"
        elif normalized > -3:
            label = "偏利空"
        else:
            label = "明显利空"

        return normalized, label, all_terms

    def _generate_summary(self, result: JudgmentResult) -> str:
        """生成一句话概括"""
        cycles = [c for c, v in result.cycles_involved.items() if v]
        cycle_str = "、".join(cycles) if cycles else "无明显周期"
        return f"这是一条{result.text_type}类信息，涉及{cycle_str}，对底层人{result.sentiment_label}。"


# ============================================================
# 命令行测试
# ============================================================

if __name__ == "__main__":
    import sys
    judger = System1Judger()

    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = "中国人民银行决定于2026年10月15日下调金融机构存款准备金率0.5个百分点，同时下调中期借贷便利利率10个基点。"

    result = judger.judge(text)
    print(result.to_markdown())
    print("\n=== JSON ===")
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
