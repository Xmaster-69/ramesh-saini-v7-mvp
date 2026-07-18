import json
data = '{"name": "test"}'
parsed = json.loads(data)
print(parsed["name"])