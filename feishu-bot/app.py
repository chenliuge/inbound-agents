"""飞书机器人中间服务 - 接收飞书消息，触发 GitHub Actions，结果推回飞书"""
from __future__ import annotations
import json
import logging
import os
import re
import threading
import time
import datetime
import traceback

import requests
from flask import Flask, jsonify, request

# ── 日志配置（输出到 stdout，Railway 可捕获）──────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Bot 配置 ─────────────────────────────────────────────────────
BOTS = {
    "cli_a93faf219fb95cb3": {
        "name": "行业监控官",
        "secret": "omE4MO7TDy7g62xEPUqeMfod5v8kOPAC",
        "workflow": "01-industry.yml",
        "branch_prefix": "agent/01-industry",
        "pool": "collaboration/01-intel-pool",
        "needs_input": False,
        "help": (
            "📊 *行业监控官* — 监控竞对 / 客户行业 / AI 行业动态\n\n"
            "用法：\n"
            "  直接 @ 我 → 默认运行（周报，14天）\n"
            "  时间=60 → 检索最近 60 天\n"
            "  频率=月报 → 月报模式（日报 / 周报 / 月报）\n"
            "  聚焦=Klook最新动态 → 本期特殊聚焦指令\n\n"
            "示例：\n"
            "  @行业监控官 时间=60 聚焦=Klook最新产品和定价"
        ),
    },
    "cli_a95d7d4bee389bdf": {
        "name": "用户洞察官",
        "secret": "isxsQqUHVsGawTK2IRdVgbrnhRmVhLMp",
        "workflow": "02-user-insight.yml",
        "branch_prefix": "agent/02-user-insight",
        "pool": "collaboration/02-insight-pool",
        "needs_input": False,
        "help": "📈 *用户洞察官* — 分析目标客源国用户行为和偏好\n\n直接 @ 我即可运行。",
    },
    "cli_a93ff44ec40b5bd3": {
        "name": "销售支持官",
        "secret": "JLmOifjO6rECy2Z0xB50nf43Dzhr22Hs",
        "workflow": "03-sales-cs.yml",
        "branch_prefix": "agent/03-sales-cs",
        "pool": "collaboration/03-sales-support-pool",
        "needs_input": True,
        "input_key": "conversation",
        "help": (
            "💼 *销售支持官* — 分析客户对话，生成跟进建议\n\n"
            "用法：\n"
            "  @销售支持官 [粘贴客户对话内容]\n\n"
            "示例：\n"
            "  @销售支持官 客户说：我们想做海外社媒但不知道从哪里开始..."
        ),
    },
    "cli_a93ffba491229bd9": {
        "name": "内容策略官",
        "secret": "UuhKXfNaZTbYI6YmoS9uigbtbhwpGRXx",
        "workflow": "04-content-strategy.yml",
        "branch_prefix": "agent/04-content-strategy",
        "pool": "collaboration/04-strategy-pool",  # 默认池（实际 pool 由 level 决定，见下方映射）
        "needs_input": False,
        "accepts_instruction": True,  # 接受自由指令文本作为 instruction 参数
        "default_instruction": "做本周选题",
        "help": (
            "📝 *内容策略官* — 三层产出：季度/月度/周度\n\n"
            "用法（直接 @ 我 + 自然语言）：\n"
            "  @内容策略官 生成本季度策略\n"
            "  @内容策略官 出本月计划\n"
            "  @内容策略官 做本周选题（默认）\n\n"
            "识别关键词：\n"
            "  季度 → 季度策略 / 战略 / Q1-Q4 / 新一季\n"
            "  月度 → 月度计划 / 本月 / X月方向\n"
            "  周度 → 周选题 / 本周选题 / 选题计划\n\n"
            "依赖链：月度需要季度已 approved；周度需要月度已 approved。"
        ),
    },
    "cli_a93a614709789cbb": {
        "name": "爆款分析官",
        "secret": "qkMRN1m6XUHnVDdOfC0uJ84qSVWG23iv",
        "workflow": "05-viral-analysis.yml",
        "branch_prefix": "agent/05-viral-analysis",
        "pool": "collaboration/06-viral-analysis-pool",
        "needs_input": False,
        "accepts_instruction": True,  # 自由指令模式
        "default_instruction": "",    # 必须用户提供，不设默认
        "help": (
            "🔥 *爆款分析官* — 找爆款 / 拆结构 / 给 Agent 06 创作蓝本\n\n"
            "当前只做 *图文* 爆款（小红书 + 公众号）,视频暂不处理。\n\n"
            "四种用法：\n\n"
            "1️⃣ 批量分析本周选题（默认推荐）\n"
            "   @爆款分析官\n"
            "   @爆款分析官 批量分析本周选题\n"
            "   → 自动读取最新周选题,对所有「需爆款分析 ✅」的选题逐条分析\n\n"
            "2️⃣ 指定分析第 N 条\n"
            "   @爆款分析官 第 3 条\n"
            "   → 不看是否勾选,强制分析本期第 3 条\n\n"
            "3️⃣ 临时单选题分析（手动提供选题）\n"
            "   @爆款分析官 入境游 GEO 4 步法\n"
            "   → 忽略选题池,直接按这个字符串搜索\n\n"
            "4️⃣ 粘贴爆款链接直接拆解（待实现）\n"
            "   @爆款分析官 拆这条：https://...\n\n"
            "📌 搜索策略：四层递进（精准垂类 → 相邻 → 相关行业 → 结构通用）\n"
            "📌 需 Agent 04 周选题表有「需爆款分析」列；没有则自动按来源类型判断"
        ),
    },
    "cli_a92730aa0a78dbd2": {
        "name": "内容制作官",
        "secret": "Jl1ZGcUhF0QkgwZlbr3D5eidqtVCPBS6",
        "workflow": "06-content-creation.yml",
        "branch_prefix": "agent/06-content-creation",
        "pool": "collaboration/08-draft-pool/xhs",
        "needs_input": False,
        "help": "✍️ *内容制作官* — 自动生成社媒内容草稿\n\n直接 @ 我即可运行。",
    },
    "cli_a93f9b542eb85cd1": {
        "name": "图片制作官",
        "secret": "79Q68r5sqbBPPBXGw7u5aeXXA6Wpet0l",
        "workflow": "07-image-creation.yml",
        "branch_prefix": "agent/07-image-creation",
        "pool": "collaboration/10-image-output-pool",
        "needs_input": False,
        "help": "🖼️ *图片制作官* — 生成社媒配图\n\n直接 @ 我即可运行。",
    },
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "chenliuge/travel-agents"
GH_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ── 去重 & 缓存 ──────────────────────────────────────────────────
_processed_messages: set = set()
_bot_open_id_cache: dict = {}

# ── 请求记录（用于诊断，保留最近20条） ───────────────────────────
_request_log: list = []

def _log_request(app_id: str, data: dict, action: str) -> None:
    try:
        msg = data.get("event", {}).get("message", {})
        content_str = msg.get("content", "{}")
        try:
            text_preview = json.loads(content_str).get("text", "?")[:60]
        except Exception:
            text_preview = content_str[:60]
        entry = {
            "time": datetime.datetime.utcnow().isoformat(),
            "app_id": app_id,
            "action": action,
            "chat_type": msg.get("chat_type", "?"),
            "message_type": msg.get("message_type", "?"),
            "message_id": msg.get("message_id", "?"),
            "text_preview": text_preview,
            "mentions_count": len(msg.get("mentions", [])),
        }
        _request_log.append(entry)
        if len(_request_log) > 20:
            _request_log.pop(0)
        logger.info(f"[webhook] app={app_id[-8:]} action={action} text={text_preview!r}")
    except Exception as e:
        logger.error(f"[_log_request] 日志记录失败：{e}")


# ── 命令解析 ─────────────────────────────────────────────────────

def parse_inputs(text: str, bot: dict) -> tuple[dict, bool]:
    """
    从用户消息中解析参数，返回 (inputs_dict, is_help)。

    通用参数（所有 Agent 支持）：
      时间=N     → time_window_days: N（检索最近 N 天）
      频率=月报  → frequency: monthly（日报 / 周报 / 月报）
      聚焦=...   → focus: "..."（本期特殊聚焦指令）

    Agent 专属输入（needs_input=True 的 Agent）：
      其余文本   → 对应 agent 的 input_key 字段
    """
    # 帮助命令
    if re.search(r'^(帮助|help|\?)$', text.strip(), re.IGNORECASE):
        return {}, True

    inputs: dict = {}

    # 时间窗口：时间=60 / 时间=60天
    m = re.search(r'时间[=＝](\d+)', text)
    if m:
        inputs["time_window_days"] = m.group(1)

    # 频率
    freq_map = {"日报": "daily", "周报": "weekly", "月报": "monthly"}
    m = re.search(r'频率[=＝](日报|周报|月报)', text)
    if m:
        inputs["frequency"] = freq_map[m.group(1)]

    # 聚焦指令：聚焦=... 直到下一个 key= 或字符串结尾
    m = re.search(r'聚焦[=＝](.+?)(?=\s+\S+[=＝]|$)', text)
    if m:
        inputs["focus"] = m.group(1).strip()

    # Agent 专属输入：去掉所有 key=value 后剩余文本
    if bot.get("needs_input") and bot.get("input_key"):
        core = re.sub(r'\S+[=＝]\S+\s*', '', text).strip()
        if core:
            inputs[bot["input_key"]] = core

    # 自由指令模式（如 Agent 04 内容策略官）：剩余文本作为 instruction
    if bot.get("accepts_instruction"):
        core = re.sub(r'\S+[=＝]\S+\s*', '', text).strip()
        inputs["instruction"] = core if core else bot.get("default_instruction", "")

    return inputs, False


# ── 飞书 API ─────────────────────────────────────────────────────

def get_feishu_token(app_id: str, app_secret: str) -> str:
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        token = resp.json().get("tenant_access_token", "")
        if not token:
            logger.error(f"[get_feishu_token] 获取 token 失败，响应：{resp.text[:200]}")
        return token
    except Exception as e:
        logger.error(f"[get_feishu_token] 异常：{e}")
        return ""


def get_bot_open_id(app_id: str, app_secret: str) -> str:
    if app_id in _bot_open_id_cache:
        return _bot_open_id_cache[app_id]
    try:
        token = get_feishu_token(app_id, app_secret)
        resp = requests.get(
            "https://open.feishu.cn/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        open_id = resp.json().get("bot", {}).get("open_id", "")
        if open_id:
            _bot_open_id_cache[app_id] = open_id
        return open_id
    except Exception as e:
        logger.error(f"[get_bot_open_id] 异常：{e}")
        return ""


def reply_message(token: str, message_id: str, text: str) -> None:
    if len(text) > 3800:
        text = text[:3800] + "\n\n...[内容过长，完整报告请查看 GitHub Pull Requests]"
    try:
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"msg_type": "text", "content": json.dumps({"text": text})},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"[reply_message] 发送失败 status={resp.status_code} body={resp.text[:200]}")
    except Exception as e:
        logger.error(f"[reply_message] 异常：{e}")


# ── GitHub API ───────────────────────────────────────────────────

def trigger_workflow(workflow: str, inputs: dict) -> bool:
    try:
        resp = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/dispatches",
            headers=GH_HEADERS,
            json={"ref": "main", "inputs": inputs},
            timeout=15,
        )
        if resp.status_code != 204:
            logger.error(f"[trigger_workflow] 失败 status={resp.status_code} body={resp.text[:200]}")
        return resp.status_code == 204
    except Exception as e:
        logger.error(f"[trigger_workflow] 异常：{e}")
        return False


def wait_for_run(workflow: str, triggered_after: float, timeout: int = 360) -> tuple[bool, int]:
    """等待 workflow 完成，返回 (success, run_id)"""
    deadline = time.time() + timeout
    run_id = None

    while time.time() < deadline:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/runs",
            headers=GH_HEADERS,
            params={"per_page": 5},
            timeout=10,
        )
        for run in resp.json().get("workflow_runs", []):
            ts = datetime.datetime.fromisoformat(
                run["created_at"].replace("Z", "+00:00")
            ).timestamp()
            if ts >= triggered_after - 5:
                run_id = run["id"]
                break
        if run_id:
            break
        time.sleep(5)

    if not run_id:
        return False, 0

    while time.time() < deadline:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs/{run_id}",
            headers=GH_HEADERS,
            timeout=10,
        )
        run = resp.json()
        if run.get("status") == "completed":
            return run.get("conclusion") == "success", run_id
        time.sleep(10)

    return False, run_id


def get_output_from_branch(branch: str, pool: str) -> str:
    """从指定分支读取最新输出文件"""
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{pool}/pending",
        headers=GH_HEADERS,
        params={"ref": branch},
        timeout=10,
    )
    if resp.status_code != 200:
        return ""
    items = resp.json()
    if not isinstance(items, list):
        return ""
    md_files = sorted(
        [f for f in items if f.get("name", "").endswith(".md")],
        key=lambda x: x.get("name", ""),
        reverse=True,
    )
    if not md_files:
        return ""
    content = requests.get(md_files[0]["download_url"], timeout=15).text
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


# ── 核心处理逻辑 ─────────────────────────────────────────────────

def _build_run_summary(inputs: dict, bot_name: str) -> str:
    """生成运行参数摘要，让用户知道 Agent 用了哪些参数"""
    parts = []
    if inputs.get("frequency"):
        freq_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(
            inputs["frequency"], inputs["frequency"]
        )
        parts.append(f"频率={freq_label}")
    if inputs.get("time_window_days"):
        parts.append(f"时间={inputs['time_window_days']}天")
    if inputs.get("focus"):
        parts.append(f'聚焦="{inputs["focus"]}"')
    if inputs.get("instruction"):
        parts.append(f'指令="{inputs["instruction"]}"')

    if parts:
        return f"⏳ {bot_name}正在工作（{' / '.join(parts)}），通常需要2-3分钟，完成后自动回复..."
    return f"⏳ {bot_name}正在工作，通常需要2-3分钟，完成后自动回复..."


def process_agent(bot: dict, app_id: str, message_id: str, inputs: dict) -> None:
    try:
        _process_agent_inner(bot, app_id, message_id, inputs)
    except Exception as e:
        logger.error(f"[process_agent] 未捕获异常: {e}\n{traceback.format_exc()}")
        try:
            token = get_feishu_token(app_id, bot["secret"])
            reply_message(token, message_id, f"❌ 内部错误：{str(e)[:200]}")
        except Exception:
            pass


def _resolve_pool(bot: dict, inputs: dict) -> str:
    """根据 instruction 决定输出池。

    - Agent 04 内容策略官：根据指令里的层级关键词路由到 04-strategy/04-monthly-plan/05-topic-plan
    - 其他 bot（包括 Agent 05 等）：返回 bot["pool"] 默认池
    """
    if not bot.get("accepts_instruction"):
        return bot["pool"]

    # Agent 04 专属的多池路由
    if bot.get("name") == "内容策略官":
        instruction = (inputs.get("instruction") or "").lower()
        for kw in ["季度策略", "季度战略", "战略", "新一季", "本季度", "q1", "q2", "q3", "q4"]:
            if kw.lower() in instruction:
                return "collaboration/04-strategy-pool"
        for kw in ["月度计划", "月度重点", "月度内容", "本月", "月度", "月方向"]:
            if kw in instruction:
                return "collaboration/04-monthly-plan-pool"
        return "collaboration/05-topic-plan-pool"

    # 其他 accepts_instruction 的 bot（如 Agent 05）→ 固定池
    return bot["pool"]


def _process_agent_inner(bot: dict, app_id: str, message_id: str, inputs: dict) -> None:
    token = get_feishu_token(app_id, bot["secret"])

    # 检查 needs_input Agent 是否有内容输入
    if bot.get("needs_input") and not inputs.get(bot.get("input_key", "")):
        reply_message(token, message_id, f"❌ 缺少输入内容\n\n{bot['help']}")
        return

    reply_message(token, message_id, _build_run_summary(inputs, bot["name"]))

    triggered_at = time.time()

    if not trigger_workflow(bot["workflow"], inputs):
        reply_message(token, message_id, "❌ 触发 Agent 失败，请稍后重试")
        return

    success, run_id = wait_for_run(bot["workflow"], triggered_at)

    if not success:
        reply_message(token, message_id, "❌ Agent 执行失败，请查看 GitHub Actions 日志")
        return

    branch = f"{bot['branch_prefix']}-{run_id}"
    pool = _resolve_pool(bot, inputs)
    output = get_output_from_branch(branch, pool)

    if not output:
        reply_message(token, message_id, f"✅ {bot['name']}完成，请查看 GitHub Pull Requests 获取报告")
        return

    reply_message(token, message_id, f"✅ {bot['name']}完成\n\n{output}")


# ── Webhook 路由 ─────────────────────────────────────────────────

@app.route("/webhook/<app_id>", methods=["POST"])
def webhook(app_id: str):
    data = request.json or {}

    # URL 验证（兼容新旧格式）
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})
    if data.get("schema") == "2.0":
        header = data.get("header", {})
        if header.get("event_type") == "url_verification":
            return jsonify({"challenge": data.get("event", {}).get("challenge", "")})

    bot = BOTS.get(app_id)
    if not bot:
        return jsonify({"code": 0})

    event = data.get("event", {})
    message = event.get("message", {})

    if message.get("message_type") != "text":
        _log_request(app_id, data, "skip:not_text")
        return jsonify({"code": 0})

    # 群聊：只响应被 @ 的 bot
    if message.get("chat_type") == "group":
        mentions = message.get("mentions", [])
        raw_content = message.get("content", "{}")
        raw_text_for_check = json.loads(raw_content).get("text", "") if raw_content else ""

        if mentions:
            # 方式1：mentions 数组有值，用 open_id 精确匹配
            bot_open_id = get_bot_open_id(app_id, bot["secret"])
            mentioned_ids = [m.get("id", {}).get("open_id", "") for m in mentions]
            if bot_open_id and bot_open_id not in mentioned_ids:
                _log_request(app_id, data, f"skip:not_mentioned bot={bot_open_id} mentioned={mentioned_ids}")
                return jsonify({"code": 0})
        else:
            # 方式2：mentions 为空（飞书部分版本不填充），改为检查文本中是否包含 bot 名字
            if bot["name"] not in raw_text_for_check:
                _log_request(app_id, data, f"skip:name_not_in_text bot={bot['name']}")
                return jsonify({"code": 0})

    message_id = message.get("message_id", "")
    if not message_id:
        _log_request(app_id, data, "skip:no_message_id")
        return jsonify({"code": 0})

    # 去重
    if message_id in _processed_messages:
        _log_request(app_id, data, "skip:duplicate")
        return jsonify({"code": 0})
    _processed_messages.add(message_id)
    if len(_processed_messages) > 1000:
        _processed_messages.clear()

    content = json.loads(message.get("content", "{}"))
    raw_text = re.sub(r"@\S+\s*", "", content.get("text", "")).strip()

    # 解析命令参数
    inputs, is_help = parse_inputs(raw_text, bot)

    if is_help:
        _log_request(app_id, data, "help")
        token = get_feishu_token(app_id, bot["secret"])
        reply_message(token, message_id, bot.get("help", f"{bot['name']} — 直接 @ 我即可运行"))
        return jsonify({"code": 0})

    _log_request(app_id, data, f"trigger inputs={list(inputs.keys())}")
    threading.Thread(
        target=process_agent,
        args=(bot, app_id, message_id, inputs),
        daemon=True,
    ).start()

    return jsonify({"code": 0})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/last-requests", methods=["GET"])
def last_requests():
    """查看最近收到的飞书消息（用于诊断）"""
    return jsonify(_request_log)


@app.route("/debug", methods=["GET"])
def debug():
    """诊断接口：检查 GitHub Token 和工作流可达性"""
    gh_token_set = bool(GITHUB_TOKEN)
    # 测试 GitHub API 连通性
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows",
            headers=GH_HEADERS,
            timeout=8,
        )
        gh_status = resp.status_code
        workflows = [w["name"] for w in resp.json().get("workflows", [])]
    except Exception as e:
        gh_status = -1
        workflows = [str(e)]

    return jsonify({
        "github_token_set": gh_token_set,
        "github_api_status": gh_status,
        "workflows": workflows,
        "repo": GITHUB_REPO,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
