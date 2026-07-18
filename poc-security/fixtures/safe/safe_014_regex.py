import re
pattern = r"\d{3}-\d{4}"
result = re.findall(pattern, "Call 555-1234")
print(result)