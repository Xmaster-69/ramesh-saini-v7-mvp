from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
    email: str

u = User(id=1, name="Alice", email="a@b.com")
print(u.model_dump_json())