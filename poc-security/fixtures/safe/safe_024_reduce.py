import functools
nums = [1, 2, 3, 4]
total = functools.reduce(lambda a, b: a + b, nums)
print(total)