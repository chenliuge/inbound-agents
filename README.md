# Inbound Agents · 业务 Agent 系统

6 个 AI Agent 覆盖入境游海外社媒营销：行业监控、内容策略、爆款分析、内容制作、图片制作、视频混剪。

## 快速开始

### 安装（每人只做一次）
```bash
git clone <仓库地址>
cd inbound-agents
pip install -r requirements.txt
cp .env.example .env   # 填入 ANTHROPIC_API_KEY
```

### 本地运行 Agent

```bash
# Agent 01 · 行业监控官
python agents/01-industry/run.py

# Agent 04 · 内容策略官（三层产出：季度/月度/周度）
python agents/04-content-strategy/run.py "生成本季度策略"
python agents/04-content-strategy/run.py "出本月计划"
python agents/04-content-strategy/run.py "帮我出本周选题"

# Agent 05 · 爆款分析官（需选题方向）
python agents/05-viral-analysis/run.py "中国自由行签证攻略"

# Agent 06 · 内容制作官
python agents/06-content-creation/run.py

# Agent 07 · 图片制作官
python agents/07-image-creation/run.py

# Agent 08 · 视频混剪官
python agents/08-video-mix/run.py
```

### 审核输出
```bash
# 审核某个 pending 文件
python scripts/approve.py collaboration/01-intel-pool/pending/<文件名>.md

# 带备注
python scripts/approve.py collaboration/01-intel-pool/pending/<文件名>.md --note "内容不错"
```

## Agent 架构与数据流

```
A1 行业监控官 ──┐
                ├──► A2 内容策略官 ──► A3 爆款分析官
需求池 demand ──┘                              │
                                                ▼
                                    A4 内容制作官 ──┬─► A5 图片制作官
                                                    └─► A6 视频混剪官
```

对应目录：
- A1 → `agents/01-industry/`
- A2 → `agents/04-content-strategy/`
- A3 → `agents/05-viral-analysis/`
- A4 → `agents/06-content-creation/`
- A5 → `agents/07-image-creation/`
- A6 → `agents/08-video-mix/`

## 协作池对照表

| 池 | 写入方 | 下游读取方 |
|---|---|---|
| `01-intel-pool` | A1 | A2 |
| `04-strategy-pool` · `04-monthly-plan-pool` | A2 | A2 自身 + A3 + A4 |
| `05-topic-plan-pool` | A2 | A3 + A4 |
| `06-viral-analysis-pool` | A3 | A4 + A6 |
| `08-draft-pool/{xhs, wechat, video}` | A4 | A5（图片 prompt）/ A6（视频脚本）|
| `09-image-prompt-pool` | A4 | A5 |
| `10-image-output-pool` | A5 | 人工发布 |
| `11-video-mix-pool` | A6 | 人工剪辑（剪映 / CapCut）发布 |
| `demand-pool` | 人工 | A2 |

## 团队协作流程

1. **拉取最新代码**：`git pull origin main`
2. **新建分支**：`git checkout -b yourname/task-description`
3. **运行 Agent**，输出自动写入 `collaboration/*/pending/`
4. **提交 PR**：`git add collaboration/ && git commit -m "说明" && git push`
5. **负责人审核**：在 GitHub 上查看 diff，通过则 Merge
6. **合并 PR = 审核通过**，文件自动进入 approved 状态

## 修改 Agent Prompt

直接编辑 `agents/0X-xxx/*.md` 文件（IDENTITY / RULES / DATAFLOW / MEMORY / PRIORITY），本地验证效果后提交 PR 即可。团队无需碰 Python 代码。

## 共享知识库

位于 `shared/knowledge/`，7 个文件：
- `COMPANY.md` — 公司背景、产品、定价、获客渠道
- `USER.md` — 核心客户画像与决策机制
- `INDUSTRY.md` — 行业数据、产业链、竞争格局
- `BRAND-VOICE.md` — 品牌语气规范与跨平台差异
- `FORBIDDEN.md` — 竞品、禁止承诺、合规红线
- `PLATFORM-RULES.md` — TikTok/IG/YouTube/视频号/小红书 发布规则
- `MARKETING-METHODOLOGY.md` — 本公司海外社媒营销方法论

**初次使用前必须先把 7 个知识文件填好**，否则 Agent 产出会是空泛的通用模板。

## GitHub Actions 在线触发

仓库 → Actions 标签页 → 选择对应 Agent → Run workflow → 填参数（如有）→ 点绿色按钮

需要先在 Settings → Secrets → Actions 中添加 `ANTHROPIC_API_KEY`（或 `TRAVEL_AGENTS_PROD`）。
