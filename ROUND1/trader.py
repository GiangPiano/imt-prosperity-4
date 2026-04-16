from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional
import json
import statistics


class Trader:
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    OSMIUM_FAIR = 10000
    PEPPER_SLOPE_PER_TIMESTAMP = 0.001  # fitted from sample data

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        trader_data = self.load_data(state.traderData)

        # rolling history
        anchors = trader_data.get("anchors", {})
        mids = trader_data.get("mids", {})

        for product, order_depth in state.order_depths.items():
            if product not in self.POSITION_LIMITS:
                result[product] = []
                continue

            if product not in anchors:
                anchors[product] = []
            if product not in mids:
                mids[product] = []

            position = state.position.get(product, 0)
            limit = self.POSITION_LIMITS[product]
            orders: List[Order] = []

            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

            if best_bid is None and best_ask is None:
                result[product] = []
                continue

            mid = self.get_microprice(order_depth, best_bid, best_ask)
            mids[product].append(mid)
            mids[product] = mids[product][-50:]

            fair = self.get_fair_value(
                product=product,
                timestamp=state.timestamp,
                mid=mid,
                anchors=anchors[product],
                mids=mids[product],
            )

            # inventory skew
            fair -= 0.12 * position

            # signal strength / thresholds
            if product == "ASH_COATED_OSMIUM":
                take_edge = 1.0
                base_half_spread = 2
                quote_size = 8
            else:
                take_edge = 1.0
                base_half_spread = 2
                quote_size = 10

            # 1) Aggressive taking
            position, aggressive_orders = self.take_mispriced_orders(
                product=product,
                order_depth=order_depth,
                fair=fair,
                position=position,
                limit=limit,
                edge=take_edge,
            )
            orders.extend(aggressive_orders)

            # 2) Passive market making
            mm_orders = self.make_markets(
                product=product,
                order_depth=order_depth,
                fair=fair,
                position=position,
                limit=limit,
                base_half_spread=base_half_spread,
                quote_size=quote_size,
            )
            orders.extend(mm_orders)

            result[product] = orders

        new_data = json.dumps({
            "anchors": anchors,
            "mids": mids,
        })

        conversions = 0
        return result, conversions, new_data

    def load_data(self, raw: str) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def get_microprice(
        self,
        order_depth: OrderDepth,
        best_bid: Optional[int],
        best_ask: Optional[int],
    ) -> float:
        if best_bid is not None and best_ask is not None:
            bid_vol = abs(order_depth.buy_orders[best_bid])
            ask_vol = abs(order_depth.sell_orders[best_ask])

            if bid_vol + ask_vol > 0:
                return (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)
            return (best_bid + best_ask) / 2

        if best_bid is not None:
            return float(best_bid)
        return float(best_ask)

    def get_fair_value(
        self,
        product: str,
        timestamp: int,
        mid: float,
        anchors: List[float],
        mids: List[float],
    ) -> float:
        if product == "ASH_COATED_OSMIUM":
            # Very stable around 10000 in samples
            return self.OSMIUM_FAIR

        if product == "INTARIAN_PEPPER_ROOT":
            # Estimate daily anchor from detrended mid:
            # mid ≈ anchor + slope * timestamp
            detrended = mid - self.PEPPER_SLOPE_PER_TIMESTAMP * timestamp
            anchors.append(detrended)
            anchors[:] = anchors[-60:]

            # robust anchor estimate
            if len(anchors) >= 5:
                anchor = statistics.median(anchors[-25:])
            else:
                anchor = detrended

            fair = anchor + self.PEPPER_SLOPE_PER_TIMESTAMP * timestamp

            # tiny momentum/residual adjustment
            if len(mids) >= 6:
                short_ma = sum(mids[-3:]) / 3
                long_ma = sum(mids[-6:]) / 6
                fair += 0.25 * (short_ma - long_ma)

            return fair

        return mid

    def take_mispriced_orders(
        self,
        product: str,
        order_depth: OrderDepth,
        fair: float,
        position: int,
        limit: int,
        edge: float,
    ):
        orders: List[Order] = []

        # Buy cheap asks
        for ask_price in sorted(order_depth.sell_orders.keys()):
            ask_volume = -order_depth.sell_orders[ask_price]
            if ask_price <= fair - edge:
                buy_qty = min(ask_volume, limit - position)
                if buy_qty > 0:
                    orders.append(Order(product, ask_price, buy_qty))
                    position += buy_qty
            else:
                break

        # Sell expensive bids
        for bid_price in sorted(order_depth.buy_orders.keys(), reverse=True):
            bid_volume = order_depth.buy_orders[bid_price]
            if bid_price >= fair + edge:
                sell_qty = min(bid_volume, position + limit)
                if sell_qty > 0:
                    orders.append(Order(product, bid_price, -sell_qty))
                    position -= sell_qty
            else:
                break

        return position, orders

    def make_markets(
        self,
        product: str,
        order_depth: OrderDepth,
        fair: float,
        position: int,
        limit: int,
        base_half_spread: int,
        quote_size: int,
    ) -> List[Order]:
        orders: List[Order] = []

        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        buy_capacity = limit - position
        sell_capacity = position + limit

        # inventory-aware widening
        inv_ratio = abs(position) / max(limit, 1)
        extra_widen = 1 if inv_ratio > 0.5 else 0
        half_spread = base_half_spread + extra_widen

        # reservation-price style quotes
        bid_quote = int(fair - half_spread)
        ask_quote = int(fair + half_spread)

        # improve toward inside market when safe
        if best_bid is not None:
            bid_quote = min(max(bid_quote, best_bid + 1), int(fair - 1))
        if best_ask is not None:
            ask_quote = max(min(ask_quote, best_ask - 1), int(fair + 1))

        if bid_quote >= ask_quote:
            bid_quote = int(fair - 1)
            ask_quote = int(fair + 1)

        # inventory leaning
        if position > 20:
            bid_quote -= 1
            ask_quote -= 1
        elif position < -20:
            bid_quote += 1
            ask_quote += 1

        # primary layer
        if buy_capacity > 0:
            size = min(quote_size, buy_capacity)
            orders.append(Order(product, bid_quote, size))

        if sell_capacity > 0:
            size = min(quote_size, sell_capacity)
            orders.append(Order(product, ask_quote, -size))

        # secondary layer for more queue presence when inventory is light
        if abs(position) < limit * 0.35:
            if buy_capacity - quote_size > 0:
                orders.append(Order(product, bid_quote - 1, min(quote_size // 2, buy_capacity - quote_size)))
            if sell_capacity - quote_size > 0:
                orders.append(Order(product, ask_quote + 1, -min(quote_size // 2, sell_capacity - quote_size)))

        return orders