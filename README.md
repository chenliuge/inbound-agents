# Travel Agents · 业务 Agent 系统

7 个 AI Agent 覆盖入境游旅行社的行业情报、销售支持、内容生产全链路。

## 快速开始

### 安装（每人只做一次）
```bash
git clone https://github.com/chenliuge/travel-agents.git
cd travel-agents
pip install -r requirements.txt
cp .env.example .env   # 填入 ANTHROPIC_API_KEY
```

### 本地运行 Agent
```bash
# Agent 01 · 行业监控官
python agents/01-industry/run.py

# Agent 02 · 用户洞察官
python agents/02-user-insight/run.py

# Agent 03 · 销售/CS官（需粘贴客户对话）
python agents/03-sales-cs/run.py "客户说：你们价格太贵了..."

# Agent 04 · 内容策略官
python agents/04-content-strategy/run.py

# Agent 05 · 爆款分析官（需提供选题方向）
python agents/05-viral-analysis/run.py "日本赏樱入境游攻略"

# Agent 06 · 内容制作官
python agents/06-content-creation/run.py

# Agent 07 · 图片制作官
python agents/07-image-creation/run.py
```

### 审核输出
```bash
# 审核某个 pending 文件
python scripts/approve.py collaboration/01-intel-pool/pending/<文件名>.md

# 带备注审核
python scripts/approve.py collaboration/01-intel-pool/pending/<文件名>.md --note "内容不错"
```

## 数据流向

```
Agent 01 行业监控官 ──┐
                      ├──► Agent 04 内容策略官 ──► Agent 05 爆款分析官
Agent 02 用户洞察官 ──┤                                    │
                      └──► Agent 03 销售/CS官    Agent 06 内容制作官
                                                           │
                                                 Agent 07 图片制作官
```

## 团队协作流程

1. **拉取最新代码**：`git pull origin main`
2. **新建分支**：`git checkout -b yourname/task-description`
3. **运行 Agent**，输出自动写入 `collaboration/*/pending/`
4. **提交 PR**：`git add collaboration/ && git commit -m "说明" && git push`
5. **负责人审核**：在 GitHub 上查看 diff，通过则 Merge

合并 PR = 审核通过，文件自动进入审核状态。

## 修改 Agent Prompt

直接编辑 `agents/0X-xxx/*.md` 文件（IDENTITY / RULES / DATAFLOW / MEMORY / PRIORITY），本地验证效果后提交 PR 即可。团队无需碰 Python 代码。

## GitHub Actions 在线触发

仓库 → Actions 标签页 → 选择对应 Agent → Run workflow → 填参数（如有）→ 点绿色按钮

需要先在 Settings → Secrets → Actions 中添加 `ANTHROPIC_API_KEY`。
