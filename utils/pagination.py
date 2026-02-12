# utils/pagination.py
from typing import TypeVar, Generic, List, Optional
from pydantic.generics import GenericModel

T = TypeVar('T')

class PaginatedResponse(GenericModel, Generic[T]):
    """پاسخ صفحه‌بندی شده"""
    items: List[T]
    total: int
    page: int
    limit: int
    total_pages: int