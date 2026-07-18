import subprocess
result = subprocess.run(["ls", "-la"], capture_output=True)
print(result.stdout)