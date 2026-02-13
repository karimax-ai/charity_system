# app/services/export_service.py
import csv
import json
import io
from typing import Dict, Any, List
from datetime import datetime
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from fastapi import HTTPException
import uuid
import os

from schemas.export import ExportRequest, ExportResult, ExportSheet, ExportColumn


class ExportService:
    def __init__(self):
        self.export_dir = "exports"
        os.makedirs(self.export_dir, exist_ok=True)

        # ثبت فونت فارسی (فرض بر اینکه فایل فونت در پوشه fonts وجود دارد)
        try:
            pdfmetrics.registerFont(TTFont('Vazir', 'fonts/Vazir.ttf'))
            pdfmetrics.registerFont(TTFont('Vazir-Bold', 'fonts/Vazir-Bold.ttf'))
        except:
            print("Warning: Vazir font not found. Falling back to Helvetica.")

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
        """خروجی CSV - ساده و سریع"""

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)

        # نوشتن هدر (اولین sheet)
        if data.get("sheets"):
            first_sheet = data["sheets"][0]
            if "columns" in first_sheet:
                writer.writerow([col["header"] for col in first_sheet["columns"]])
                for row in first_sheet.get("data", []):
                    writer.writerow([row.get(col["key"], "") for col in first_sheet["columns"]])

        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(self.export_dir, filename)

        with open(filepath, "w", encoding="utf-8-sig") as f:  # utf-8-sig برای اکسل فارسی
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
        """خروجی Excel با چند شیت + رتبه‌بندی"""

        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(self.export_dir, filename)

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            for sheet in data.get("sheets", []):
                if "data" in sheet and "columns" in sheet:
                    df = pd.DataFrame(sheet["data"])
                    # ستون‌ها رو به ترتیب columns مرتب می‌کنیم
                    columns_order = [col["key"] for col in sheet["columns"]]
                    df = df.reindex(columns=columns_order, fill_value="")
                    df.columns = [col["header"] for col in sheet["columns"]]
                    df.to_excel(writer, sheet_name=sheet["name"], index=False)

            # اضافه کردن شیت رتبه‌بندی اگر وجود داشته باشد
            if "top_products" in data:
                df_top = pd.DataFrame(data["top_products"])
                df_top.to_excel(writer, sheet_name="رتبه‌بندی محصولات", index=False)

            if "top_charities" in data:
                df_top_charity = pd.DataFrame(data["top_charities"])
                df_top_charity.to_excel(writer, sheet_name="رتبه‌بندی خیریه‌ها", index=False)

            if "comparison" in data:
                comparison_data = {
                    "معیار": ["دوره فعلی", "دوره قبلی", "نرخ رشد"],
                    "درآمد کل": [
                        data["comparison"]["current"].get("total_revenue", 0),
                        data["comparison"]["previous"].get("total_revenue", 0),
                        f"{data['comparison']['growth'].get('revenue_growth_percent', 0):.2f}%"
                    ],
                    "کمک کل": [
                        data["comparison"]["current"].get("total_donations", 0),
                        data["comparison"]["previous"].get("total_donations", 0),
                        f"{data['comparison']['growth'].get('donations_growth_percent', 0):.2f}%"
                    ]
                }
                df_comparison = pd.DataFrame(comparison_data)
                df_comparison.to_excel(writer, sheet_name="مقایسه دوره‌ها", index=False)

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
        """خروجی PDF با فونت فارسی + راست‌به‌چپ + رتبه‌بندی + مقایسه"""

        filename = f"{request.template.value}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        filepath = os.path.join(self.export_dir, filename)

        doc = SimpleDocTemplate(filepath, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []
        styles = getSampleStyleSheet()

        # فونت فارسی
        try:
            vazir = 'Vazir'
            vazir_bold = 'Vazir-Bold'
        except:
            vazir = 'Helvetica'
            vazir_bold = 'Helvetica-Bold'

        # عنوان گزارش
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontName=vazir_bold,
            fontSize=18,
            spaceAfter=20,
            alignment=1,  # مرکز
            wordWrap='RTL',
            leading=22
        )
        title = Paragraph(request.title or "گزارش سیستم خیریه", title_style)
        story.append(title)
        story.append(Spacer(1, 0.2 * inch))

        # تاریخ تولید
        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontName=vazir,
            fontSize=10,
            alignment=2,  # راست
            wordWrap='RTL'
        )
        date_text = f"تاریخ تولید: {datetime.utcnow().strftime('%Y/%m/%d %H:%M')}"
        date_p = Paragraph(date_text, date_style)
        story.append(date_p)
        story.append(Spacer(1, 0.3 * inch))

        # جداول اصلی
        for sheet in data.get("sheets", []):
            story.append(Paragraph(sheet["name"], styles['Heading2']))
            story.append(Spacer(1, 0.1 * inch))

            table_data = []
            headers = [col["header"] for col in sheet["columns"]]
            table_data.append(headers)

            for row in sheet["data"][:100]:  # افزایش به ۱۰۰ سطر
                table_row = []
                for col in sheet["columns"]:
                    value = row.get(col["key"], "")
                    if col.get("format") == "currency":
                        value = f"{int(value):,}" if value else "۰"
                    elif col.get("format") == "percentage":
                        value = f"{value:.1f}%" if value is not None else "۰%"
                    elif col.get("format") == "date" and value:
                        value = value.strftime("%Y/%m/%d") if hasattr(value, 'strftime') else str(value)
                    table_row.append(str(value))
                table_data.append(table_row)

            table = Table(table_data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), vazir_bold),
                ('FONTNAME', (0, 1), (-1, -1), vazir),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('WORDWRAP', (0, 0), (-1, -1), 'RTL'),
            ]))
            story.append(table)
            story.append(Spacer(1, 0.3 * inch))

        # بخش رتبه‌بندی (اگر وجود داشته باشد)
        if "top_products" in data or "top_charities" in data:
            story.append(Paragraph("رتبه‌بندی ۱۰ مورد برتر", styles['Heading2']))
            story.append(Spacer(1, 0.1 * inch))

            if "top_products" in data:
                story.append(Paragraph("۱۰ محصول برتر از نظر درآمد", styles['Heading3']))
                top_data = [["رتبه", "محصول", "درآمد", "کمک به خیریه"]]
                for i, item in enumerate(data["top_products"][:10], 1):
                    top_data.append([
                        i,
                        item.get("product_name", "نامشخص"),
                        f"{item.get('revenue', 0):,}",
                        f"{item.get('charity_amount', 0):,}"
                    ])
                top_table = Table(top_data)
                top_table.setStyle(TableStyle([
                    ('FONTNAME', (0,0), (-1,-1), vazir),
                    ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ]))
                story.append(top_table)
                story.append(Spacer(1, 0.2 * inch))

            if "top_charities" in data:
                story.append(Paragraph("۱۰ خیریه برتر از نظر کمک دریافتی", styles['Heading3']))
                top_data = [["رتبه", "خیریه", "کمک کل"]]
                for i, item in enumerate(data["top_charities"][:10], 1):
                    top_data.append([
                        i,
                        item.get("charity_name", "نامشخص"),
                        f"{item.get('total_received', 0):,}"
                    ])
                top_table = Table(top_data)
                top_table.setStyle(TableStyle([
                    ('FONTNAME', (0,0), (-1,-1), vazir),
                    ('BACKGROUND', (0,0), (-1,0), colors.lightgreen),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ]))
                story.append(top_table)

            story.append(PageBreak())

        # بخش مقایسه دوره‌ای (اگر وجود داشته باشد)
        if "comparison" in data:
            story.append(Paragraph("مقایسه دوره‌ای", styles['Heading2']))
            story.append(Spacer(1, 0.1 * inch))

            cmp_data = [
                ["معیار", "دوره فعلی", "دوره قبلی", "نرخ رشد"],
                ["درآمد کل",
                 f"{data['comparison']['current']['total_revenue']:,}",
                 f"{data['comparison']['previous']['total_revenue']:,}",
                 f"{data['comparison']['growth']['revenue_growth_percent']:.1f}%"
                ],
                ["کمک کل",
                 f"{data['comparison']['current']['total_donations']:,}",
                 f"{data['comparison']['previous']['total_donations']:,}",
                 f"{data['comparison']['growth']['donations_growth_percent']:.1f}%"
                ]
            ]

            cmp_table = Table(cmp_data)
            cmp_table.setStyle(TableStyle([
                ('FONTNAME', (0,0), (-1,-1), vazir),
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
            ]))
            story.append(cmp_table)

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
        """خروجی JSON - بدون تغییر بزرگ"""

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