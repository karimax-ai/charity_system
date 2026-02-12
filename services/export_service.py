# app/services/export_service.py
import csv
import json
import io
from typing import Dict, Any, List
from datetime import datetime
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from fastapi import HTTPException
import uuid
import os

from schemas.export import ExportRequest, ExportResult, ExportSheet, ExportColumn


class ExportService:
    def __init__(self):
        self.export_dir = "exports"
        os.makedirs(self.export_dir, exist_ok=True)

    async def export_data(self, request: ExportRequest, data: Dict[str, Any]) -> ExportResult:
        """خروجی‌گیری از داده‌ها"""

        if request.format == "csv":
            return await self._export_csv(data, request)
        elif request.format == "excel":
            return await self._export_excel(data, request)
        elif request.format == "pdf":
            return await self._export_pdf(data, request)
        elif request.format == "json":
            return await self._export_json(data, request)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

    async def _export_csv(self, data: Dict[str, Any], request: ExportRequest) -> ExportResult:
        """خروجی CSV"""

        output = io.StringIO()
        writer = csv.writer(output)

        # نوشتن هدر
        if "columns" in data:
            writer.writerow([col["header"] for col in data["columns"]])

        # نوشتن داده‌ها
        for row in data.get("rows", []):
            writer.writerow([row.get(col["key"], "") for col in data.get("columns", [])])

        # ذخیره فایل
        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(self.export_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(output.getvalue())

        file_size = os.path.getsize(filepath)

        return ExportResult(
            success=True,
            format=request.format,
            filename=filename,
            file_size=file_size,
            file_url=f"/exports/{filename}",
            generated_at=datetime.utcnow()
        )

    async def _export_excel(self, data: Dict[str, Any], request: ExportRequest) -> ExportResult:
        """خروجی Excel"""

        with pd.ExcelWriter(f"{self.export_dir}/temp.xlsx", engine='openpyxl') as writer:
            for sheet in data.get("sheets", []):
                df = pd.DataFrame(sheet["data"])
                df.to_excel(writer, sheet_name=sheet["name"], index=False)

        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(self.export_dir, filename)

        os.rename(f"{self.export_dir}/temp.xlsx", filepath)
        file_size = os.path.getsize(filepath)

        return ExportResult(
            success=True,
            format=request.format,
            filename=filename,
            file_size=file_size,
            file_url=f"/exports/{filename}",
            sheets=[s["name"] for s in data.get("sheets", [])],
            generated_at=datetime.utcnow()
        )

    async def _export_pdf(self, data: Dict[str, Any], request: ExportRequest) -> ExportResult:
        """خروجی PDF"""

        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(self.export_dir, filename)

        doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
        story = []
        styles = getSampleStyleSheet()

        # عنوان
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1  # مرکز
        )
        title = Paragraph(request.title or "گزارش", title_style)
        story.append(title)
        story.append(Spacer(1, 0.2 * inch))

        # تاریخ
        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontSize=10,
            alignment=2  # راست
        )
        date_text = f"تاریخ تولید: {datetime.utcnow().strftime('%Y/%m/%d %H:%M')}"
        date = Paragraph(date_text, date_style)
        story.append(date)
        story.append(Spacer(1, 0.3 * inch))

        # جداول
        for sheet in data.get("sheets", []):
            # عنوان جدول
            sheet_title = Paragraph(sheet["name"], styles['Heading2'])
            story.append(sheet_title)
            story.append(Spacer(1, 0.1 * inch))

            # ایجاد جدول
            table_data = []

            # هدر
            headers = [col["header"] for col in sheet["columns"]]
            table_data.append(headers)

            # داده‌ها
            for row in sheet["data"][:50]:  # محدودیت ۵۰ سطر برای PDF
                table_row = []
                for col in sheet["columns"]:
                    value = row.get(col["key"], "")

                    # فرمت‌دهی
                    if col.get("format") == "currency":
                        value = f"{int(value):,}"
                    elif col.get("format") == "percentage":
                        value = f"{value:.1f}%"
                    elif col.get("format") == "date":
                        if value:
                            value = value.strftime("%Y/%m/%d") if hasattr(value, 'strftime') else str(value)

                    table_row.append(str(value))

                table_data.append(table_row)

            # تنظیمات جدول
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(table)
            story.append(Spacer(1, 0.3 * inch))

        doc.build(story)
        file_size = os.path.getsize(filepath)

        return ExportResult(
            success=True,
            format=request.format,
            filename=filename,
            file_size=file_size,
            file_url=f"/exports/{filename}",
            generated_at=datetime.utcnow()
        )

    async def _export_json(self, data: Dict[str, Any], request: ExportRequest) -> ExportResult:
        """خروجی JSON"""

        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.export_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        file_size = os.path.getsize(filepath)

        return ExportResult(
            success=True,
            format=request.format,
            filename=filename,
            file_size=file_size,
            file_url=f"/exports/{filename}",
            generated_at=datetime.utcnow()
        )