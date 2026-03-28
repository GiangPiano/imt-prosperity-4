import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Prevents macOS font-manager hangs in terminal

# 1. Load data
df = pd.read_csv('data/prices_round_0_day_-1.csv', sep=';')

# 2. Filter for ONE specific product
target_product = 'EMERALDS'  # Change this to 'EMERALDS' or others as needed
emerald_subset = df[df['product'] == target_product]

# 3. Setup plotting
fig, ax = plt.subplots(figsize=(10, 6))

# 4. Plot only the subset
ax.plot(emerald_subset['timestamp'], emerald_subset['mid_price'], marker='.', color='green', label=target_product)

# 5. Formatting
ax.set_title(f'Market Mid Price: {target_product}')
ax.set_xlabel('Timestamp')
ax.set_ylabel('Mid Price')
ax.legend()
ax.grid(True, linestyle='--', alpha=0.7)

# 6. Save output
plt.savefig('emerald_mid_price_plot.png')
print(f"Plot for {target_product} saved")

# 2. Filter for ONE specific product
target_product = 'TOMATOES'  # Change this to 'EMERALDS' or others as needed
emerald_subset = df[df['product'] == target_product]

# 3. Setup plotting
fig, ax = plt.subplots(figsize=(10, 6))

# 4. Plot only the subset
ax.plot(emerald_subset['timestamp'], emerald_subset['mid_price'], marker='.', color='red', label=target_product)

# 5. Formatting
ax.set_title(f'Market Mid Price: {target_product}')
ax.set_xlabel('Timestamp')
ax.set_ylabel('Mid Price')
ax.legend()
ax.grid(True, linestyle='--', alpha=0.7)

# 6. Save output
plt.savefig('tomatoes_mid_price_plot.png')
print(f"Plot for {target_product} saved")
