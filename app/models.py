from sqlalchemy import Integer, Float, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    used_credits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_credits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
