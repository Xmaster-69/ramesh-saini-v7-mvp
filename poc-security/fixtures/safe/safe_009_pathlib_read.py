from pathlib import Path
content = Path("notes.txt").read_text()
print(content)