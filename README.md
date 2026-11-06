# A股行情数据

**A股行情数据**：一句话拉取 A 股日线、股票清单、涨跌停价和交易日历，落在本地并做数据质量体检。

A股行情数据 Skill：拉取/增量更新日线（前复权 / 后复权 / 原始价）、股票清单（ST、停牌、板块、每手股数）、某日真实涨跌停价、交易日历，并体检本地缓存的数据质量。

- 数据源：`eltdx`（通达信协议）
- 本地存储：Parquet
- 不需要 API key
- 不做投资建议

## 安装

### 方式 A：git clone（推荐）

```bash
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-data.git
```

把目录放到 Agent 的 skills 目录：

```text
Claude Code   ~/.claude/skills/a-share-data/
Codex         ~/.codex/skills/a-share-data/
Cursor        ~/.cursor/skills/a-share-data/
通用           ~/.agents/skills/a-share-data/
```

Windows 示例：

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-data.git "$HOME\.agents\skills\a-share-data"
```

macOS / Linux 示例：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/LINZIQI24GITHUB/finansi-a-share-data.git ~/.agents/skills/a-share-data
```

### 方式 B：让 Agent 安装

把下面这句发给 Claude Code / Codex / Cursor：

```text
Clone https://github.com/LINZIQI24GITHUB/finansi-a-share-data into your skills directory,
install requirements.txt, then read SKILL.md and run the 600519 demo.
```

## 依赖

```bash
cd a-share-data
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Python 3.11+。依赖：pandas、numpy、pyarrow、eltdx。

## 快速开始

```bash
# 拉 600519 日线，前复权，落本地 parquet
python scripts/fetch.py bars 600519 --start 2024-01-01 --end 2026-11-05 --adjust qfq

# 数据质量体检
python scripts/fetch.py inspect 600519 --start 2024-01-01 --end 2026-11-05

# 股票清单（ST / 停牌）
python scripts/fetch.py list --st
python scripts/fetch.py list --suspended

# 某日真实涨跌停价
python scripts/fetch.py limits 600519 --date 2025-06-03

# 交易日历
python scripts/fetch.py calendar 2025
```

也可以在 Agent 里直接说：

```text
用 a-share-data 拉 600519 从 2024-01-01 到今天的前复权日线，存本地，并检查数据质量。
```

## 设计边界

- 数据落在本地 `<skill>/data/` 或 `--data-dir` 指定目录；不上传用户数据。
- 原始行情不随仓库分发；首次使用需能连通通达信行情服务器。
- `inspect` 只检查本地缓存：日期缺口、零成交、复权口径、负价格等。
- 这是数据工具，不是投资建议。

## License

MIT. See [LICENSE](LICENSE).
