# models/need_social_share.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from models.base import Base

class NeedSocialShare(Base):
    __tablename__ = "need_social_shares"

    id = Column(Integer, primary_key=True, index=True)
    need_id = Column(Integer, ForeignKey("need_ads.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String, nullable=False)  # telegram, whatsapp, etc.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="social_shares")
    need = relationship("NeedAd", backref="social_shares")
