"""日频回测引擎：信号次日开盘成交，成交前过一遍账本的真实规则。

设计要点：
- 信号只用当日及之前的数据（由调用方保证），引擎在第 i+1 根开盘执行；
- 涨跌停默认按板块比例兜底计算，需要精确值时可注入 limit_fn；
- 所有成交都走 Account，费用 / T+1 / 最小申报量与实盘完全同一套代码。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import rules
from .account import Account


@dataclass
class BacktestResult:
    account: Account
    equity: pd.Series
    position: pd.Series
    blocked: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {**self.account.snapshot(), "blocked": self.blocked}


def _limit_prices(prev_close: float, code: str, is_st: bool) -> tuple[float, float]:
    """返回 (涨停价, 跌停价)。"""
    pct = rules.limit_ratio(code, is_st)
    return (rules.round_price(prev_close * (1 + pct)),
            rules.round_price(prev_close * (1 - pct)))


def run(
    df: pd.DataFrame,
    signal: pd.Series,
    code: str,
    cash: float = 100_000.0,
    is_st: bool = False,
    slippage: float = 0.0,
) -> BacktestResult:
    df = df.reset_index(drop=True)
    sig = pd.Series(signal).reset_index(drop=True).fillna(0).astype(int).clip(0, 1)
    code = str(code).zfill(6)
    min_qty = rules.min_order_qty(code)
    step = rules.lot_step(code)

    acct = Account(cash)
    blocked = {"limit_up": 0, "limit_down": 0, "cash": 0, "t1": 0}

    equity, positions = [], []
    prev_close: float | None = None

    for i in range(len(df)):
        row = df.iloc[i]
        day = row["date"]
        o, c = float(row["open"]), float(row["close"])
        acct.settle(day)

        if i > 0 and prev_close is not None:
            target = int(sig.iloc[i - 1])
            pos = acct.position(code)
            held = pos.qty if pos else 0
            up, down = _limit_prices(prev_close, code, is_st)

            if target == 1 and held == 0:
                px = o * (1 + slippage)
                budget = acct.cash
                lot = int((budget / (px * (1 + rules.COMMISSION_RATE + rules.TRANSFER_FEE_RATE))) // step) * step
                if lot < min_qty:
                    blocked["cash"] += 1
                else:
                    try:
                        acct.buy(code, px, lot, day, limit_up=up)
                    except rules.OrderRejected as e:
                        blocked["limit_up" if any("涨停" in r for r in e.reasons) else "cash"] += 1
            elif target == 0 and held > 0:
                px = o * (1 - slippage)
                try:
                    acct.sell(code, px, held, day, limit_down=down)
                except rules.OrderRejected as e:
                    blocked["limit_down" if any("跌停" in r for r in e.reasons) else "t1"] += 1

        acct.mark(day, {code: c})
        equity.append(acct.equity)
        positions.append(1 if (acct.position(code) and acct.position(code).qty) else 0)
        prev_close = c

    return BacktestResult(
        account=acct,
        equity=pd.Series(equity, index=df["date"].tolist(), name="equity"),
        position=pd.Series(positions, index=df["date"].tolist(), name="position"),
        blocked=blocked,
    )
