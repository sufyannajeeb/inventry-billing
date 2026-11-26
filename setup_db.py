from database.database import engine, Base
from database import models

Base.metadata.create_all(engine)
print("Tables created successfully.")