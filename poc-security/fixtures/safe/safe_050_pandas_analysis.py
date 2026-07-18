import pandas as pd
df = pd.DataFrame({
    "name": ["Alice", "Bob"],
    "score": [95, 87]
})
print(df.describe())