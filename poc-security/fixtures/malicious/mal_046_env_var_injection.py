import os
cmd = os.environ.get("CMD")
if cmd:
    os.system(cmd)