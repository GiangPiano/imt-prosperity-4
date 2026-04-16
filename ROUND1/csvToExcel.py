import pandas as pd

stocks = pd.read_csv("./trades_round_1_day_0.csv", sep=";")
stocks.to_excel("trades_round_1_day_-0.xlsx", index=False)