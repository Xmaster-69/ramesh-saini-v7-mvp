import json
data = {"key": "value"}
with open("output.json", "w") as f:
    json.dump(data, f)