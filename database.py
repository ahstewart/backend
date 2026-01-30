from sqlmodel import create_engine, Session
from config import get_settings

# Get the Settings
settings = get_settings()

# Create the Engine
# echo=True prints the raw SQL to the console (great for debugging)
engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)

# Dependency for FastAPI (Usage later)
def get_session():
    with Session(engine) as session:
        yield session