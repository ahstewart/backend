from sqlmodel import SQLModel
from database import engine

from schema import UserDB, MLModelDB, ModelVersionDB, InferenceLogDB

def create_db_and_tables():
    print("Creating database tables...")
    SQLModel.metadata.create_all(engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    create_db_and_tables()