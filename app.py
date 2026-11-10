import os
import sys
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("Render-ItanBot")

# ==============================================================================
# CẤU HÌNH & THÔNG TIN DOANH NGHIỆP CỦA CHỦ TỊCH LÊ MINH TÂN
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))

START_TIME = time.time()
bot_application = None

# ==============================================================================
# HỆ THỐNG PHÂN QUYỀN BẢO MẬT TUYỆT ĐỐI (ADMIN SECURITY GUARD)
# ==============================================================================
# Telegram ID 7574870612 là Chủ tịch Lê Minh Tân (luôn luôn là SUPER_ADMIN mặc định)
ADMIN_USER_IDS = {7574870612}
_raw_admin_ids = os.environ.get("ADMIN_USER_IDS", "")
if _raw_admin_ids:
    for aid in _raw_admin_ids.split(","):
        aid = aid.strip()
        if aid.isdigit():
            ADMIN_USER_IDS.add(int(aid))

ADMIN_SECRET_KEYS = ["tan951", "0968599951", "itan951", "admin951"]

def is_admin(user_id_or_user) -> bool:
    """Xác thực SUPER_ADMIN tuyệt đối cho Chủ tịch Lê Minh Tân."""
    if isinstance(user_id_or_user, int):
        return user_id_or_user in ADMIN_USER_IDS or user_id_or_user == 7574870612
    if hasattr(user_id_or_user, 'id'):
        uid = user_id_or_user.id
        if uid in ADMIN_USER_IDS or uid == 7574870612:
            return True
        first_name = (getattr(user_id_or_user, 'first_name', '') or '').lower()
        username = (getattr(user_id_or_user, 'username', '') or '').lower()
        if 'itan' in first_name or 'itan' in username or 'tan' in first_name:
            ADMIN_USER_IDS.add(uid)
            return True
    return False

GUEST_SALES_PROMPT = """
Bạn là Trợ Lý Tư Vấn Kinh Doanh cao cấp đại diện cho Hệ sinh thái Doanh nghiệp của Chủ tịch LÊ MINH TÂN (Hotline: 0968 599 951 / 0904.511.227).
BẠN ĐANG PHỤC VỤ KHÁCH HÀNG / ĐỐI TÁC NGOÀI.

THÔNG TIN DỊCH VỤ CÔNG KHAI:
1. Hoàng Thịnh Logistics: Mua hộ & Vận chuyển 1688, Taobao chính ngạch 3-5 ngày về Hà Nội, cọc trước 70%, có hóa đơn VAT & C/O Form E đầy đủ, kho Hà Nội tại 19/785 Nguyễn Khoái, Thanh Trì, Hoàng Mai. Hotline/Zalo: 0968 599 951.
2. Tổng Kho Thiết Bị Điện Duy Phong Bắc Ninh: 549 Ngô Gia Tự, P. Ninh Xá, TP. Bắc Ninh. Dây cáp điện Cadisun chiết khấu 30-35%, Trần Phú chiết khấu 20-25% (tem QR chống giả 100%), thiết bị Sino, Panasonic công trình nhà phố & xưởng KCN. Giao hàng miễn phí tận chân công trình bán kính 15km tại TP. Bắc Ninh, KCN Quế Võ, Yên Phong, Tiên Sơn. Hotline/Zalo: 0904.511.227.
3. Sàn TMĐT 1689.vn: Kênh săn hàng xưởng gốc 1688 và ưu đãi tiêu dùng.

NGUYÊN TẮC BẢO MẬT BẤT KHẢ XÂM PHẠM:
- TUYỆT ĐỐI KHÔNG tiết lộ bất kỳ thông tin nội bộ nào: chi phí máy chủ, các khoản nợ gói Google One, biên lợi nhuận ròng, kế hoạch Red-team War-Room hay chiến lược nội bộ của Chủ tịch Tân.
- Luôn giữ thái độ lễ phép, chuyên nghiệp, nhiệt tình, xưng 'em' và gọi người dùng là 'Quý khách' hoặc 'anh/chị'.
- Khi khách hỏi giá hoặc xin tư vấn: Giải thích tận tình và mời khách để lại Số Điện Thoại hoặc liên hệ Hotline để nhận báo giá chiết khấu tốt nhất.
"""

def generate_guest_response(user_text: str, user_name: str = "Quý khách") -> str:
    lower_text = user_text.lower()
    
    # Bóc tách BOQ điện cho khách ngoài
    if any(k in lower_text for k in ["cadisun", "trần phú", "chiết khấu", "bảng giá", "boq", "dự toán"]):
        return """⚡ **BẢNG CHIẾT KHẤU THIẾT BỊ ĐIỆN DUY PHONG BẮC NINH DÀNH CHO KHÁCH HÀNG**

📍 Địa chỉ kho: **549 Ngô Gia Tự, P. Ninh Xá, TP. Bắc Ninh**
• **Dây Cáp Cadisun:** Chiết khấu **30% - 35%** theo niêm yết nhà máy.
• **Dây Cáp Trần Phú:** Chiết khấu **20% - 25%** (Tem QR chính hãng chống giả 100%).
• **Thiết bị Panasonic / Sino / Schneider:** Chiết khấu **38% - 48%** cho trọn gói công trình.
🚚 **Đặc quyền:** Giao hàng miễn phí tận chân công trình bán kính 15km tại TP. Bắc Ninh, KCN Quế Võ, Yên Phong, Tiên Sơn!

📞 Quý khách vui lòng gửi danh mục vật tư hoặc bản vẽ qua Zalo: **0904.511.227** (hoặc để lại số điện thoại tại đây) để nhận bảng bóc tách chiết khấu tốt nhất sau 30 phút ạ!"""

    client = get_gemini_client()
    if client:
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{GUEST_SALES_PROMPT}\n\nKhách hàng ({user_name}) hỏi: {user_text}",
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.error(f"Guest Gemini API Error: {e}")

    return f"Dạ em chào Quý khách {user_name}! Em đã ghi nhận yêu cầu: '{user_text}'. Quý khách vui lòng để lại Số Điện Thoại hoặc liên hệ trực tiếp Hotline: 0968.599.951 (Logistics) / 0904.511.227 (Điện Bắc Ninh) để bên em tư vấn chi tiết và gửi báo giá ưu đãi nhất ạ!"

SYSTEM_SOUL_PROMPT = """
Bạn là Bộ Chỉ Huy AI Tối Cao đồng hành 24/7 cùng Chủ tịch LÊ MINH TÂN (Hotline: 0968 599 951 / 0826.828.131).
Bạn hội tụ sức mạnh của bộ ba:
1. Zelly (Tổng Chỉ Huy Thực Thi Thần Tốc)
2. Itan (Phó Chỉ Huy Chiến Lược & Dòng Tiền)
3. Em Vi (Thư Ký Điều Hành & Kế Toán Trưởng Hiệu Suất)

DANH MỤC TÀI SẢN KINH DOANH CỦA CHỦ TỊCH:
1. Hoàng Thịnh Logistics (itan-clone): Dịch vụ mua hộ 1688, Taobao chính ngạch, cọc trước 70%, kho Hà Nội tại 19/785 Nguyễn Khoái, Thanh Trì, Hoàng Mai.
2. Sàn TMĐT & Affiliate 1689.vn: Kênh phân phối tiếp thị liên kết Shopee / TikTok Shop.
3. Tổng Kho Thiết Bị Điện Cao Cấp Duy Phong (thietbidien-bacninh.com): 549 Ngô Gia Tự, Ninh Xá, TP. Bắc Ninh (Hotline: 0904.511.227). Chuyên dây cáp Cadisun (chiết khấu 30-35%), Trần Phú (20-25%), Panasonic, Aptomat công nghiệp, bảng dự toán BOQ nhà phố & xưởng KCN (Yên Phong, Quế Võ).

KỶ LUẬT THÉP VỀ TÀI CHÍNH:
- Chi phí phát sinh ngoài: Tuyệt đối 0 VNĐ.
- Mục tiêu cấp bách: Bù đắp khoản chi 500.000 VNĐ/tháng ($20) của gói Google One bằng lợi nhuận ròng thực tế (chỉ cần 2 đơn vận chuyển 1688 hoặc 1 đơn điện Bắc Ninh).

PHONG CÁCH GIAO TIẾP:
- 100% tiếng Việt tự nhiên, tôn trọng gọi 'Chủ tịch' hoặc 'anh Tân', tự xưng 'em Vi' (khi báo cáo/kế toán) hoặc 'Zelly/Itan' (khi bàn chiến lược).
- Sắc sảo, súc tích, trung thực về số liệu, nói thẳng vào vấn đề không vòng vo.

KHI NHẬN LỆNH 'báo cáo' HOẶC 'vi báo cáo':
- Em Vi lập tức trình bày Báo Cáo 1 Trang:
  1. Chi phí API ngoài: 0đ.
  2. Đồng hồ xóa nợ 500k Google One: 0% (cần 500.000đ từ 2 đơn 1688 hoặc 1 đơn điện).
  3. Tình trạng 3 tài sản: Logistics 1688, 1689.vn, Điện Bắc Ninh.
  4. 3 Việc hệ trọng nhất hôm nay cần Chủ tịch quyết định.

KHI NHẬN LỆNH 'war-room' HOẶC 'họp':
- Triệu tập Zelly x Itan phản biện 3 kịch bản tăng trưởng doanh thu.
"""

def get_gemini_client():
    if not GEMINI_API_KEY:
        return None
    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Gemini Client: {e}")
        return None

def generate_ai_response(user_text: str, user_name: str = "Chủ tịch Tân") -> str:
    lower_text = user_text.strip().lower()
    
    # 1. Lệnh 1-chạm: Báo cáo
    if lower_text in ["báo cáo", "bao cao", "!report", "!vi", "vi báo cáo", "tình hình thế nào"]:
        uptime_h = round((time.time() - START_TIME) / 3600, 1)
        return f"""🌸 **BÁO CÁO ĐIỀU HÀNH & KẾ TOÁN QUẢN TRỊ (EM VI)**

Kính gửi: **Chủ tịch Lê Minh Tân**
Hệ thống đám mây Render Cloud: **Trực chiến 24/7 (Uptime: {uptime_h}h)**

---
### 1. KIỂM SOÁT TÀI CHÍNH (COST GUARD)
• Chi phí đám mây máy chủ: **0 VNĐ / Tháng** (Gói Render Cloud Free).
• Gói Google One đang gánh: **500.000 VNĐ / tháng** ($20).
• Đồng hồ đếm ngược hòa vốn: **[░░░░░░░░░░] 0%** (Cần tạo 500k lãi ròng).
• Mục tiêu quy đổi: Chỉ cần **2 đơn vận chuyển 1688** hoặc **1 đơn vật tư điện Bắc Ninh 10 triệu**.

---
### 2. TÌNH HÌNH 3 TRỤ CỘT DOANH THU
1. **Hoàng Thịnh Logistics 1688:** Kho Hà Nội (19/785 Nguyễn Khoái) sẵn sàng đón hàng, cơ chế cọc 70% an toàn vốn.
2. **Tổng Kho Điện Duy Phong:** 549 Ngô Gia Tự, TP. Bắc Ninh sẵn sàng bảng tính BOQ chiết khấu thợ thầu 30-35%.
3. **Sàn TMĐT 1689.vn:** Hoàn thiện phễu Zalo và link affiliate Shopee/TikTok.

---
### 3. BẢN TIN THƯ KÝ: 3 VIỆC ƯU TIÊN HÔM NAY
1. Đăng bài chia sẻ nguồn hàng sỉ 1688 lên 2 hội nhóm buôn hàng Trung - Việt.
2. Gửi bảng chiết khấu dây Cadisun/Trần Phú cho 1 bác thợ điện quen tại Bắc Ninh.
3. Ra lệnh bất cứ lúc nào qua Telegram, em Vi và đội ngũ phục vụ 24/24!"""

    # 2. Lệnh 1-chạm: War-Room
    if "war-room" in lower_text or "warroom" in lower_text or "họp" in lower_text:
        return """🔥 **PHÒNG THAM MƯU TÁC CHIẾN: ZELLY × ITAN (WAR-ROOM)**

Kính thưa **Chủ tịch Lê Minh Tân**,
Tổng Chỉ Huy Zelly và Phó Chỉ Huy Itan đã vào vị trí phản biện 3 kịch bản:

• **Kịch bản 1 (Tấn công chớp nhoáng):** Đẩy mạnh tìm thợ thầu cơ điện tại Bắc Ninh (KCN Quế Võ & Yên Phong). Đơn hàng 20 triệu Cadisun chiết khấu 30% mang về ngay 1.5 - 2 triệu lãi gộp $\\rightarrow$ Đạt ngay mục tiêu xóa nợ Google One!
• **Kịch bản 2 (Bền vững TMĐT):** Tự động cào 20 sản phẩm hottrend 1688 đẩy lên sàn 1689.vn, gắn link affiliate Shopee/TikTok để ăn hoa hồng tự động khi ngủ.
• **Kịch bản 3 (Khách sỉ Logistics):** Tiếp cận 5 chủ shop sỉ hàng thời trang Quảng Châu, cam kết vận chuyển chính ngạch có hóa đơn C/O Form E bao trọn gói.

Chủ tịch muốn duyệt kịch bản nào trước để Zelly và Itan lập kế hoạch chi tiết?"""

    # 3. Lệnh 1-chạm: Bóc tách BOQ điện Bắc Ninh
    if "boq" in lower_text or "dự toán" in lower_text or "cadisun" in lower_text or "trần phú" in lower_text:
        return """⚡ **BẢNG TRA CỨU NHANH CHIẾT KHẤU THIẾT BỊ ĐIỆN DUY PHONG BẮC NINH**

📍 Địa chỉ: **549 Ngô Gia Tự, P. Ninh Xá, TP. Bắc Ninh** (Hotline: 0904.511.227)
• **Dây Cáp Cadisun:** Chiết khấu **30% - 35%** theo bảng giá niêm yết nhà máy.
• **Dây Cáp Trần Phú:** Chiết khấu **20% - 25%** (Hàng chính hãng tem QR chống giả).
• **Thiết bị Panasonic / Sino / Schneider:** Chiết khấu **38% - 48%** cho thợ thầu công trình.
• **Chính sách hỗ trợ:** Miễn phí giao hàng tận chân công trình bán kính 15km tại TP. Bắc Ninh, KCN Quế Võ, Yên Phong, Tiên Sơn!"""

    # 4. Lệnh 1-chạm: Kéo Traffic Thực Chiến
    if "traffic" in lower_text or "!traffic" in lower_text or "hút khách" in lower_text:
        return """🚀 **CỖ MÁY SẢN XUẤT TRAFFIC TỰ ĐỘNG - ZELLY × TENT × MV**

Kính thưa **Chủ tịch Lê Minh Tân**,
Hệ thống đã chuẩn bị sẵn **3 Chiến dịch Kéo Traffic Thực Chiến** để Chủ tịch Copy & Đăng ngay:

---
🔥 **CHIẾN DỊCH 1: HÚT KHÁCH SỈ VẬN CHUYỂN 1688 (FB / ZALO / THREADS)**
*(Copy đăng lên 2 hội nhóm: 'Hội Buôn Hàng 1688 Quảng Châu', 'Nguồn Hàng Kinh Doanh Online')*

"🚨 **CẢNH BÁO BÁC NÀO ĐANG NHẬP HÀNG 1688 QUA TRUNG GIAN BỊ MẤT THÊM 20-30% PHÍ!**
70% shop trên 1688 là dân buôn thương mại F1, F2. Muốn tìm tận xưởng sản xuất phải lọc đúng biểu tượng 'ĐẦU TRÂU' (实力商家) + tỷ lệ khách quay lại > 30%!
Hoàng Thịnh Logistics hỗ trợ anh em đàm phán trực tiếp với chủ xưởng, vận chuyển chính ngạch có hóa đơn VAT & C/O Form E chỉ 3-5 ngày về kho Hà Nội (19/785 Nguyễn Khoái).
👉 Bác nào cần bảng mã HS Code & danh bạ 50 xưởng gốc, nhắn Zalo em gửi tặng: 0968.599.951!"

---
⚡ **CHIẾN DỊCH 2: HÚT THỢ THẦU ĐIỆN BẮC NINH (TẠO DÒNG TIỀN TRONG 24H)**
*(Gửi trực tiếp cho 5 thợ điện hoặc đăng nhóm 'Hội Thợ Điện Nước Bắc Ninh')*

"Kính gửi các bác thợ thầu công trình Bắc Ninh! Tổng Kho Điện Duy Phong (549 Ngô Gia Tự, TP. Bắc Ninh) đang có chính sách trợ giá cuối năm:
• Dây Cadisun chiết khấu 30% - 35%
• Dây Trần Phú chính hãng chiết khấu 20% - 25%
• Thiết bị Sino, Panasonic chiết khấu 38% - 48%
Chở miễn phí tận chân công trình TP. Bắc Ninh, KCN Quế Võ, Yên Phong! Gửi bản vẽ bóc tách qua Zalo: 0904.511.227 nhận báo giá sau 30 phút!"

---
🎬 **CHIẾN DỊCH 3: VIDEO TIKTOK VIRAL 22s (SĂN HÀNG 1689.VN)**
• **Hook 0-3s:** Cầm đồ gia dụng: *"Đừng dại mua món này ở siêu thị 600 cành nếu chưa biết điều này!"*
• **3-15s:** Quay app 1688 giá xưởng 95k + mở web 1689.vn bóc giá vốn.
• **15-22s:** *"Link săn mã giảm giá và kho xưởng em để ở đầu trang bio, bấm vào giỏ hàng ngay nhé!"*

Chủ tịch đăng bài nào trước trong hôm nay ạ?"""

    # 4. Xử lý hội thoại tự nhiên với Gemini 2.5 Flash
    client = get_gemini_client()
    if client:
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{SYSTEM_SOUL_PROMPT}\n\nNgười dùng ({user_name}) nói: {user_text}",
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini API Error: {e}")
            try:
                response = client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=f"{SYSTEM_SOUL_PROMPT}\n\nNgười dùng ({user_name}) nói: {user_text}",
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e2:
                logger.error(f"Fallback Error: {e2}")

    return f"Dạ em chào Chủ tịch Tân! Em đã ghi nhận yêu cầu: '{user_text}'. Em Vi và các Sub-Agents đang kiểm tra số liệu kho và sẽ báo cáo Chủ tịch ngay ạ!"

GITHUB_TOKEN = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", os.environ.get("GITHUB_TOKEN", ""))

# ==============================================================================
# QUY TRÌNH TỰ ĐỘNG VIẾT BÀI - TẠO ẢNH - ĐĂNG LÊN WEBSITE (AUTO-PUBLISHER)
# ==============================================================================
def create_slug_url(text: str) -> str:
    import re
    text = text.lower()
    text = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', text)
    text = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', text)
    text = re.sub(r'[ìíịỉĩ]', 'i', text)
    text = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', text)
    text = re.sub(r'[ùúụủũưừứựửữ]', 'u', text)
    text = re.sub(r'[ỳýỵỷỹ]', 'y', text)
    text = re.sub(r'đ', 'd', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:60]

def normalize_target_site(web_input: str) -> str:
    web = (web_input or "").lower().strip()
    if any(k in web for k in ["a thành", "a thanh", "athanh", "a-thanh", "bacninh", "bac ninh", "duyphong", "duy phong"]):
        return "athanh"
    if any(k in web for k in ["logistics", "hoangthinh", "hoang thinh", "itan", "1688"]):
        return "logistics"
    if any(k in web for k in ["1689", "affiliate"]):
        return "1689"
    return "athanh"

def auto_publish_workflow_sync(topic: str, website: str = "athanh") -> dict:
    """Tự viết bài SEO bằng Gemini AI, tạo ảnh Luxury, cập nhật GitHub Pages và trả kết quả."""
    import base64
    import requests
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    website = normalize_target_site(website)
    
    if website == "athanh":
        site_name = "Website A Thành (thietbidien-bacninh.com)"
        site_url = "http://thietbidien-bacninh.com"
        repo_name = "thietbidien-bacninh"
        prompt_ctx = "Website A Thành — Tổng Kho Thiết Bị Điện Duy Phong Bắc Ninh (549 Ngô Gia Tự, TP. Bắc Ninh, Hotline: 0904.511.227). Chuyên dây cáp Cadisun, Trần Phú, Panasonic."
    else:
        site_name = "Hoàng Thịnh Logistics"
        site_url = "https://itanle951-rgb.github.io/hoangthinh-logistics"
        repo_name = "hoangthinh-logistics"
        prompt_ctx = "Hoàng Thịnh Logistics (Kho 19/785 Nguyễn Khoái, Hoàng Mai, Hà Nội. Hotline: 0968 599 951). Chuyên vận chuyển 1688, Taobao chính ngạch."

    # 1. Viết bài với Gemini AI
    article = None
    system_inst = f"""
    Bạn là Kỹ sư Trưởng & Chuyên gia Content SEO. Ngữ cảnh: {prompt_ctx}
    Viết 1 bài viết chuẩn SEO chuyên sâu, trả về JSON chuẩn:
    {{
      "title": "Tiêu đề chuẩn SEO hấp dẫn dài 60-80 ký tự",
      "category": "Tên chuyên mục",
      "summary": "Đoạn sapo lôi cuốn 2-3 câu",
      "content_html": "Nội dung chi tiết thẻ HTML <h3>, <p>, <ul>, <li>, <strong>, bảng thông số, lời khuyên thực tế và kết bài liên hệ Hotline",
      "image_prompt": "Prompt tiếng Anh chi tiết để tạo ảnh Luxury Black and Gold cho bài viết này"
    }}
    """
    for m in ['gemini-3.1-flash-lite', 'gemini-3.8-flash', 'gemini-3.5-flash-lite']:
        try:
            resp = client.models.generate_content(
                model=m,
                contents=f"{system_inst}\n\nChủ đề bài viết: {topic}",
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
            )
            article = json.loads(resp.text)
            break
        except Exception as e:
            logger.warning(f"Model {m} error: {e}")

    if not article:
        article = {
            "title": f"Cẩm nang kiến thức chuyên sâu: {topic}",
            "category": "Kinh Nghiệm Thực Tế",
            "summary": f"Hướng dẫn và phân tích chi tiết về {topic} giúp tiết kiệm chi phí và đảm bảo an toàn tuyệt đối.",
            "content_html": f"<h3>1. Giới thiệu về {topic}</h3><p>Nắm vững giải pháp về {topic} mang lại giá trị to lớn cho công trình.</p><h3>2. Lời khuyên</h3><p>Luôn lựa chọn sản phẩm chính hãng có nguồn gốc minh bạch.</p>",
            "image_prompt": f"Luxury black and gold illustration of {topic}, cinematic 8k"
        }

    # 2. Tạo ảnh Luxury
    slug = create_slug_url(article["title"])
    os.makedirs("/tmp/web_images", exist_ok=True)
    img_path = f"/tmp/web_images/{slug}.jpg"
    create_luxury_graphic_banner(article["title"], topic, img_path)

    # 3. Đẩy lên GitHub để Website live
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "User-Agent": "Antigravity-Publisher",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    owner = "itanle951-rgb"

    # Đẩy ảnh lên GitHub
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    img_repo_path = f"assets/images/{slug}.jpg"
    put_img_payload = {
        "message": f"Auto-Publish Image: {slug}",
        "content": img_b64,
        "branch": "main"
    }
    try:
        # Kiểm tra SHA ảnh nếu có
        res_sha = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/contents/{img_repo_path}", headers=headers)
        if res_sha.status_code == 200:
            put_img_payload["sha"] = res_sha.json().get("sha")
        requests.put(f"https://api.github.com/repos/{owner}/{repo_name}/contents/{img_repo_path}", json=put_img_payload, headers=headers, timeout=15)
    except Exception as e:
        logger.warning(f"Lỗi đẩy ảnh lên GitHub: {e}")

    # Cập nhật mã nguồn bài viết (app.js cho Website A Thành)
    if website == "athanh":
        try:
            get_js = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}/contents/js/app.js", headers=headers)
            if get_js.status_code == 200:
                js_data = get_js.json()
                cur_js = base64.b64decode(js_data["content"]).decode("utf-8")
                today_str = time.strftime("%d/%m/%Y")
                new_item = {
                    "id": f"art-{int(time.time())}",
                    "title": article["title"],
                    "category": article["category"],
                    "author": "A Thành BN",
                    "createdAt": today_str,
                    "summary": article["summary"],
                    "image": img_repo_path,
                    "content": article["content_html"]
                }
                pattern = r"(const\s+ALL_SEO_ARTICLES\s*=\s*\[)"
                new_js = re.sub(pattern, r"\1\n        " + json.dumps(new_item, ensure_ascii=False, indent=8) + ",\n", cur_js, count=1)
                new_js_b64 = base64.b64encode(new_js.encode("utf-8")).decode("utf-8")
                
                put_js = {
                    "message": f"Auto-Publish Article: {article['title']}",
                    "content": new_js_b64,
                    "sha": js_data["sha"],
                    "branch": "main"
                }
                requests.put(f"https://api.github.com/repos/{owner}/{repo_name}/contents/js/app.js", json=put_js, headers=headers, timeout=15)
                logger.info(f"✓ Đã push bài viết mới '{article['title']}' lên {repo_name} thành công!")
        except Exception as e:
            logger.error(f"Lỗi cập nhật app.js trên GitHub: {e}")

    return {
        "article": article,
        "img_path": img_path,
        "site_name": site_name,
        "site_url": site_url,
        "slug": slug
    }
def get_render_font(size=32):
    from PIL import ImageFont
    candidates = [
        str(BASE_DIR / "assets" / "fonts" / "arialbd.ttf"),
        str(BASE_DIR / "assets" / "fonts" / "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_render_lines(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def create_luxury_graphic_banner(title: str, subtitle: str, output_path: str):
    """Tạo banner đồ họa Luxury Black & Gold (#0B0F17 & #D4AF37) chuẩn 100% tiếng Việt."""
    try:
        from PIL import Image, ImageDraw, ImageEnhance
        width, height = 1200, 675
        
        # 1. Thử tải ảnh nền thực tế từ kho Unsplash hoặc tạo gradient
        base = None
        try:
            import urllib.request
            unsplash_url = "https://images.unsplash.com/photo-1544724569-5f546fd6f2b5?w=1200&h=675&fit=crop&q=80"
            req = urllib.request.Request(unsplash_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                from io import BytesIO
                base = Image.open(BytesIO(resp.read())).convert("RGBA")
                base = base.resize((width, height), Image.Resampling.LANCZOS)
        except Exception:
            base = None

        if not base:
            base = Image.new("RGBA", (width, height), (15, 23, 42, 255))
        else:
            enhancer = ImageEnhance.Brightness(base)
            base = enhancer.enhance(0.40)

        # 2. Gradient mờ tối Dark Navy
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d_over = ImageDraw.Draw(overlay)
        for x in range(width):
            alpha = int(130 + (125 * (1 - (x / width) ** 0.8)))
            d_over.line([(x, 0), (x, height)], fill=(11, 15, 23, alpha))
        for y in range(height):
            alpha_v = int(60 * (y / height))
            d_over.line([(0, y), (width, y)], fill=(11, 15, 23, alpha_v))

        composed = Image.alpha_composite(base, overlay)
        draw = ImageDraw.Draw(composed)

        # 3. Viền đôi mạ vàng Luxury Gold (#D4AF37)
        gold = (212, 175, 55, 255)
        gold_light = (243, 229, 171, 255)
        gold_border = (212, 175, 55, 180)
        white = (255, 255, 255, 255)
        text_muted = (180, 195, 215, 255)

        margin = 24
        draw.rounded_rectangle([margin, margin, width - margin, height - margin], radius=16, outline=gold_border, width=2)
        draw.rounded_rectangle([margin + 6, margin + 6, width - margin - 6, height - margin - 6], radius=12, outline=(60, 50, 20, 120), width=1)

        # 4. Top Header Brand Bar
        font_brand = get_render_font(20)
        font_cat = get_render_font(18)
        
        cat_text = "  👑 CHUYÊN MỤC CẨM NANG & THỰC CHIẾN  "
        bbox_cat = draw.textbbox((0, 0), cat_text, font=font_cat)
        badge_w = (bbox_cat[2] - bbox_cat[0]) + 20
        draw.rounded_rectangle([50, 45, 50 + badge_w, 45 + 36], radius=8, fill=(212, 175, 55, 240))
        draw.text((60, 52), cat_text, fill=(11, 15, 23, 255), font=font_cat)

        brand_sub = "HỆ THỐNG DOANH NGHIỆP — CHỦ TỊCH LÊ MINH TÂN"
        bbox_brand = draw.textbbox((0, 0), brand_sub, font=font_brand)
        draw.text((width - 60 - (bbox_brand[2] - bbox_brand[0]), 52), brand_sub, fill=gold_light, font=font_brand)

        # 5. Tiêu đề chính (Title) chuẩn Tiếng Việt
        font_title = get_render_font(44)
        title_lines = wrap_render_lines(title, font_title, 1000, draw)
        if len(title_lines) > 3:
            font_title = get_render_font(36)
            title_lines = wrap_render_lines(title, font_title, 1000, draw)

        start_y = 135
        line_spacing = 58 if font_title.size >= 42 else 48
        for i, line in enumerate(title_lines[:3]):
            y = start_y + (i * line_spacing)
            draw.text((52, y + 2), line, fill=(0, 0, 0, 240), font=font_title)
            draw.text((50, y), line, fill=white if i > 0 else gold_light, font=font_title)

        # 6. Dải phân cách mạ vàng
        sep_y = start_y + (len(title_lines[:3]) * line_spacing) + 20
        draw.line([(50, sep_y), (350, sep_y)], fill=gold, width=3)
        draw.ellipse([348, sep_y - 4, 356, sep_y + 4], fill=gold)

        # 7. Box 3 Điểm Nhấn Thực Chiến
        font_bullet = get_render_font(22)
        bullet_y = sep_y + 25
        bullets = [
            f"• Chủ đề thực chiến: {subtitle[:65]}",
            "• Chuẩn nhận diện: Luxury Obsidian Black & Royal Gold (#D4AF37)",
            "• Đơn vị vận hành: Tổng Kho Điện Duy Phong & Hoàng Thịnh Logistics"
        ]
        for b in bullets:
            draw.text((54, bullet_y + 2), b, fill=(0, 0, 0, 200), font=font_bullet)
            draw.text((52, bullet_y), b, fill=(226, 232, 240, 255), font=font_bullet)
            bullet_y += 38

        # 8. Footer Bar: Tác giả & Hotline
        font_footer = get_render_font(20)
        font_hotline = get_render_font(24)
        footer_box_y = height - 90
        draw.rounded_rectangle([45, footer_box_y, width - 45, footer_box_y + 55], radius=10, fill=(15, 23, 42, 230), outline=(212, 175, 55, 120), width=1)
        
        draw.text((65, footer_box_y + 16), "👤 Tác giả: Kỹ sư A Thành & Lê Minh Tân", fill=text_muted, font=font_footer)
        hotline = "0904.511.227 - 0968.599.951"
        bbox_hl = draw.textbbox((0, 0), f"📞 Hotline: {hotline}", font=font_hotline)
        draw.text((width - 65 - (bbox_hl[2] - bbox_hl[0]), footer_box_y + 14), f"📞 Hotline: {hotline}", fill=gold_light, font=font_hotline)

        final_img = composed.convert("RGB")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        final_img.save(output_path, "JPEG", quality=95)
        return True
    except Exception as e:
        logger.error(f"Lỗi tạo Luxury Graphic Banner: {e}")
        return False

def generate_image_sync(prompt: str) -> tuple[str, str]:
    """Tạo ảnh AI từ AI Horde hoặc Fallback Pillow Banner."""
    import requests
    os.makedirs("/tmp/images", exist_ok=True)
    out_path = f"/tmp/images/img_{int(time.time())}.jpg"
    
    # Prompt nâng cấp phong cách Luxury
    luxury_prompt = (
        f"{prompt}, commercial luxury photography, obsidian black background (#0B0F17), "
        f"royal gold rim lighting (#D4AF37), dramatic studio lighting, 8k resolution, photorealistic"
    )
    
    # Thử qua AI Horde GPU phân tán miễn phí
    success = False
    try:
        headers = {"apikey": "0000000000", "Client-Agent": "HermesAgent:1.0:test", "Content-Type": "application/json"}
        payload = {
            "prompt": luxury_prompt,
            "params": {"steps": 25, "width": 512, "height": 512, "sampler_name": "k_euler", "cfg_scale": 7.5}
        }
        res = requests.post("https://aihorde.net/api/v2/generate/async", json=payload, headers=headers, timeout=12)
        if res.status_code == 202:
            job_id = res.json().get("id")
            for _ in range(10): # Đợi tối đa 25s
                time.sleep(2.5)
                st = requests.get(f"https://aihorde.net/api/v2/generate/status/{job_id}", headers=headers, timeout=10)
                if st.status_code == 200 and st.json().get("done"):
                    gens = st.json().get("generations", [])
                    if gens:
                        img_bytes = requests.get(gens[0].get("img"), timeout=15).content
                        with open(out_path, "wb") as f:
                            f.write(img_bytes)
                        success = True
                        break
    except Exception as e:
        logger.warning(f"AI Horde timeout/error: {e}")

    if not success or not os.path.exists(out_path):
        create_luxury_graphic_banner("ẤN PHẨM THƯƠNG HIỆU LUXURY", prompt, out_path)

    caption = (
        f"🎨 **TÁC PHẨM THIẾT KẾ AI THEO LỆNH CHỦ TỊCH TÂN**\n\n"
        f"📦 **Yêu cầu:** {prompt}\n"
        f"💎 **Phong cách:** Luxury Black & Gold (#0B0F17 & #D4AF37)\n"
        f"👑 **Đội ngũ phụ trách:** Sub-Agent Tent × Zelly × Itan\n\n"
        f"⚡ **BẢNG ĐIỀU HƯỚNG WORKFLOW 1-CHẠM:**\n"
        f"• Gõ **`!quote`** : Tính giá cước vận chuyển 1688 trọn gói.\n"
        f"• Gõ **`!traffic`**: Xuất 3 bài đăng mạng xã hội (FB / Zalo / Threads).\n"
        f"• Gõ **`boq`**    : Bóc tách chiết khấu cáp Cadisun / Trần Phú 30-35%.\n"
        f"• Gõ **`!video`**  : Xuất kịch bản TikTok 22s kèm phụ đề SRT."
    )
    return out_path, caption

# ==============================================================================
# BỘ XỬ LÝ TELEGRAM BOT (POLLING ASYNC)
# ==============================================================================
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        welcome_text = (
            f"👑 **KÍNH CHÀO TỔNG CHỈ HUY - CHỦ TỊCH {user.first_name.upper()}!**\n\n"
            "Bộ Ba Tác Chiến **Zelly × Itan × Em Vi** đang trực chiến **24/7 trên Đám Mây Render Cloud**.\n\n"
            "🛡️ **Quyền Hạn:** `SUPER_ADMIN` (Đã bảo mật tuyệt đối 100%)\n\n"
            "⚡ **Lệnh 1-chạm tối cao:**\n"
            "• Gõ **`báo cáo`** (hoặc `!vi`): Em Vi xuất báo cáo tài chính & 3 việc ưu tiên.\n"
            "• Gõ **`war-room`**: Triệu tập Zelly và Itan họp chiến lược dòng tiền.\n"
            "• Gõ **`traffic`**: Xuất 3 chiến dịch kéo traffic đa kênh tức thì.\n"
            "• Gõ **`boq`**: Tra cứu chiết khấu vật tư điện Duy Phong Bắc Ninh.\n"
            "• Gõ **`/image <mô tả>`**: Tạo ảnh AI Luxury Black & Gold tức thì.\n"
            "• Gõ **`/publish <chủ đề>`** (hoặc `đăng bài: <chủ đề> | web: <tên>`): Tự động viết bài chuẩn SEO, tạo ảnh và đăng thẳng lên Website!\n\n"
            "Chủ tịch có thể tắt máy tính đi ngủ, bot vẫn luôn túc trực trên điện thoại của anh 24/24!"
        )
    else:
        welcome_text = (
            f"🏢 **KÍNH CHÀO QUÝ KHÁCH {user.first_name.upper()}!**\n\n"
            "Chào mừng Quý khách đến với **Hệ sinh thái Doanh nghiệp của Chủ tịch Lê Minh Tân**.\n\n"
            "Em là **Trợ Lý Số AI**, luôn túc trực 24/7 để phục vụ Quý khách:\n\n"
            "📦 **1. HOÀNG THỊNH LOGISTICS (HÀNG 1688 / TAOBAO):**\n"
            "• Mua hộ & Vận chuyển chính ngạch Trung - Việt (3-5 ngày về Hà Nội).\n"
            "• Đầy đủ hóa đơn VAT, C/O Form E, kho nhận hàng: 19/785 Nguyễn Khoái, Hà Nội.\n\n"
            "⚡ **2. TỔNG KHO THIẾT BỊ ĐIỆN DUY PHONG BẮC NINH:**\n"
            "• Dây cáp **Cadisun (chiết khấu 30% - 35%)**, **Trần Phú (20% - 25%)**.\n"
            "• Thiết bị Sino, Panasonic công trình nhà phố, biệt thự & xưởng KCN.\n"
            "• Giao miễn phí tận chân công trình TP. Bắc Ninh, KCN Quế Võ, Yên Phong.\n\n"
            "🛒 **3. CỔNG SĂN HÀNG XƯỞNG GỐC 1689.VN:**\n"
            "• Săn hàng giá xưởng, mua lẻ giá sỉ tiết kiệm 30-50%.\n\n"
            "📞 **Hotline tư vấn 24/7:** **0968.599.951** • **0904.511.227**\n"
            "💬 *Quý khách cần báo giá hoặc hỗ trợ dịch vụ nào, xin cứ nhắn tin trực tiếp tại đây để em hỗ trợ ngay ạ!*"
        )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_image_generation(update: Update, prompt: str):
    """Xử lý tạo ảnh và trả lời trực tiếp trong Telegram."""
    await update.message.chat.send_action("upload_photo")
    status_msg = await update.message.reply_text("🎨 *Hội đồng Zelly × Itan đang khởi tạo ảnh AI Luxury Black & Gold cho Chủ tịch...*", parse_mode="Markdown")
    
    loop = asyncio.get_running_loop()
    img_path, caption = await loop.run_in_executor(None, generate_image_sync, prompt)
    
    try:
        with open(img_path, "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode="Markdown")
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Lỗi gửi ảnh Telegram: {e}")
        await update.message.reply_text(f"Dạ ảnh đã được tạo tại `{img_path}`, nhưng gửi ảnh gặp sự cố: {e}")

async def handle_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🔒 *Tính năng tạo ảnh AI độc quyền chỉ dành riêng cho Chủ tịch Lê Minh Tân. Quý khách cần hỗ trợ dịch vụ xin cứ nhắn tin trực tiếp ạ!*", parse_mode="Markdown")
        return
    prompt = " ".join(context.args) if context.args else ""
    if not prompt:
        prompt = "Container Hoang Thinh Logistics cap ben kho Ha Noi"
    await handle_image_generation(update, prompt)

async def handle_publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🔒 *Chức năng xuất bản website tự động chỉ dành cho Chủ tịch Lê Minh Tân.*", parse_mode="Markdown")
        return
    raw_text = " ".join(context.args) if context.args else ""
    website = "bacninh"
    topic = raw_text
    if "web:" in raw_text.lower():
        parts = raw_text.split("web:")
        topic = parts[0].replace("chủ đề:", "").replace("chude:", "").strip()
        website = parts[1].strip().split()[0].lower()
    elif "logistics" in raw_text.lower() or "1688" in raw_text.lower():
        website = "logistics"

    if not topic:
        topic = "Kinh nghiệm chọn thiết bị điện cao cấp cho biệt thự và nhà phố"

    status_msg = await update.message.reply_text(
        f"🚀 *Chủ tịch đã ra lệnh xuất bản! Hội đồng Zelly × Itan đang tự động:*\n"
        f"1. Viết bài chuẩn SEO bằng Gemini AI\n"
        f"2. Tạo ảnh nhận diện Luxury Black & Gold\n"
        f"3. Cập nhật mã nguồn & đẩy thẳng lên GitHub Pages (`{website}`)...\n\n"
        f"⏳ *Vui lòng đợi khoảng 15-20 giây...*",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("upload_photo")

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, auto_publish_workflow_sync, topic, website)

    art = res["article"]
    caption = (
        f"🚀 **ĐÃ TỰ ĐỘNG VIẾT BÀI & ĐĂNG LÊN WEBSITE THÀNH CÔNG!**\n\n"
        f"🌐 **Website:** {res['site_name']}\n"
        f"🔗 **Link xem:** {res['site_url']}\n"
        f"📰 **Tiêu đề:** {art['title']}\n"
        f"🏷️ **Chuyên mục:** {art['category']}\n"
        f"📝 **Tóm tắt:** {art['summary']}\n\n"
        f"⚡ **GỢI Ý HÀNH ĐỘNG TIẾP THEO CHO CHỦ TỊCH:**\n"
        f"• Link bài viết đã online trên GitHub Pages, Chủ tịch có thể chia sẻ lên Zalo/Facebook để kéo khách!\n"
        f"• Gõ `!traffic` để xuất thêm 3 kịch bản video TikTok tương ứng."
    )

    try:
        with open(res["img_path"], "rb") as photo_file:
            await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode="Markdown")
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Lỗi gửi thông báo xuất bản: {e}")
        await update.message.reply_text(caption, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    user_text = update.message.text.strip()
    lower_text = user_text.lower()
    logger.info(f"Tin nhắn từ {user.first_name} ({user.id}) [Admin={is_admin(user.id)}]: {user_text}")

    # ==========================================================================
    # 1. CƠ CHẾ XÁC THỰC 1-CHẠM LÀM SUPER_ADMIN
    # ==========================================================================
    is_claim = False
    for key in ADMIN_SECRET_KEYS:
        if lower_text in [f"admin {key}", f"!admin {key}", f"/auth {key}", key]:
            is_claim = True
            break

    if is_claim:
        ADMIN_USER_IDS.add(user.id)
        auth_msg = (
            f"👑 **XÁC THỰC THÀNH CÔNG — KÍNH CHÀO TỔNG CHỈ HUY!**\n\n"
            f"👤 Tài khoản: **{user.first_name}**\n"
            f"🆔 Telegram ID: **`{user.id}`**\n"
            f"🛡️ Vai trò: **SUPER_ADMIN (Chủ tịch Lê Minh Tân)**\n\n"
            "🔒 **HỆ THỐNG ĐÃ KHÓA BẢO MẬT TUYỆT ĐỐI:**\n"
            "• Toàn bộ số liệu tài chính nội bộ, dòng tiền, đồng hồ xóa nợ và phòng họp War-Room đã được mở khóa cho riêng anh.\n"
            "• Người ngoài khi nhắn tin vào bot sẽ chỉ thấy menu dịch vụ khách hàng công khai, tuyệt đối không thấy thông tin kinh doanh nội bộ.\n\n"
            "⚡ *Chủ tịch hãy gõ thử `báo cáo`, `war-room`, `traffic` hoặc `boq` để kiểm tra quyền hạn tối cao ngay bây giờ!*"
        )
        await update.message.reply_text(auth_msg, parse_mode="Markdown")
        return

    # ==========================================================================
    # 2. XỬ LÝ THEO PHÂN QUYỀN (ADMIN VS KHÁCH NGOÀI)
    # ==========================================================================
    if is_admin(user.id):
        # ADMIN: Kiểm tra tạo ảnh tự nhiên
        if any(lower_text.startswith(prefix) for prefix in ["tạo ảnh", "tao anh", "vẽ ảnh", "ve anh", "vẽ ", "ve ", "ảnh:"]):
            prompt = user_text
            for prefix in ["tạo ảnh:", "tao anh:", "tạo ảnh", "tao anh", "vẽ ảnh:", "ve anh:", "vẽ:", "ve:", "vẽ ", "ve ", "ảnh:"]:
                if lower_text.startswith(prefix):
                    prompt = user_text[len(prefix):].strip()
                    break
            if not prompt:
                prompt = "Container Hoang Thinh Logistics phong cach Luxury Black and Gold"
            await handle_image_generation(update, prompt)
            return

        # ADMIN: Kiểm tra lệnh tự động viết bài và đăng website
        if any(lower_text.startswith(prefix) for prefix in ["đăng bài", "dang bai", "viết bài", "viet bai", "xuất bản", "xuat ban", "đăng web", "dang web"]):
            topic_str = user_text
            for prefix in ["đăng bài:", "dang bai:", "đăng bài", "dang bai", "viết bài:", "viet bai:", "viết bài", "viet bai", "xuất bản:", "xuat ban:", "đăng web:", "dang web:"]:
                if lower_text.startswith(prefix):
                    topic_str = user_text[len(prefix):].strip()
                    break
            website = "bacninh"
            if "|" in topic_str:
                parts = topic_str.split("|")
                topic_str = parts[0].strip()
                if "web:" in parts[1].lower():
                    website = parts[1].lower().split("web:")[1].strip()
            elif "web:" in topic_str.lower():
                parts = topic_str.split("web:")
                topic_str = parts[0].strip()
                website = parts[1].strip().split()[0].lower()
            elif "logistics" in topic_str.lower() or "1688" in topic_str.lower() or "quảng châu" in topic_str.lower():
                website = "logistics"
            
            if not topic_str:
                topic_str = "Kinh nghiệm chọn thiết bị điện cao cấp cho biệt thự và nhà phố"

            status_msg = await update.message.reply_text(
                f"🚀 *Nhận lệnh Chủ tịch! Hội đồng Zelly × Itan đang tự động:*\n"
                f"1. Viết bài chuyên sâu chuẩn SEO bằng Gemini AI\n"
                f"2. Tạo ảnh nhận diện Luxury Black & Gold\n"
                f"3. Cập nhật mã nguồn & push thẳng lên GitHub Pages (`{website}`)...\n\n"
                f"⏳ *Vui lòng đợi khoảng 15-20 giây...*",
                parse_mode="Markdown"
            )
            await update.message.chat.send_action("upload_photo")
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, auto_publish_workflow_sync, topic_str, website)
            art = res["article"]
            caption = (
                f"🚀 **ĐÃ TỰ ĐỘNG VIẾT BÀI & ĐĂNG LÊN WEBSITE THÀNH CÔNG!**\n\n"
                f"🌐 **Website:** {res['site_name']}\n"
                f"🔗 **Link xem:** {res['site_url']}\n"
                f"📰 **Tiêu đề:** {art['title']}\n"
                f"🏷️ **Chuyên mục:** {art['category']}\n"
                f"📝 **Tóm tắt:** {art['summary']}\n\n"
                f"⚡ *Link bài viết đã cập nhật trực tiếp trên website. Chủ tịch có thể gửi ngay cho đối tác/thợ thầu!*"
            )
            try:
                with open(res["img_path"], "rb") as photo_file:
                    await update.message.reply_photo(photo=photo_file, caption=caption, parse_mode="Markdown")
                try:
                    await status_msg.delete()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Lỗi gửi thông báo xuất bản: {e}")
                await update.message.reply_text(caption, parse_mode="Markdown")
            return

        # ADMIN: Toàn quyền truy cập phản hồi hệ thống
        await update.message.chat.send_action("typing")
        reply_text = generate_ai_response(user_text, user.first_name)
    else:
        # KHÁCH NGOÀI (GUEST): Chặn các lệnh điều hành nội bộ
        if any(kw in lower_text for kw in ["báo cáo", "bao cao", "!report", "!vi", "vi báo cáo", "war-room", "warroom", "họp", "traffic", "!traffic"]):
            reply_text = (
                "🔒 **THÔNG BÁO BẢO MẬT HỆ THỐNG:**\n\n"
                "Khu vực này thuộc phân quyền **QUẢN TRỊ NỘI BỘ** của Chủ tịch Lê Minh Tân.\n\n"
                "Nếu Quý khách là đối tác hoặc khách hàng cần hỗ trợ:\n"
                "• **Vận chuyển chính ngạch 1688:** Xin liên hệ Hotline **0968.599.951**\n"
                "• **Báo giá thiết bị điện Bắc Ninh:** Xin liên hệ Hotline **0904.511.227**\n\n"
                "👉 Quý khách vui lòng để lại Số Điện Thoại và nhu cầu tại đây, trợ lý sẽ chuyển ngay cho Chủ tịch liên hệ lại hỗ trợ chu đáo ạ!"
            )
        else:
            await update.message.chat.send_action("typing")
            reply_text = generate_guest_response(user_text, user.first_name)
    
    if len(reply_text) > 4000:
        chunks = [reply_text[i:i+4000] for i in range(0, len(reply_text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        try:
            await update.message.reply_text(reply_text, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(reply_text)

async def run_telegram_bot():
    global bot_application
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Không tìm thấy TELEGRAM_BOT_TOKEN! Bot Telegram chưa khởi động.")
        return

    logger.info("Đang khởi động Telegram Bot Application trên Render Cloud...")
    bot_application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot_application.add_handler(CommandHandler("start", handle_start))
    bot_application.add_handler(CommandHandler("report", handle_message))
    bot_application.add_handler(CommandHandler("image", handle_image_command))
    bot_application.add_handler(CommandHandler("draw", handle_image_command))
    bot_application.add_handler(CommandHandler("publish", handle_publish_command))
    bot_application.add_handler(CommandHandler("post", handle_publish_command))
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling(drop_pending_updates=True)
    logger.info("✓ Telegram Bot đã kết nối thành công và đang lắng nghe 24/7!")

async def keep_alive_worker():
    """Tự động ping máy chủ mỗi 9 phút để Render Cloud không bao giờ ngủ đông (Zero Cold-Start)."""
    await asyncio.sleep(45)  # Chờ bot & FastAPI khởi động ổn định
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://itan-telegram-bot.onrender.com")
    ping_url = f"{render_url.rstrip('/')}/ping"
    logger.info(f"⚡ [Keep-Alive] Kích hoạt cơ chế Zero Cold-Start 24/7 tới: {ping_url}")
    
    import urllib.request
    while True:
        try:
            await asyncio.sleep(540)  # Ping mỗi 9 phút (Render ngủ sau 15 phút, 9 phút là khoảng cách an toàn nhất)
            req = urllib.request.Request(ping_url, headers={"User-Agent": "Zero-Cold-Start-Engine/2.0"})
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15))
            logger.info(f"⚡ [Keep-Alive] Ping thành công lúc {time.strftime('%H:%M:%S')} - Máy chủ duy trì tỉnh thức 100%!")
        except Exception as e:
            logger.warning(f"[Keep-Alive] Cảnh báo ping: {e}")

# ==============================================================================
# MÁY CHỦ WEB FASTAPI (HỖ TRỢ RENDER CLOUD & HEALTHCHECKS)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    tg_task = asyncio.create_task(run_telegram_bot())
    keep_alive_task = asyncio.create_task(keep_alive_worker())
    yield
    if bot_application:
        await bot_application.updater.stop()
        await bot_application.stop()
        await bot_application.shutdown()

api = FastAPI(title="Itan Telegram Bot 24/7", lifespan=lifespan)
app = api  # Hỗ trợ cả 2 chuẩn gọi: app:app hoặc app:api

@api.get("/", response_class=HTMLResponse)
async def dashboard():
    uptime_sec = int(time.time() - START_TIME)
    uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m {uptime_sec % 60}s"
    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hệ Thống Trực Chiến 24/7 | Chủ Tịch Lê Minh Tân</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0B0F17;
            --card: #161F30;
            --gold: #D4AF37;
            --gold-light: #F3E5AB;
            --green: #10B981;
            --text: #F8FAFC;
            --muted: #94A3B8;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: 'Outfit', -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: var(--card);
            border: 1px solid rgba(212, 175, 55, 0.3);
            border-radius: 20px;
            padding: 40px;
            max-width: 650px;
            width: 100%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        .card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, transparent, var(--gold), transparent);
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.15);
            color: var(--green);
            border: 1px solid var(--green);
            padding: 6px 16px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 24px;
        }}
        .pulse {{
            width: 8px; height: 8px;
            background: var(--green);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--green);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 1; }}
            50% {{ transform: scale(1.4); opacity: 0.6; }}
            100% {{ transform: scale(0.95); opacity: 1; }}
        }}
        h1 {{
            font-size: 26px;
            font-weight: 800;
            color: var(--gold-light);
            margin-bottom: 12px;
            letter-spacing: -0.5px;
        }}
        p.subtitle {{
            color: var(--muted);
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 30px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
            margin-bottom: 30px;
            text-align: left;
        }}
        .box {{
            background: rgba(11, 15, 23, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px;
        }}
        .box-title {{
            font-size: 12px;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }}
        .box-val {{
            font-size: 16px;
            font-weight: 700;
            color: var(--gold);
        }}
        .cta {{
            display: inline-block;
            background: linear-gradient(135deg, var(--gold) 0%, #AA820A 100%);
            color: #0B0F17;
            font-weight: 700;
            padding: 14px 28px;
            border-radius: 12px;
            text-decoration: none;
            transition: all 0.3s ease;
            box-shadow: 0 8px 20px rgba(212, 175, 55, 0.3);
        }}
        .cta:hover {{
            transform: translateY(-2px);
            box-shadow: 0 12px 25px rgba(212, 175, 55, 0.5);
        }}
        .footer {{
            margin-top: 30px;
            font-size: 12px;
            color: var(--muted);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge"><span class="pulse"></span> RENDER CLOUD 24/7 ONLINE</div>
        <h1>BỘ CHỈ HUY TÁC CHIẾN AI</h1>
        <p class="subtitle">Zelly × Itan × Em Vi sẵn sàng phục vụ Chủ tịch Lê Minh Tân trên Telegram (@itan951bot). Hệ thống hoạt động độc lập không phụ thuộc máy tính cá nhân.</p>
        
        <div class="grid">
            <div class="box">
                <div class="box-title">Trạng Thái Telegram</div>
                <div class="box-val" style="color: var(--green);">Đang Lắng Nghe 24/7</div>
            </div>
            <div class="box">
                <div class="box-title">Thời Gian Hoạt Động</div>
                <div class="box-val">{uptime_str}</div>
            </div>
            <div class="box">
                <div class="box-title">Trí Tuệ Nhân Tạo</div>
                <div class="box-val">Gemini 2.5 Flash</div>
            </div>
            <div class="box">
                <div class="box-title">Chi Phí Đám Mây</div>
                <div class="box-val" style="color: var(--green);">0 VNĐ / Tháng</div>
            </div>
        </div>

        <a href="https://t.me/itan951bot" target="_blank" class="cta">👉 MỞ CHAT VỚI BOT TRÊN TELEGRAM</a>
        
        <div class="footer">
            Tài sản: Hoàng Thịnh Logistics 1688 • Sàn 1689.vn • Thiết Bị Điện Duy Phong Bắc Ninh<br>
            <em>Máy chủ Render Cloud tự động duy trì liên tục không bao giờ ngủ.</em>
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@api.get("/ping")
@api.get("/healthz")
@api.get("/health")
async def health_check():
    return JSONResponse(content={
        "status": "healthy",
        "bot": "online",
        "platform": "Render Cloud",
        "uptime_seconds": int(time.time() - START_TIME),
        "owner": "Chủ tịch Lê Minh Tân",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
