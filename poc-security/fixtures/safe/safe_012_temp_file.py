import tempfile
with tempfile.NamedTemporaryFile(suffix=".txt") as f:
    f.write(b"hello")