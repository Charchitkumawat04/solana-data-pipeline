import json
import pandas as pd

# Load your output
    with open("data/raw/raydium_20260504_090250.json") as f:
        swaps = json.load(f)

df = pd.DataFrame(swaps)

# Sanity check 1: Are there duplicate signatures?
print("Duplicates:", df["signature"].duplicated().sum())  # should be 0

# Sanity check 2: What token pairs did we capture?
df["pair"] = df["token_sold_symbol"] + "→" + df["token_bought_symbol"]
print("\nTop pairs:")
print(df["pair"].value_counts().head(10))

# Sanity check 3: Are amounts sensible?
print("\nAmount stats (sold):")
print(df["token_sold_amount"].describe())

# Sanity check 4: Are all records from expected date?
print("\nDate distribution:")
print(df["block_date"].value_counts())