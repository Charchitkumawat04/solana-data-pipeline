import json
import pandas as pd
from datetime import datetime

# Load your output
try:
    with open("data/raw/raydium_20260504_090250.json") as f:
        swaps = json.load(f)
except FileNotFoundError:
    print("Error: The data file 'data/raw/raydium_20260504_090250.json' was not found.")
    print("Please make sure the file exists or update the path in src/sanity.py.")
    exit(1)

df = pd.DataFrame(swaps)

if df.empty:
    print("The data file is empty.")
    exit(0)

# Convert timestamp to readable date
df['date'] = pd.to_datetime(df['timestamp'], unit='s')

# Sanity check 1: Are there duplicate signatures?
print("Duplicates:", df["tx_signature"].duplicated().sum())

# Sanity check 2: What token pairs did we capture?
# Using first 4 chars of mint address as a shortcut
df["pair"] = df["token_in_mint"].str[:4] + "→" + df["token_out_mint"].str[:4]
print("\nTop pairs (mint prefixes):")
print(df["pair"].value_counts().head(10))

# Sanity check 3: Are amounts sensible?
print("\nAmount stats (token_in):")
print(df["token_in_amount"].describe())

# Sanity check 4: Date distribution
print("\nDate distribution:")
print(df["date"].dt.date.value_counts())