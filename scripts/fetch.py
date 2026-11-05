#!/usr/bin/env python3
"""A 股数据：拉取、更新、体检。

所有命令都可以直接跑，不依赖 Agent：
    python scripts/fetch.py bars 600519 --start 2024-01-01 --end 2025-12-31
    python scripts/fetch.py update 600519 300750
    python scripts/fetch.py inspect 600519
    python scripts/fetch.py list --board 科创板 --limit 10
    python scripts/fetch.py limits 600519 --date 2025-06-03
    python scripts/fetch.py calendar 2025
    python scripts/fetch.py demo          # 离线自检，用本地缓存
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ── 定位共享内核：环境变量 > 包内布局 > 技能内自带 > 已安装包 ─────────
SKILL_DIR = Path(__file__).resolve().parent.parent
for candidate in (os.getenv("ASHARE_LIB"),
                  SKILL_DIR.parents[1] / "lib" if len(SKILL_DIR.parents) > 1 else None,
                  SKILL_DIR / "lib"):
    if candidate and Path(candidate).is_dir() and (Path(candidate) / "ashare_core").is_dir():
        sys.path.insert(0, str(candidate))
        break

from ashare_core import schema  # noqa: E402
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.providers.base import ProviderError  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402

def _default_data_dir() -> Path:
    """数据目录：环境变量 > 包内布局（<pack>/data）> 用户目录 ~/.ashare/data。"""
    env = os.getenv("ASHARE_DATA")
    if env:
        return Path(env)
    pack_data = SKILL_DIR.parents[1] / "data" if len(SKILL_DIR.parents) > 1 else None
    if pack_data and (pack_data.exists() or (SKILL_DIR.parents[1] / "lib").exists()):
        return pack_data
    return Path.home() / ".ashare" / "data"


DEFAULT_DATA = _default_data_dir()


def _cache(provider) -> BarsCache:
    return BarsCache(provider, DEFAULT_DATA)


def _fmt_table(rows: list[dict], cols: list[str]) -> str:
    widths = {c: max(len(str(c)), *(len(str(r.get(c, ""))) for r in rows)) if rows else len(c)
              for c in cols}
    head = "  ".join(str(c).ljust(widths[c]) for c in cols)
    line = "  ".join("-" * widths[c] for c in cols)
    body = ["  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols) for r in rows]
    return "\n".join([head, line, *body])


# ── 命令 ─────────────────────────────────────────────────────────────
def cmd_bars(args) -> int:
    with EltdxProvider() as p:
        cache = _cache(p)
        df = cache.get(args.code, args.start, args.end, args.adjust, refresh=args.refresh)
    problems = schema.validate_bars(df)
    out = {
        "code": args.code.zfill(6),
        "adjust": args.adjust,
        "rows": int(len(df)),
        "start": str(df["date"].iloc[0]),
        "end": str(df["date"].iloc[-1]),
        "last_close": round(float(df["close"].iloc[-1]), 2),
        "source": str(df["source"].iloc[-1]),
        "problems": problems,
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"✓ {out['code']}  {out['adjust']}  {out['rows']} 根  "
          f"{out['start']} ~ {out['end']}  收盘 {out['last_close']}")
    print(f"  缓存：{DEFAULT_DATA / 'bars' / (out['code'] + '.parquet')}（存全量历史）")
    print(f"  校验：{'通过' if not problems else '；'.join(problems)}")
    return 0 if not problems else 1


def cmd_update(args) -> int:
    ok, failed = [], []
    with EltdxProvider() as p:
        cache = _cache(p)
        for code in args.codes:
            try:
                before = cache.load(code)
                df = cache.get(code, adjust=args.adjust)
                delta = len(df) - (len(before) if before is not None else 0)
                ok.append((code.zfill(6), len(df), str(df["date"].iloc[-1]), delta))
            except Exception as exc:  # noqa: BLE001
                failed.append((code, f"{type(exc).__name__}: {exc}"))
    print(f"更新完成：成功 {len(ok)}，失败 {len(failed)}")
    for code, rows, last, delta in ok:
        print(f"  ✓ {code}  {rows} 根  最后 {last}  新增 {delta:+d}")
    for code, err in failed:
        print(f"  ✗ {code}  {err}")
    return 0 if not failed else 1


def cmd_inspect(args) -> int:
    import pandas as pd

    with EltdxProvider() as p:
        cache = _cache(p)
        raw = cache.load(args.code)
        if raw is None:
            print(f"✗ {args.code} 还没有本地数据，先跑：fetch.py bars {args.code} --start ... --end ...")
            return 1
        end = args.end or str(raw["date"].iloc[-1])
        start = args.start or (pd.Timestamp(end) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
        df = raw[(raw["date"] >= start) & (raw["date"] <= end)]
        problems = schema.validate_bars(df)
        start, end = df["date"].iloc[0], df["date"].iloc[-1]
        try:
            expected = len(p.calendar(start, end))
        except ProviderError:
            expected = None
        zero_vol = int((df["volume"] <= 0).sum())
        out = {
            "code": args.code.zfill(6),
            "window": f"{start} ~ {end}",
            "rows": int(len(df)),
            "cached_rows": int(len(raw)),
            "adjust": str(df["adjust"].iloc[-1]),
            "source": str(df["source"].iloc[-1]),
            "expected_trading_days": expected,
            "missing_days": (expected - len(df)) if expected else None,
            "zero_volume_days": zero_vol,
            "problems": problems,
        }
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        print(f"{out['code']}  {start} ~ {end}  本地 {out['rows']} 根"
              f"（缓存共 {out['cached_rows']} 根，{out['adjust']} / {out['source']}）")
        if expected:
            print(f"  区间交易日 {expected} 天，缺口 {out['missing_days']} 天")
        print(f"  零成交日 {zero_vol} 天")
        print(f"  校验：{'通过' if not problems else '；'.join(problems)}")
        return 0


def cmd_list(args) -> int:
    with EltdxProvider() as p:
        df = p.stock_list()
    if args.board:
        df = df[df["board"] == args.board]
    if args.st:
        df = df[df["is_st"]]
    if args.suspended:
        df = df[df["suspended"]]
    if args.search:
        df = df[df["code"].str.contains(args.search) | df["name"].str.contains(args.search)]
    total = len(df)
    df = df.head(args.limit)
    rows = df.to_dict("records")
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"共 {total} 只（显示前 {len(rows)}）")
    print(_fmt_table(rows, ["code", "name", "board", "lot_size", "is_st", "suspended"]))
    return 0


def cmd_limits(args) -> int:
    with EltdxProvider() as p:
        df = p.limits(args.codes, args.date)
    rows = df.to_dict("records")
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"{args.date} 真实涨跌停")
    print(_fmt_table([{k: r[k] for k in ("code", "pre_close", "limit_up", "limit_down", "limit_rule")}
                      for r in rows], ["code", "pre_close", "limit_up", "limit_down", "limit_rule"]))
    return 0


def cmd_calendar(args) -> int:
    with EltdxProvider() as p:
        days = p.calendar(f"{args.year}-01-01", f"{args.year}-12-31")
    print(f"{args.year} 年交易日：{len(days)} 天，{days[0]} ~ {days[-1]}")
    return 0


def cmd_demo(args) -> int:
    """离线自检：只用本地缓存，验证契约、复权、缺口（默认最近 3 年）。"""
    import pandas as pd

    checks: list[tuple[str, bool, str]] = []
    with EltdxProvider() as p:
        cache = _cache(p)
        code = args.code
        raw = cache.load(code)
        checks.append(("本地缓存存在", raw is not None, f"{code} -> {DEFAULT_DATA}"))
        if raw is None:
            for name, ok, detail in checks:
                print(f"  {'✓' if ok else '✗'} {name}：{detail}")
            print("\n✗ 离线自检未通过：先跑 fetch.py bars 建缓存")
            return 1

        end = str(raw["date"].iloc[-1])
        start = (pd.Timestamp(end) - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
        if start < str(raw["date"].iloc[0]):          # 缓存不足 3 年时，用缓存起点
            start = str(raw["date"].iloc[0])
        df = raw[(raw["date"] >= start) & (raw["date"] <= end)]
        checks.append(("窗口内数据充足", len(df) >= 100, f"{start} ~ {end}，{len(df)} 根"))

        problems = schema.validate_bars(df)
        checks.append(("schema 校验通过", not problems, "；".join(problems) or "无问题"))
        checks.append(("日期升序无重复", df["date"].is_monotonic_increasing and
                       not df["date"].duplicated().any(), f"{len(df)} 行"))
        checks.append(("价格为正", bool((df[["open", "high", "low", "close"]] > 0).all().all()), ""))
        checks.append(("复权口径为 qfq", not df[df["adjust"] == "qfq"].empty, str(df["adjust"].iloc[-1])))

        try:
            days = p.calendar(df["date"].iloc[0], df["date"].iloc[-1])
            gap = len(days) - len(df)
            checks.append(("交易日缺口 ≤ 5 天", abs(gap) <= 5, f"缺口 {gap} 天"))
        except ProviderError:
            checks.append(("交易日历可用", False, "provider 不支持 calendar"))

        print(f"离线自检：{code}（窗口 {start} ~ {end}）")
        for name, ok, detail in checks:
            print(f"  {'✓' if ok else '✗'} {name}" + (f"：{detail}" if detail else ""))
        passed = all(ok for _, ok, _ in checks)
        print(f"\n{'✓ 通过' if passed else '✗ 未通过'}（{sum(ok for _, ok, _ in checks)}/{len(checks)}）")
        return 0 if passed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="A 股数据：拉取 / 更新 / 体检")
    ap.add_argument("--data-dir", default=None, help="缓存目录（默认 <pack>/data）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bars", help="拉取日线（落盘缓存）")
    b.add_argument("code")
    b.add_argument("--start", default=None)
    b.add_argument("--end", default=None)
    b.add_argument("--adjust", default="qfq", choices=["none", "qfq", "hfq"])
    b.add_argument("--refresh", action="store_true", help="忽略缓存重新全量拉取")
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_bars)

    u = sub.add_parser("update", help="增量更新多只股票")
    u.add_argument("codes", nargs="+")
    u.add_argument("--adjust", default="qfq", choices=["none", "qfq", "hfq"])
    u.set_defaults(func=cmd_update)

    i = sub.add_parser("inspect", help="检查本地数据质量（默认最近 3 年）")
    i.add_argument("code")
    i.add_argument("--start", default=None)
    i.add_argument("--end", default=None)
    i.add_argument("--json", action="store_true")
    i.set_defaults(func=cmd_inspect)

    ls = sub.add_parser("list", help="股票清单（含 ST / 停牌）")
    ls.add_argument("--board", default=None)
    ls.add_argument("--st", action="store_true")
    ls.add_argument("--suspended", action="store_true")
    ls.add_argument("--search", default=None)
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    lm = sub.add_parser("limits", help="某日真实涨跌停价")
    lm.add_argument("codes", nargs="+")
    lm.add_argument("--date", required=True)
    lm.add_argument("--json", action="store_true")
    lm.set_defaults(func=cmd_limits)

    cal = sub.add_parser("calendar", help="某年交易日数量")
    cal.add_argument("year", type=int)
    cal.set_defaults(func=cmd_calendar)

    d = sub.add_parser("demo", help="离线自检（不联网）")
    d.add_argument("--code", default="600519")
    d.set_defaults(func=cmd_demo)

    args = ap.parse_args()
    if args.data_dir:
        global DEFAULT_DATA
        DEFAULT_DATA = Path(args.data_dir)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
