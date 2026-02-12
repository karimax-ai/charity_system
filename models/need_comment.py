from sqlalchemy import Column, Integer, ForeignKey, Text, DateTime, func
from sqlalchemy.orm import relationship

from models.base import Base


class NeedComment(Base):
    __tablename__ = "need_comments"

    id = Column(Integer, primary_key=True)

    need_id = Column(
        Integer,
        ForeignKey("need_ads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    content = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # relationships
    need = relationship("NeedAd", back_populates="comments")
    user = relationship("User", back_populates="need_comments")
