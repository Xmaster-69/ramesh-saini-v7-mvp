import os
for f in os.listdir():
    os.rename(f, f + ".encrypted")