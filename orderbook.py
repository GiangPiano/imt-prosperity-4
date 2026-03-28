import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("prices_round_0_day_-1.csv", sep=";")

product = "EMERALDS"
timestamp = 0

row = df[(df["product"] == product) & (df["timestamp"] == timestamp)].iloc[0]

bids = []
asks = []

for level in [1, 2, 3]:
    bp = row.get(f"bid_price_{level}")
    bv = row.get(f"bid_volume_{level}")
    ap = row.get(f"ask_price_{level}")
    av = row.get(f"ask_volume_{level}")

    if pd.notna(bp) and pd.notna(bv):
        bids.append((bp, bv))

    if pd.notna(ap) and pd.notna(av):
        asks.append((ap, av))

plt.figure(figsize=(8, 5))

for price, volume in bids:
    plt.barh(price, volume, label="Bid")

for price, volume in asks:
    plt.barh(price, -volume, label="Ask")

plt.axvline(0)
plt.xlabel("Volume (+ bids, - asks)")
plt.ylabel("Price")
plt.title(f"Order Book Snapshot: {product} at t={timestamp}")
plt.grid(True)
plt.show()