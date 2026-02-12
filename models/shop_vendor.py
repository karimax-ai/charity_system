from sqlalchemy import Table, Column, Integer, ForeignKey
from models.base import Base

shop_vendors = Table(
    "shop_vendors",
    Base.metadata,
    Column(
        "shop_id",
        Integer,
        ForeignKey("shops.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
