from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json


class Trader:
    POSITION_LIMITS = {
        "EMERALDS": 20,
        "TOMATOES": 20,
    }

    EMERALDS_FAIR = 10000

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        # Load saved history
        trader_data = {}
        if state.traderData:
            try:
                trader_data = json.loads(state.traderData)
            except Exception:
                trader_data = {}

        price_history = trader_data.get("price_history", {})

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []

            position = state.position.get(product, 0)
            limit = self.POSITION_LIMITS.get(product, 20)

            if product not in price_history:
                price_history[product] = []

            # Best prices
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

            # Current midpoint
            if best_bid is not None and best_ask is not None:
                bid_vol = abs(order_depth.buy_orders[best_bid])
                ask_vol = abs(order_depth.sell_orders[best_ask])
                mid = (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
            elif best_bid is not None:
                mid = best_bid
            elif best_ask is not None:
                mid = best_ask
            else:
                result[product] = []
                continue

            # Save price history
            price_history[product].append(mid)
            price_history[product] = price_history[product][-20:]  # keep last 20 mids

            # Fair value
            fair = self.get_fair_value(product, price_history[product])

            # Inventory skew:
            # if long, lower fair to encourage selling
            # if short, raise fair to encourage buying
            skew = 0.1 * position
            fair -= skew

            # --- 1) TAKE favorable prices aggressively ---

            # Buy from asks that are cheap relative to fair
            if order_depth.sell_orders:
                for ask_price in sorted(order_depth.sell_orders.keys()):
                    ask_volume = -order_depth.sell_orders[ask_price]  # convert to positive size

                    # only buy if price is clearly good
                    if ask_price < fair - 1:
                        buy_qty = min(ask_volume, limit - position)
                        if buy_qty > 0:
                            orders.append(Order(product, ask_price, buy_qty))
                            position += buy_qty

            # Sell into bids that are rich relative to fair
            if order_depth.buy_orders:
                for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    bid_volume = order_depth.buy_orders[bid_price]

                    if bid_price > fair + 1:
                        sell_qty = min(bid_volume, position + limit)
                        if sell_qty > 0:
                            orders.append(Order(product, bid_price, -sell_qty))
                            position -= sell_qty

            # --- 2) PASSIVE MARKET MAKING ---
            # Quote around fair if we still have inventory room

            buy_capacity = limit - position
            sell_capacity = position + limit

            # choose quote width by product
            if product == "EMERALDS":
                half_spread = 2
                quote_size = 4
            else:  # TOMATOES
                half_spread = 2
                quote_size = 3

            bid_quote = int(fair - half_spread)
            ask_quote = int(fair + half_spread)

            # Improve inside market slightly when sensible
            if best_bid is not None:
                bid_quote = min(bid_quote, best_bid + 1)
            if best_ask is not None:
                ask_quote = max(ask_quote, best_ask - 1)

            # Avoid crossing ourselves accidentally
            if bid_quote < ask_quote:
                if buy_capacity > 0:
                    orders.append(Order(product, bid_quote, min(quote_size, buy_capacity)))
                if sell_capacity > 0:
                    orders.append(Order(product, ask_quote, -min(quote_size, sell_capacity)))

            result[product] = orders

        trader_data = json.dumps({"price_history": price_history})
        conversions = 0
        return result, conversions, trader_data

    def get_fair_value(self, product: str, history: List[float]) -> float:
        if product == "EMERALDS":
            return self.EMERALDS_FAIR

        if product == "TOMATOES":
            if not history:
                return 0
            # EMA implementation (alpha = 0.2 approx equals an 9-period SMA)
            n = 18
            alpha = 2 / (n + 1)
            ema = history[0]
            for price in history[1:]:
                ema = alpha * price + (1 - alpha) * ema
            return ema
        return history[-1]
