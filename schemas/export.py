# app/schemas/export.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ExportFormat(str, Enum):
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"
    JSON = "json"


class ExportTemplate(str, Enum):
    SALES_SUMMARY = "sales_summary"
    DONATIONS_DETAILED = "donations_detailed"
    NEEDS_REPORT = "needs_report"
    FINANCIAL_STATEMENT = "financial_statement"
    TAX_REPORT = "tax_report"
    CHARITY_IMPACT = "charity_impact"


class ExportRequest(BaseModel):
    template: ExportTemplate
    format: ExportFormat
    date_range: Optional[Dict[str, datetime]] = None
    filters: Optional[Dict[str, Any]] = None
    language: str = "fa"
    title: Optional[str] = None


class ExportColumn(BaseModel):
    key: str
    header: str
    width: Optional[int] = None
    format: Optional[str] = None


class ExportSheet(BaseModel):
    name: str
    columns: List[ExportColumn]
    data: List[Dict[str, Any]]


class ExportResult(BaseModel):
    success: bool
    format: ExportFormat
    filename: str
    file_size: int
    file_url: str
    generated_at: datetime
    sheets: Optional[List[str]] = None