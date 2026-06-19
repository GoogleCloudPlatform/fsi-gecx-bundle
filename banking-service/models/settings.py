from sqlalchemy import Column, String
from utils.database import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
