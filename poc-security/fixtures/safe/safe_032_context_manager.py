class ManagedResource:
    def __enter__(self):
        print("Acquiring")
        return self
    def __exit__(self, *args):
        print("Releasing")

with ManagedResource() as r:
    print("Working")