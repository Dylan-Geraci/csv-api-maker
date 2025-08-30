from sqlalchemy import Column, Integer, String, Text, DateTime, func, UniqueConstraint
from app.db import Base


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    table_name = Column(String(140), nullable=False)
    schema_json = Column(Text, nullable=False)
    row_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now)
    __table_args__ = (UniqueConstraint("name", name="uq_datasets_name"),)
