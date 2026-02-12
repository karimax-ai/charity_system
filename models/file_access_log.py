# models/file_access_log.py


from sqlalchemy import *
from sqlalchemy.orm import relationship

from models import Base


class FileAccessLog(Base):
    __tablename__ = "file_access_logs"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("file_attachments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # اطلاعات دسترسی
    action = Column(String(50), nullable=False)  # view, download, delete, update
    ip_address = Column(String(45))
    user_agent = Column(Text)
    accessed_via = Column(String(100))  # api, web, mobile

    # نتیجه دسترسی
    success = Column(Boolean, default=True)
    error_message = Column(Text)

    # زمان
    accessed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    file = relationship("FileAttachment", foreign_keys=[file_id])
    user = relationship("User", foreign_keys=[user_id])