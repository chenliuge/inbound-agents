"""Agent 05 - 爆款分析官

三种触发模式：
  模式 A：单选题分析
    python3 run.py "入境游 GEO 4 步法"

  模式 B：批量分析本期周选题
    python3 run.py "批量分析本周选题"
    python3 run.py "批量分析 W16"

  模式 C：用户提供爆款参考直接拆解
    python3 run.py "拆这条：https://www.xiaohongshu.com/explore/abc"

档 1：仅用 API 文字元数据做分析（小红书正文 + 抖音文案 + 公众号正文）
档 2：视频还会用 yt-dlp 下载 + Whisper 转写后深度拆解
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from scripts.utils import read_knowledge, read_approved, write_pending, get_client, chat
from scripts.social_crawler import (
    xhs_search_note, xhs_note_detail, xhs_user_post,
    wechat_kw_search, wechat_hot_typical_search, wechat_post_history, wechat_read_zan,
)
# 注：抖音 / 视频下载 / Whisper 转写已移除，当前只做小红书 + 公众号图文


# ============================================================
# 配置加载
# ============================================================

def load_core_config() -> str:
    """加载 Agent 05 所有配置文件，拼接成大段文本。"""
    agent_dir = Path(__file__).parent
    files = [
        "IDENTITY.md",
        "RULES.md",
        "PRIORITY.md",
        "SEARCH_STRATEGY.md",
        "VIRAL_THRESHOLDS.md",
        "EXTRACTION_FRAMEWORK.md",
        "DATAFLOW.md",
        "MEMORY.md",
    ]
    parts = []
    for fn in files:
        path = agent_dir / fn
        if path.exists():
            parts.append(f"## {fn}\n\n{read_knowledge(str(path))}")
        else:
            print(f"[warn] 缺失：{fn}")
    return "\n\n---\n\n".join(parts)


def load_shared_knowledge() -> str:
    """加载公司共享知识。"""
    shared = ROOT / "shared" / "knowledge"
    files = ["COMPANY.md", "USER.md", "BRAND-VOICE.md", "FORBIDDEN.md"]
    parts = []
    for fn in files:
        path = shared / fn
        if path.exists():
            parts.append(f"## shared/knowledge/{fn}\n\n{read_knowledge(str(path))}")
    return "\n\n".join(parts)


def _load_yaml(fname: str) -> dict:
    import yaml
    cfg_path = Path(__file__).parent / "config" / fname
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def load_wechat_accounts() -> dict:
    """读取公众号参考账号池。"""
    return _load_yaml("wechat_accounts.yaml")


def load_xhs_users() -> dict:
    """读取小红书参考账号池。"""
    return _load_yaml("xhs_users.yaml")


def load_latest_topic_plan() -> tuple[str, str]:
    """读取 05-topic-plan-pool/approved/ 最新一期的内容。
    返回 (file_path, content)，若找不到返回 ('', '')
    """
    approved_dir = ROOT / "collaboration" / "05-topic-plan-pool" / "approved"
    if not approved_dir.exists():
        return "", ""
    md_files = sorted(
        approved_dir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not md_files:
        return "", ""
    return str(md_files[0]), md_files[0].read_text(encoding="utf-8")


def parse_topic_table(md_text: str) -> list[dict]:
    """从 markdown 文档里找选题表，解析为 list[dict]。

    策略：找所有 markdown 表格，取第一个列头里包含"选题标题"的。
    每条记录返回 dict，列名 → 值。
    """
    lines = md_text.splitlines()
    topics: list[dict] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 表格头部必须以 | 开头、包含 |
        if not (line.startswith("|") and "|" in line[1:]):
            i += 1
            continue

        # 尝试解析表头
        header_cells = [c.strip() for c in line.strip("|").split("|")]
        if "选题标题" not in header_cells and "标题" not in header_cells:
            i += 1
            continue

        # 下一行应是分隔行
        if i + 1 >= len(lines):
            break
        sep_line = lines[i + 1].strip()
        if not re.match(r"^\|[\s:\-|]+\|$", sep_line):
            i += 1
            continue

        # 开始读数据行
        j = i + 2
        while j < len(lines):
            row = lines[j].strip()
            if not (row.startswith("|") and row.endswith("|")):
                break
            # 跳过全分隔的行
            if re.match(r"^\|[\s:\-|]+\|$", row):
                j += 1
                continue
            cells = [c.strip() for c in row.strip("|").split("|")]
            if len(cells) != len(header_cells):
                j += 1
                continue
            record = dict(zip(header_cells, cells))
            # 过滤空行（所有值都是 ... 或空）
            non_empty = [v for v in record.values() if v and v != "..."]
            if non_empty:
                topics.append(record)
            j += 1

        return topics  # 只取第一张匹配的表

    return topics


def _is_viral_needed(topic: dict) -> bool:
    """判断这条选题是否需爆款分析。"""
    val = (topic.get("需爆款分析") or topic.get("需爆款拆解") or "").strip()
    if "✅" in val or "是" in val:
        return True
    if "❌" in val or "否" in val:
        return False
    # 无标记时按来源类型判断（兼容老数据）
    source = (topic.get("来源类型") or "").strip()
    return source in ("爆款拆解", "外部热点", "需求池")


def _topic_to_query(topic: dict) -> str:
    """从选题 dict 提取用于搜索的主关键词。"""
    return (
        topic.get("选题标题")
        or topic.get("标题")
        or topic.get("核心角度")
        or ""
    ).strip()


def _topic_context(topic: dict) -> str:
    """把选题完整上下文格式化为 LLM prompt 里的引用段。"""
    fields_order = [
        "#", "优先级", "选题标题", "归属支柱", "子方向", "目标平台",
        "目标决策人", "预期作用", "来源类型", "来源详情",
        "业务价值", "钩子", "核心角度", "需爆款分析",
    ]
    lines = []
    for f in fields_order:
        if f in topic and topic[f]:
            lines.append(f"  - {f}：{topic[f]}")
    return "\n".join(lines)


def _extract_user_ids(layer_list: list) -> list[str]:
    """从 yaml 中提取 user_id 列表（支持 str / {user_id, nickname} 两种格式）。"""
    if not layer_list:
        return []
    result = []
    for item in layer_list:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            uid = item.get("user_id") or item.get("id")
            if uid:
                result.append(uid)
    return result


# ============================================================
# 模式识别
# ============================================================

def detect_mode(user_input: str) -> tuple[str, str]:
    """返回 (mode, payload)
    mode: 'single' / 'batch' / 'batch_nth' / 'manual'
    """
    text = user_input.strip()

    # 模式 C：用户提供 URL
    if re.search(r"(https?://)", text):
        return "manual", text

    # 模式 B（精确）：第 N 条
    m = re.search(r"第\s*(\d+)\s*条?", text)
    if m:
        return "batch_nth", m.group(1)

    # 模式 B（批量）：空输入 / "批量分析" / "本周选题" / "W16"
    if (
        not text
        or any(kw in text for kw in ["批量分析", "批量拆解", "本周选题", "分析本周", "分析 w", "分析W", "批量"])
        or re.search(r"^W\d+$", text)
    ):
        return "batch", text

    # 模式 A：单选题手动（默认）
    return "single", text


# ============================================================
# 阈值判定（与 VIRAL_THRESHOLDS.md 同步）
# ============================================================

THRESHOLDS = {
    "xhs": {"big": 10000, "viral": 2000, "potential": 500},
    "wechat": {"big": 100000, "viral": 10000, "potential": 1000},
}
VERTICAL_COEF = 0.3


def score_item(item: dict, platform: str, layer: int) -> str:
    """返回 'big_viral' / 'viral' / 'potential' / 'normal'"""
    th = THRESHOLDS.get(platform, {})
    coef = VERTICAL_COEF if layer in (1, 2) else 1.0

    main_value = 0
    if platform == "xhs":
        main_value = item.get("stats", {}).get("like", 0)
    elif platform == "wechat":
        main_value = item.get("read_count", 0)

    if main_value >= th.get("big", 0) * coef:
        return "big_viral"
    if main_value >= th.get("viral", 0) * coef:
        return "viral"
    if main_value >= th.get("potential", 0) * coef:
        return "potential"
    return "normal"


def is_viral(item: dict, platform: str, layer: int) -> bool:
    """是否达到入选拆解的门槛。"""
    level = score_item(item, platform, layer)
    if layer in (1, 2):
        return level in ("potential", "viral", "big_viral")  # 垂类降门槛
    else:
        return level in ("viral", "big_viral")  # 泛行业要真爆款


# ============================================================
# 四层关键词生成（启发式，LLM 会补充）
# ============================================================

def gen_layer_keywords(topic: str, layer: int) -> list[str]:
    """基于选题生成各层关键词的启发式版本。
    真正的语义扩展由 LLM 做（见 enrich_keywords_by_llm）。
    """
    if layer == 1:
        # 精准：选题原文 + "入境游" 组合
        base = [topic]
        if "入境游" not in topic:
            base.append(f"入境游 {topic}")
            base.append(f"外国游客 {topic}")
        return base[:5]
    return []  # 其他 Layer 完全由 LLM 生成


def enrich_keywords_by_llm(topic: str, layer: int, client) -> list[str]:
    """让 LLM 生成各 Layer 的关键词池（3-8 个）。"""
    layer_desc = {
        2: "相邻垂类（出境游 / 留学 B 端 / 海外营销工具 / 旅行社经营）",
        3: "相关行业（B 端 SaaS / 跨境电商 / 外贸 / 海外 DTC）",
        4: "结构通用层（不限行业，按爆款结构类型如 X 步法/反差/清单/名单点名等）",
    }.get(layer, "")
    if not layer_desc:
        return []

    prompt = (
        f"给定选题：{topic}\n\n"
        f'请为 Layer {layer}（{layer_desc}）生成 5-8 个搜索关键词。\n'
        f"要求：\n"
        f"1. 每个关键词 2-6 个字，适合用于小红书/抖音/公众号搜索\n"
        f"2. 必须符合 Layer {layer} 的语境\n"
        f'3. 直接返回 JSON 数组，不要其他文字：["kw1", "kw2", ...]\n'
    )
    try:
        raw = chat(client, "你是搜索关键词专家。", prompt, max_tokens=500)
        # 提取 JSON 数组
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            kws = json.loads(m.group(0))
            return [k for k in kws if isinstance(k, str) and k][:8]
    except Exception as e:
        print(f"[keyword] LLM 生成失败 Layer {layer}: {e}")
    return []


# ============================================================
# 执行搜索（跨平台、跨 Layer）
# ============================================================

def search_layer(keywords: list[str], layer: int, per_kw_per_platform: int = 10) -> list[dict]:
    """对一个 Layer 的所有关键词，在小红书 + 公众号执行搜索。"""
    results = []
    seen_ids = set()

    for kw in keywords:
        # 小红书
        for item in xhs_search_note(kw, max_results=per_kw_per_platform):
            key = ("xhs", item.get("note_id"))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            item["_platform"] = "xhs"
            item["_layer"] = layer
            item["_keyword"] = kw
            item["_level"] = score_item(item, "xhs", layer)
            results.append(item)

        # 公众号：先 hot_typical（质量高），再 kw_search（量大）
        for item in wechat_hot_typical_search(kw, max_results=per_kw_per_platform):
            key = ("wechat", item.get("url"))
            if key in seen_ids or not item.get("url"):
                continue
            seen_ids.add(key)
            item["_platform"] = "wechat"
            item["_layer"] = layer
            item["_keyword"] = kw
            item["_level"] = score_item(item, "wechat", layer)
            results.append(item)

    return results


def pull_wechat_accounts(accounts: list[str], layer: int) -> list[dict]:
    """按账号池拉公众号文章。"""
    results = []
    seen = set()
    for acc in accounts[:10]:  # 控制 QUOTA
        articles = wechat_post_history(acc, max_articles=10)
        for art in articles:
            if art.get("url") in seen or not art.get("url"):
                continue
            seen.add(art["url"])
            # 补全阅读数
            if not art.get("read_count"):
                rz = wechat_read_zan(art["url"])
                art["read_count"] = rz["read"]
                art["zan_count"] = rz["zan"]
            art["_platform"] = "wechat"
            art["_layer"] = layer
            art["_keyword"] = f"[账号]{acc}"
            art["_level"] = score_item(art, "wechat", layer)
            results.append(art)
    return results


def pull_xhs_users(user_ids: list[str], layer: int) -> list[dict]:
    """按账号池拉小红书笔记。"""
    results = []
    seen = set()
    for uid in user_ids[:10]:  # 控制 QUOTA
        notes = xhs_user_post(uid, max_results=10)
        for n in notes:
            note_id = n.get("note_id")
            if note_id in seen or not note_id:
                continue
            seen.add(note_id)
            n["_platform"] = "xhs"
            n["_layer"] = layer
            n["_keyword"] = f"[账号]{uid[:8]}"
            n["_level"] = score_item(n, "xhs", layer)
            results.append(n)
    return results


# ============================================================
# 核心流程
# ============================================================

def run_single_topic(topic: str, client) -> dict:
    """模式 A：单选题的完整搜索 + 拆解流程。"""
    print(f"\n▶ 分析选题：{topic}")
    all_results = []
    layers_used = {"layer1": 0, "layer2": 0, "layer3": 0, "layer4": 0}
    keywords_by_layer = {}

    # Layer 1：精准
    kws1 = gen_layer_keywords(topic, 1)
    keywords_by_layer[1] = kws1
    print(f"  Layer 1 关键词: {kws1}")
    r1 = search_layer(kws1, 1)
    all_results.extend(r1)
    layers_used["layer1"] = sum(1 for i in r1 if is_viral(i, i["_platform"], 1))
    print(f"  Layer 1: 原始 {len(r1)} 条 / 达标 {layers_used['layer1']} 条")

    # 加载所有账号池（抖音不做池，只靠关键词搜索）
    wechat_cfg = load_wechat_accounts()
    xhs_cfg = load_xhs_users()

    def _pull_pools_for_layer(layer: int, keys: list[str]) -> list[dict]:
        """按 Layer 拉 小红书 + 公众号 的账号池。"""
        pooled = []
        for key in keys:
            wacc = wechat_cfg.get(key, [])
            if wacc:
                pooled.extend(pull_wechat_accounts(wacc, layer))
            xusers = _extract_user_ids(xhs_cfg.get(key, []))
            if xusers:
                pooled.extend(pull_xhs_users(xusers, layer))
        return pooled

    # Layer 1 账号池补充
    r1_pool = _pull_pools_for_layer(1, ["layer_1_inbound"])
    if r1_pool:
        all_results.extend(r1_pool)
        layers_used["layer1"] += sum(1 for i in r1_pool if is_viral(i, i["_platform"], 1))
        print(f"  Layer 1 账号池补充: 小红书/公众号 共 {len(r1_pool)} 条")

    # Layer 2：相邻（条件触发）
    if layers_used["layer1"] < 5:
        kws2 = enrich_keywords_by_llm(topic, 2, client)
        keywords_by_layer[2] = kws2
        print(f"  → 触发 Layer 2 关键词: {kws2}")
        r2 = search_layer(kws2, 2, per_kw_per_platform=5)
        all_results.extend(r2)
        layers_used["layer2"] = sum(1 for i in r2 if is_viral(i, i["_platform"], 2))
        # 账号池补充
        r2_pool = _pull_pools_for_layer(2, ["layer_2_adjacent"])
        if r2_pool:
            all_results.extend(r2_pool)
            layers_used["layer2"] += sum(1 for i in r2_pool if is_viral(i, i["_platform"], 2))
            print(f"  Layer 2 账号池补充: {len(r2_pool)} 条")
        print(f"  Layer 2: 达标 {layers_used['layer2']} 条")

    # Layer 3：相关（条件触发）
    if layers_used["layer1"] + layers_used["layer2"] < 10:
        kws3 = enrich_keywords_by_llm(topic, 3, client)
        keywords_by_layer[3] = kws3
        print(f"  → 触发 Layer 3 关键词: {kws3}")
        r3 = search_layer(kws3, 3, per_kw_per_platform=5)
        all_results.extend(r3)
        layers_used["layer3"] = sum(1 for i in r3 if is_viral(i, i["_platform"], 3))
        r3_pool = _pull_pools_for_layer(3, ["layer_3_related"])
        if r3_pool:
            all_results.extend(r3_pool)
            layers_used["layer3"] += sum(1 for i in r3_pool if is_viral(i, i["_platform"], 3))
            print(f"  Layer 3 账号池补充: {len(r3_pool)} 条")
        print(f"  Layer 3: 达标 {layers_used['layer3']} 条")

    # Layer 4：结构（条件触发）
    if layers_used["layer1"] + layers_used["layer2"] + layers_used["layer3"] < 15:
        kws4 = enrich_keywords_by_llm(topic, 4, client)
        keywords_by_layer[4] = kws4
        print(f"  → 触发 Layer 4 关键词: {kws4}")
        r4 = search_layer(kws4, 4, per_kw_per_platform=5)
        all_results.extend(r4)
        layers_used["layer4"] = sum(1 for i in r4 if is_viral(i, i["_platform"], 4))
        r4_pool = _pull_pools_for_layer(4, ["layer_4_structure"])
        if r4_pool:
            all_results.extend(r4_pool)
            layers_used["layer4"] += sum(1 for i in r4_pool if is_viral(i, i["_platform"], 4))
            print(f"  Layer 4 账号池补充: {len(r4_pool)} 条")
        print(f"  Layer 4: 达标 {layers_used['layer4']} 条")

    # 筛选入选（最多 8 条）
    viral_items = [i for i in all_results if is_viral(i, i["_platform"], i["_layer"])]
    viral_items.sort(key=lambda x: _main_metric(x), reverse=True)
    selected = viral_items[:8]

    # 置信度判定
    l12 = layers_used["layer1"] + layers_used["layer2"]
    total = l12 + layers_used["layer3"] + layers_used["layer4"]
    if l12 >= 3:
        confidence = "high"
    elif total >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    print(f"\n  入选 {len(selected)} 条 | 置信度: {confidence}")

    # 丰富小红书正文（拿 note_detail）
    for item in selected:
        if item["_platform"] == "xhs" and item.get("note_id"):
            detail = xhs_note_detail(item["note_id"])
            if detail.get("desc"):
                item["full_content"] = detail["desc"]
                item["tags"] = detail.get("tags", [])

    return {
        "topic": topic,
        "confidence": confidence,
        "layers_used": layers_used,
        "keywords_by_layer": keywords_by_layer,
        "all_count": len(all_results),
        "selected": selected,
    }


def _main_metric(item: dict) -> int:
    """返回排序用的主指标。"""
    p = item.get("_platform")
    if p == "xhs":
        return item.get("stats", {}).get("like", 0)
    if p == "wechat":
        return item.get("read_count", 0)
    return 0


# ============================================================
# LLM 拆解
# ============================================================

def build_llm_prompt(analysis: dict, core_config: str, shared: str) -> tuple[str, str]:
    """构建发给 LLM 的 system + user prompt。"""
    system = (
        f"# Agent 05 爆款分析官配置\n\n{core_config}\n\n"
        f"# 公司共享知识\n\n{shared}"
    )

    # 用户消息：把搜索结果喂给 LLM
    selected_text = "\n\n---\n\n".join([_format_item_for_prompt(i) for i in analysis["selected"]])

    user = (
        f"# 爆款分析任务（仅小红书+公众号图文）\n\n"
        f"**选题**：{analysis['topic']}\n"
        f"**置信度**：{analysis['confidence']}\n"
        f"**各层命中**：Layer1={analysis['layers_used']['layer1']} / Layer2={analysis['layers_used']['layer2']} "
        f"/ Layer3={analysis['layers_used']['layer3']} / Layer4={analysis['layers_used']['layer4']}\n"
        f"**入选样本数**：{len(analysis['selected'])}\n\n"
        f"## 入选爆款原始数据\n\n{selected_text}\n\n"
        f"---\n\n"
        f"请严格按照 DATAFLOW.md §4.1 的结构输出完整爆款分析报告。\n"
        f"必须：\n"
        f"1. 完成搜索过程说明、入选样本拆解（按 EXTRACTION_FRAMEWORK 图文 7 维）、结构规律归纳\n"
        f"2. 给出【嫁接到未来流量】章节（核心）\n"
        f"3. 给出各平台创作建议（仅小红书 + 公众号）\n"
        f"4. 末尾附交接给 Agent 06 的清单\n"
        f"5. 若置信度为 low，在开头明确标注并列出需要人工补充的内容"
    )
    return system, user


def _format_item_for_prompt(item: dict) -> str:
    """格式化单条爆款样本给 LLM。"""
    p = item["_platform"]
    if p == "xhs":
        s = item.get("stats", {})
        return (
            f"### [小红书] {item.get('title', '')} | Layer {item['_layer']} | {item.get('_level', '')}\n"
            f"URL: {item.get('url', '')}\n"
            f"作者: {item.get('author', {}).get('nickname', '')}\n"
            f"数据: ❤️{s.get('like', 0)} ⭐{s.get('collect', 0)} 💬{s.get('comment', 0)}\n"
            f"关键词命中: {item.get('_keyword', '')}\n"
            f"正文摘要/完整:\n{item.get('full_content') or item.get('desc', '')[:2000]}\n"
            f"标签: {item.get('tags', [])}"
        )
    if p == "wechat":
        return (
            f"### [公众号] {item.get('title', '')} | Layer {item['_layer']} | {item.get('_level', '')}\n"
            f"URL: {item.get('url', '')}\n"
            f"账号: {item.get('account_name', '')}\n"
            f"数据: 👁️{item.get('read_count', 0)} 👍{item.get('zan_count', 0)}\n"
            f"发布: {item.get('publish_date', '')}\n"
            f"关键词命中: {item.get('_keyword', '')}\n"
            f"摘要: {item.get('digest', '')[:500]}"
        )
    return str(item)[:500]


# ============================================================
# 主入口
# ============================================================

def run_batch_mode(nth: int | None, client) -> dict:
    """批量模式 / 指定第 N 条模式。

    参数：
        nth: None 表示分析所有标记为"需爆款分析"的选题
             整数 N 表示只分析第 N 条（不看标记）
    """
    # 1. 读最新选题文件
    topic_file, content = load_latest_topic_plan()
    if not content:
        return {
            "status": "error",
            "message": "未找到 05-topic-plan-pool/approved/ 下的选题文件。请先由内容策略官产出并审核通过。",
        }
    print(f"→ 读取选题文件: {topic_file}")

    # 2. 解析选题表
    topics = parse_topic_table(content)
    if not topics:
        return {
            "status": "error",
            "message": f"选题文件里没有找到可解析的选题表（或列头不含'选题标题'）：{topic_file}",
        }
    print(f"→ 解析到 {len(topics)} 条选题")

    # 3. 选出要分析的选题
    if nth is not None:
        if nth < 1 or nth > len(topics):
            return {
                "status": "error",
                "message": f"第 {nth} 条不存在（当前共 {len(topics)} 条）",
            }
        target_topics = [topics[nth - 1]]
        print(f"→ 指定分析第 {nth} 条")
    else:
        target_topics = [t for t in topics if _is_viral_needed(t)]
        if not target_topics:
            return {
                "status": "error",
                "message": (
                    f"本期 {len(topics)} 条选题中，没有任何一条标记了「需爆款分析 ✅」。"
                    f"若要强制分析，请用 `@爆款分析官 第 N 条`。"
                ),
            }
        print(f"→ 筛选出 {len(target_topics)} 条需分析（共 {len(topics)} 条）")

    # 4. 对每条选题执行完整流程
    all_analyses = []
    for idx, topic in enumerate(target_topics, 1):
        topic_title = _topic_to_query(topic)
        if not topic_title:
            print(f"  [跳过] 第 {idx} 条无有效标题")
            continue
        print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"[{idx}/{len(target_topics)}] 分析：{topic_title}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        analysis = run_single_topic(topic_title, client)
        analysis["_topic_context"] = topic  # 完整上下文附上
        all_analyses.append(analysis)

    # 5. 批量汇总产出（每条调 LLM 生成分析，最后合并为一个 md）
    core_config = load_core_config()
    shared = load_shared_knowledge()

    parts = [
        f"# 本期爆款分析（{len(all_analyses)} 条选题）",
        "",
        f"**选题来源文件**：`{Path(topic_file).name}`",
        f"**分析时间**：{Path(topic_file).stat().st_mtime}",
        "",
        "---",
        "",
    ]

    for idx, analysis in enumerate(all_analyses, 1):
        print(f"\n→ 调用 LLM 生成第 {idx} 条的分析...")
        system, user = build_llm_prompt_with_context(analysis, analysis["_topic_context"], core_config, shared)
        section = chat(client, system, user, max_tokens=8000)
        parts.append(f"## 选题 {idx}：{analysis['topic']}\n\n")
        parts.append(f"**置信度**：{analysis['confidence']} | **入选样本**：{len(analysis['selected'])} 条\n\n")
        parts.append(section)
        parts.append("\n\n---\n\n")

    output = "\n".join(parts)

    # 6. 写入 pool
    tags = [
        f"批量分析",
        f"选题数:{len(all_analyses)}",
        f"来源:{Path(topic_file).stem}",
    ]
    path = write_pending(
        pool="collaboration/06-viral-analysis-pool",
        content=output,
        agent="05-viral-analysis",
        tags=tags,
    )
    print(f"\n✓ 批量分析完成 → {path}")

    return {
        "status": "ok",
        "output_path": str(path),
        "analyzed_count": len(all_analyses),
        "content": output,
    }


def build_llm_prompt_with_context(analysis: dict, topic_context: dict, core_config: str, shared: str) -> tuple[str, str]:
    """构建发给 LLM 的 system + user prompt，带选题完整上下文。"""
    system = (
        f"# Agent 05 爆款分析官配置\n\n{core_config}\n\n"
        f"# 公司共享知识\n\n{shared}"
    )

    context_block = _topic_context(topic_context)
    selected_text = "\n\n---\n\n".join([_format_item_for_prompt(i) for i in analysis["selected"]])

    user = (
        f"# 爆款分析任务（仅小红书+公众号图文）\n\n"
        f"## 选题完整上下文（来自 Agent 04 周选题表）\n\n"
        f"{context_block}\n\n"
        f"---\n\n"
        f"## 搜索结果摘要\n\n"
        f"- **置信度**：{analysis['confidence']}\n"
        f"- **各层命中**：Layer1={analysis['layers_used']['layer1']} / Layer2={analysis['layers_used']['layer2']} "
        f"/ Layer3={analysis['layers_used']['layer3']} / Layer4={analysis['layers_used']['layer4']}\n"
        f"- **入选样本数**：{len(analysis['selected'])}\n\n"
        f"## 入选爆款原始数据\n\n{selected_text}\n\n"
        f"---\n\n"
        f"请严格按照 DATAFLOW.md §4.1 的结构输出爆款分析报告。\n"
        f"**特别注意**：\n"
        f"1. 你必须根据「选题完整上下文」里的『目标平台』『目标决策人』『钩子』『核心角度』来定向拆解\n"
        f"2. 嫁接方案必须呼应选题的「业务价值」字段\n"
        f"3. 仅输出小红书 + 公众号两个平台的建议（本期不做视频）\n"
        f"4. 末尾附交接给 Agent 06 的清单\n"
        f"5. 若置信度为 low，在开头明确标注并列出需要人工补充的内容"
    )
    return system, user


def run_agent_05(user_input: str) -> dict:
    mode, payload = detect_mode(user_input)
    print(f"→ 模式: {mode}")
    print(f"→ 输入: {payload[:100] if payload else '(空)'}")

    core_config = load_core_config()
    shared = load_shared_knowledge()
    client = get_client()

    if mode == "single":
        analysis = run_single_topic(payload, client)
    elif mode == "batch":
        return run_batch_mode(nth=None, client=client)
    elif mode == "batch_nth":
        return run_batch_mode(nth=int(payload), client=client)
    elif mode == "manual":
        print("手动 URL 模式暂未实现，请用批量或单选题模式")
        return {"status": "error", "message": "手动模式待后续版本支持"}
    else:
        return {"status": "error", "message": f"未知模式: {mode}"}

    # --- 以下仅 single 模式走 ---
    if analysis["confidence"] == "low":
        print("⚠️  置信度低，将触发人工补充提示")

    # 调 LLM 写分析
    print("\n→ 调用 LLM 生成分析...")
    system, user = build_llm_prompt(analysis, core_config, shared)
    output = chat(client, system, user, max_tokens=8000)

    # 写入 pool
    safe_topic = re.sub(r'[^\w\u4e00-\u9fff-]', '_', analysis["topic"])[:30]
    tags = [
        f"选题:{safe_topic}",
        f"置信度:{analysis['confidence']}",
        f"入选:{len(analysis['selected'])}",
    ]

    path = write_pending(
        pool="collaboration/06-viral-analysis-pool",
        content=output,
        agent="05-viral-analysis",
        tags=tags,
    )
    print(f"\n✓ 完成 → {path}")

    return {
        "status": "ok",
        "output_path": str(path),
        "confidence": analysis["confidence"],
        "selected_count": len(analysis["selected"]),
        "content": output,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])
    result = run_agent_05(user_input)

    if result["status"] == "error":
        print(f"\n❌ {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
