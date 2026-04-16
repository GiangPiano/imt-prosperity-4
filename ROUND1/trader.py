from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json


class Trader:
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM":    80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    ASH_FAIR = 10000

    PEPPER_DAY_BASE = 12000

    ENDGAME_TS = 160000
    PANIC_TS   = 190000

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        trader_data = {}
        if state.traderData:
            try:
                trader_data = json.loads(state.traderData)
            except:
                trader_data = {}

        price_history = trader_data.get("price_history", {})

        if "ASH_COATED_OSMIUM" in state.order_depths:
            result["ASH_COATED_OSMIUM"] = self._trade_ash(state)

        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            result["INTARIAN_PEPPER_ROOT"] = self._trade_pepper(state, price_history)

        trader_data = json.dumps({"price_history": price_history})
        return result, 0, trader_data

    # ───────────────────────── ASH (Mean Reversion Pro) ─────────────────────────

    def _trade_ash(self, state: TradingState) -> List[Order]:
        depth    = state.order_depths["ASH_COATED_OSMIUM"]
        position = state.position.get("ASH_COATED_OSMIUM", 0)
        limit    = self.POSITION_LIMITS["ASH_COATED_OSMIUM"]
        fair     = self.ASH_FAIR

        orders: List[Order] = []

        if not depth.buy_orders or not depth.sell_orders:
            return []

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)

        # --- SNIPE (only real edge) ---
        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            if bid >= fair + 2:
                vol = min(depth.buy_orders[bid], position + limit)
                if vol > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", bid, -vol))
                    position -= vol

        for ask in sorted(depth.sell_orders.keys()):
            if ask <= fair - 2:
                vol = min(abs(depth.sell_orders[ask]), limit - position)
                if vol > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", ask, vol))
                    position += vol

        # --- Inventory skew ---
        skew = (position / limit) * 3

        bid_quote = min(best_bid + 1, fair - 1 - skew)
        ask_quote = max(best_ask - 1, fair + 1 - skew)

        buy_cap  = limit - position
        sell_cap = position + limit

        # --- Layered MM ---
        if buy_cap > 0:
            orders.append(Order("ASH_COATED_OSMIUM", round(bid_quote),
                                min(10, buy_cap)))
            if buy_cap > 10:
                orders.append(Order("ASH_COATED_OSMIUM", round(bid_quote) - 2,
                                    min(10, buy_cap - 10)))

        if sell_cap > 0:
            orders.append(Order("ASH_COATED_OSMIUM", round(ask_quote),
                                -min(10, sell_cap)))
            if sell_cap > 10:
                orders.append(Order("ASH_COATED_OSMIUM", round(ask_quote) + 2,
                                    -min(10, sell_cap - 10)))

        return orders

    # ───────────────────────── PEPPER (Alpha Engine) ─────────────────────────

    def _trade_pepper(self, state: TradingState, price_history: dict) -> List[Order]:
        depth = state.order_depths["INTARIAN_PEPPER_ROOT"]
        position = state.position.get("INTARIAN_PEPPER_ROOT", 0)
        limit = self.POSITION_LIMITS["INTARIAN_PEPPER_ROOT"]

        orders: List[Order] = []

        if not depth.buy_orders or not depth.sell_orders:
            return []

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)

        bid_vol = abs(depth.buy_orders[best_bid])
        ask_vol = abs(depth.sell_orders[best_ask])

    # --- Microprice ---
        microprice = (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)

    # --- Init storage ---
        if "pepper_state" not in price_history:
            price_history["pepper_state"] = {
                "est": microprice,
                "var": 10,
                "history": []
            }

        s = price_history["pepper_state"]

    # --- Kalman update ---
        est, var = self._kalman_update(s["est"], s["var"], microprice)
        s["est"], s["var"] = est, var

    # --- Save history ---
        s["history"].append(microprice)
        s["history"] = s["history"][-50:]

        history = s["history"]

    # --- Volatility ---
        if len(history) > 5:
            returns = [history[i] - history[i-1] for i in range(1, len(history))]
            vol = sum(abs(r) for r in returns[-10:]) / 10
        else:
            vol = 2

    # --- Imbalance ---
        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)

    # --- Final fair ---
        fair = est + imbalance * 2

    # --- Confidence (LOW var = HIGH confidence) ---
        confidence = max(0.1, min(1, 10 / (var + 1)))

    # --- Dynamic spread ---
        spread = max(2, int(vol * 1.5))

    # --- Inventory skew ---
        skew = (position / limit) * spread

        bid_quote = round(fair - spread - skew)
        ask_quote = round(fair + spread - skew)

        bid_quote = min(bid_quote, best_bid + 1)
        ask_quote = max(ask_quote, best_ask - 1)

    # --- Position sizing ---
        base_size = int(10 + 20 * confidence)

        buy_cap = limit - position
        sell_cap = position + limit

    # --- Snipe ---
        for ask in sorted(depth.sell_orders.keys()):
            if fair - ask > spread:
                vol = min(abs(depth.sell_orders[ask]), buy_cap)
                if vol > 0:
                    orders.append(Order("INTARIAN_PEPPER_ROOT", ask, vol))
                    position += vol
                    buy_cap -= vol
            else:
                break

        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            if bid - fair > spread:
                vol = min(depth.buy_orders[bid], sell_cap)
                if vol > 0:
                    orders.append(Order("INTARIAN_PEPPER_ROOT", bid, -vol))
                    position -= vol
                    sell_cap -= vol
            else:
                break

    # --- Layered MM ---
        if bid_quote < ask_quote:
            if buy_cap > 0:
                orders.append(Order("INTARIAN_PEPPER_ROOT", bid_quote,
                                min(base_size, buy_cap)))
            if sell_cap > 0:
                orders.append(Order("INTARIAN_PEPPER_ROOT", ask_quote,
                                -min(base_size, sell_cap)))

        return orders

    # ───────────────────────── EMA ─────────────────────────

    def _ema(self, history: List[float], n: int) -> float:
        if not history:
            return 0
        alpha = 2 / (n + 1)
        ema = history[0]
        for p in history[1:]:
            ema = alpha * p + (1 - alpha) * ema
        return ema
    def _kalman_update(self, prev_est, prev_var, price):
        process_var = 1
        meas_var = 4

        pred_est = prev_est
        pred_var = prev_var + process_var

        K = pred_var / (pred_var + meas_var)

        new_est = pred_est + K * (price - pred_est)
        new_var = (1 - K) * pred_var

        return new_est, new_var