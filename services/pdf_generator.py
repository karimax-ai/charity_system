# app/services/pdf_generator.py - فایل جدید

from typing import Dict, Any, List
from datetime import datetime
import os
from weasyprint import HTML, CSS
from jinja2 import Template
import locale

# تنظیم locale برای اعداد فارسی
try:
    locale.setlocale(locale.LC_ALL, 'fa_IR.UTF-8')
except:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')


class PDFGenerator:
    """تولید گزارش PDF با پشتیبانی کامل از فارسی"""

    # تمپلیت HTML برای گزارش فروش
    SALES_TEMPLATE = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>{{ title }}</title>
        <style>
            @font-face {
                font-family: 'Vazir';
                src: url('fonts/Vazir.ttf') format('truetype');
            }
            body {
                font-family: 'Vazir', sans-serif;
                margin: 40px;
                background: white;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #27ae60;
                padding-bottom: 20px;
            }
            h1 {
                color: #27ae60;
                margin-bottom: 10px;
            }
            .date {
                color: #7f8c8d;
                font-size: 14px;
            }
            .summary {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 30px;
                display: flex;
                justify-content: space-around;
            }
            .summary-item {
                text-align: center;
            }
            .summary-label {
                font-size: 14px;
                color: #7f8c8d;
            }
            .summary-value {
                font-size: 24px;
                font-weight: bold;
                color: #27ae60;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
            }
            th {
                background: #27ae60;
                color: white;
                padding: 12px;
                text-align: center;
            }
            td {
                padding: 10px;
                border-bottom: 1px solid #e0e0e0;
                text-align: center;
            }
            tr:nth-child(even) {
                background: #f8f9fa;
            }
            .footer {
                margin-top: 50px;
                text-align: center;
                color: #7f8c8d;
                font-size: 12px;
                border-top: 1px solid #e0e0e0;
                padding-top: 20px;
            }
            .badge {
                background: #27ae60;
                color: white;
                padding: 5px 10px;
                border-radius: 20px;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{{ title }}</h1>
            <div class="date">تاریخ گزارش: {{ persian_date(generated_at) }}</div>
            <div class="date">دوره: {{ date_range.start }} تا {{ date_range.end }}</div>
        </div>

        <div class="summary">
            <div class="summary-item">
                <div class="summary-label">جمع فروش</div>
                <div class="summary-value">{{ format_currency(summary.total_revenue) }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">تعداد سفارش</div>
                <div class="summary-value">{{ summary.total_orders }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">کمک به خیریه</div>
                <div class="summary-value">{{ format_currency(summary.total_charity) }}</div>
            </div>
        </div>

        <h3>فروش روزانه</h3>
        <table>
            <thead>
                <tr>
                    <th>تاریخ</th>
                    <th>تعداد سفارش</th>
                    <th>فروش (ریال)</th>
                    <th>کمک به خیریه (ریال)</th>
                </tr>
            </thead>
            <tbody>
                {% for item in daily_stats %}
                <tr>
                    <td>{{ item.period }}</td>
                    <td>{{ item.order_count }}</td>
                    <td>{{ format_currency(item.revenue) }}</td>
                    <td>{{ format_currency(item.charity_amount) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <h3>محصولات پرفروش</h3>
        <table>
            <thead>
                <tr>
                    <th>محصول</th>
                    <th>تعداد فروش</th>
                    <th>درآمد (ریال)</th>
                    <th>کمک به خیریه (ریال)</th>
                </tr>
            </thead>
            <tbody>
                {% for product in top_products %}
                <tr>
                    <td>{{ product.product_name }}</td>
                    <td>{{ product.quantity_sold }}</td>
                    <td>{{ format_currency(product.revenue) }}</td>
                    <td>{{ format_currency(product.charity_amount) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="footer">
            <p>این گزارش به صورت خودکار توسط سامانه خیریه تولید شده است.</p>
        </div>
    </body>
    </html>
    """

    # تمپلیت گزارش تأثیر محصولات بر نیازها
    IMPACT_TEMPLATE = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>{{ title }}</title>
        <style>
            @font-face {
                font-family: 'Vazir';
                src: url('fonts/Vazir.ttf') format('truetype');
            }
            body {
                font-family: 'Vazir', sans-serif;
                margin: 40px;
                background: white;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #e67e22;
                padding-bottom: 20px;
            }
            h1 {
                color: #e67e22;
            }
            .impact-card {
                background: #fef5e7;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 20px;
                border-right: 5px solid #e67e22;
            }
            .progress {
                height: 20px;
                background: #f0f0f0;
                border-radius: 10px;
                margin: 10px 0;
            }
            .progress-bar {
                height: 20px;
                background: #27ae60;
                border-radius: 10px;
                width: {{ coverage_percentage }}%;
            }
            .stat {
                display: inline-block;
                margin: 10px;
                padding: 10px;
                background: white;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{{ title }}</h1>
            <div class="date">تاریخ گزارش: {{ persian_date(generated_at) }}</div>
        </div>

        <div class="summary">
            <div class="summary-item">
                <div class="summary-label">تعداد نیازهای بررسی شده</div>
                <div class="summary-value">{{ summary.total_needs_analyzed }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">مبلغ کل نیازها</div>
                <div class="summary-value">{{ format_currency(summary.total_needs_amount) }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">تأمین شده از فروش</div>
                <div class="summary-value">{{ format_currency(summary.total_covered_by_products) }}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">درصد تأمین</div>
                <div class="summary-value">{{ summary.overall_coverage_percentage }}%</div>
            </div>
        </div>

        <h3>نیازهای تحت تأثیر</h3>
        {% for need in impact_by_need %}
        <div class="impact-card">
            <h4>{{ need.need_title }}</h4>
            <p>دسته‌بندی: {{ need.need_category }}</p>
            <div>هدف: {{ format_currency(need.target_amount) }}</div>
            <div>تأمین شده از فروش: {{ format_currency(need.covered_by_products) }}</div>
            <div>درصد تأمین: {{ need.coverage_percentage }}%</div>
            <div class="progress">
                <div class="progress-bar" style="width: {{ need.coverage_percentage }}%;"></div>
            </div>

            {% if need.top_products %}
            <h5>محصولات مشارکت‌کننده:</h5>
            <table>
                <thead>
                    <tr>
                        <th>محصول</th>
                        <th>تعداد</th>
                        <th>کمک (ریال)</th>
                    </tr>
                </thead>
                <tbody>
                    {% for product in need.top_products %}
                    <tr>
                        <td>{{ product.product_name }}</td>
                        <td>{{ product.quantity_sold }}</td>
                        <td>{{ format_currency(product.charity_contribution) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% endif %}
        </div>
        {% endfor %}

        <h3>۱۰ محصول برتر از نظر تأثیر</h3>
        <table>
            <thead>
                <tr>
                    <th>محصول</th>
                    <th>تعداد نیازهای کمک شده</th>
                    <th>جمع کمک (ریال)</th>
                    <th>امتیاز تأثیر</th>
                </tr>
            </thead>
            <tbody>
                {% for product in top_impact_products %}
                <tr>
                    <td>{{ product.product_name }}</td>
                    <td>{{ product.needs_helped_count }}</td>
                    <td>{{ format_currency(product.total_charity_contribution) }}</td>
                    <td>{{ product.impact_score }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """

    def __init__(self):
        # ایجاد پوشه fonts اگر وجود ندارد
        os.makedirs("fonts", exist_ok=True)
        self._check_fonts()

    def _check_fonts(self):
        """بررسی وجود فونت فارسی"""
        font_path = "fonts/Vazir.ttf"
        if not os.path.exists(font_path):
            # اگر فونت وجود نداشت، از فونت سیستمی استفاده کن
            print("⚠️ فونت Vazir یافت نشد. از فونت پیش‌فرض استفاده می‌شود.")

    async def generate_sales_pdf(
            self,
            report_data: Dict[str, Any],
            title: str = "گزارش فروش"
    ) -> bytes:
        """تولید PDF گزارش فروش"""

        # آماده‌سازی داده‌ها
        template_data = self._prepare_sales_data(report_data, title)

        # رندر HTML
        template = Template(self.SALES_TEMPLATE)
        html_content = template.render(**template_data)

        # تولید PDF
        pdf = HTML(string=html_content).write_pdf()

        return pdf

    async def generate_impact_pdf(
            self,
            report_data: Dict[str, Any],
            title: str = "گزارش تأثیر محصولات بر نیازها"
    ) -> bytes:
        """تولید PDF گزارش تأثیر"""

        template_data = self._prepare_impact_data(report_data, title)

        template = Template(self.IMPACT_TEMPLATE)
        html_content = template.render(**template_data)

        pdf = HTML(string=html_content).write_pdf()
        return pdf

    def _prepare_sales_data(self, data: Dict[str, Any], title: str) -> Dict[str, Any]:
        """آماده‌سازی داده‌های فروش برای PDF"""

        summary = data.get("summary", {})
        daily_stats = data.get("daily_stats", [])

        # ۱۰ محصول پرفروش
        all_products = data.get("by_product", [])
        top_products = sorted(
            all_products,
            key=lambda x: x.get("revenue", 0),
            reverse=True
        )[:10]

        return {
            "title": title,
            "generated_at": datetime.utcnow(),
            "persian_date": self._to_persian_date,
            "format_currency": self._format_currency,
            "date_range": {
                "start": data.get("date_range", {}).get("start", ""),
                "end": data.get("date_range", {}).get("end", "")
            },
            "summary": {
                "total_revenue": summary.get("total_revenue", 0),
                "total_orders": summary.get("total_orders", 0),
                "total_charity": summary.get("total_charity", 0)
            },
            "daily_stats": daily_stats[:30],  # ۳۰ روز اخیر
            "top_products": top_products
        }

    def _prepare_impact_data(self, data: Dict[str, Any], title: str) -> Dict[str, Any]:
        """آماده‌سازی داده‌های تأثیر برای PDF"""

        return {
            "title": title,
            "generated_at": datetime.utcnow(),
            "persian_date": self._to_persian_date,
            "format_currency": self._format_currency,
            "summary": data.get("summary", {}),
            "impact_by_need": data.get("impact_by_need", [])[:20],  # ۲۰ نیاز برتر
            "top_impact_products": data.get("top_impact_products", [])
        }

    def _format_currency(self, amount: float) -> str:
        """تبدیل عدد به فرمت ریال با سه رقم سه رقم"""
        if amount is None:
            amount = 0
        try:
            # حذف اعشار و تبدیل به عدد صحیح
            amount_int = int(round(amount))
            # سه رقم سه رقم کردن
            formatted = "{:,}".format(amount_int)
            return f"{formatted} ریال"
        except:
            return f"{int(amount)} ریال"

    def _to_persian_date(self, dt: datetime) -> str:
        """تبدیل تاریخ میلادی به شمسی"""
        if not dt:
            return ""
        try:
            import jdatetime
            persian = jdatetime.datetime.fromgregorian(datetime=dt)
            return persian.strftime("%Y/%m/%d - %H:%M")
        except:
            return dt.strftime("%Y-%m-%d %H:%M")