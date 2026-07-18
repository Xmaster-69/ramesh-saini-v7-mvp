from sqlalchemy import create_engine, text
engine = create_engine("sqlite:///test.db")
with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print(result.fetchone())