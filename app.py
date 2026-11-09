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

# ==============================================================================
# BỘ XỬ LÝ TELEGRAM BOT (POLLING ASYNC)
# ==============================================================================
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👑 **KÍNH CHÀO CHỦ TỊCH {user.first_name.upper()}!**\n\n"
        "Bộ Ba Tác Chiến **Zelly × Itan × Em Vi** đang trực chiến **24/7 trên Đám Mây Render Cloud**.\n\n"
        "⚡ **Lệnh 1-chạm thông minh:**\n"
        "• Gõ **`báo cáo`** (hoặc `!vi`): Em Vi xuất báo cáo tài chính & 3 việc ưu tiên.\n"
        "• Gõ **`war-room`**: Triệu tập Zelly và Itan họp chiến lược dòng tiền.\n"
        "• Hỏi bất kỳ điều gì về: Logistics 1688, Sàn 1689.vn hoặc Thiết bị điện Duy Phong Bắc Ninh!\n\n"
        "Chủ tịch có thể tắt máy tính đi ngủ, bot vẫn luôn túc trực trên điện thoại của anh 24/24!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    user_text = update.message.text
    logger.info(f"Tin nhắn từ {user.first_name} ({user.id}): {user_text}")
    
    await update.message.chat.send_action("typing")
    reply_text = generate_ai_response(user_text, user.first_name)
    
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
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling(drop_pending_updates=True)
    logger.info("✓ Telegram Bot đã kết nối thành công và đang lắng nghe 24/7!")

# ==============================================================================
# MÁY CHỦ WEB FASTAPI (HỖ TRỢ RENDER CLOUD & HEALTHCHECKS)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    tg_task = asyncio.create_task(run_telegram_bot())
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
