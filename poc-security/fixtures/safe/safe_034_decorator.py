def timer(f):
    import time
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        print(f"Took {time.time()-start:.2f}s")
        return result
    return wrapper

@timer
def slow_func():
    import time
    time.sleep(0.1)
    return 42