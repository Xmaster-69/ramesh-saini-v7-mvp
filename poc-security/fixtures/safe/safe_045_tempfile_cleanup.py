import tempfile, os
tmp = tempfile.mkstemp()
os.close(tmp[0])
os.remove(tmp[1])