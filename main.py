import io
import os
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageOps, ImageDraw, ImageEnhance
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- DUMMY WEB SERVER FOR RENDER FREE TIER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# Background thread me web server chalao
threading.Thread(target=run_dummy_server, daemon=True).start()
# ---------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Logos URLs
TOP_LOGO_URL = os.getenv(
    "TOP_LOGO_URL", 
    "https://cdn5.telesco.pe/file/aSf192hYDvLjeIu3QeKrEm5d5xwzUYN5wKLLNfbvOpuz6PKzQPyZ4up71rfuxRSwujzDh-AsMI4xOSplp2HjZ7lsn9-s4L-99jJG7VlKtqcG_62mytf04QZet_QoVVWlxYscNDhofqiPec2HCXUsc7DSV0c8BBLA2muRkN6IGhA9XZhjrYJqLGbLH9HFaQwImozgwXi-lBD_89f8XoiqIMS9KZaW8udXb-aEPaBgFk_sRHPr_joYXxJnXlo1pJSV8dAQuEzoxfBTR1eppST0l-BpNTDeJaPyWslYguzSIC3rr5ePrqlQ3Yldmkc0uXQhe_68AlZ6Jzdwfku0UTrbZw.jpg"
)

MIDDLE_LOGO_URL = os.getenv(
    "MIDDLE_LOGO_URL",
    "https://chatgpt.com/backend-api/estuary/content?id=file_00000000475082079d69d65adda877c4&ts=495774&p=fs&cid=1&sig=1f1773a0b2c08ce58a3335c60a828e5ee2affb98174141e679314ea8b6ff2296&v=0"
)

# Caching for faster performance
CACHED_TOP_LOGO = None
CACHED_MIDDLE_LOGO = None

def get_circular_logo(url: str) -> Image.Image:
    """Logo URL se download karke circular transparent PNG banata hai"""
    response = requests.get(url, timeout=10)
    logo_img = Image.open(io.BytesIO(response.content)).convert("RGBA")
    
    size = (min(logo_img.size), min(logo_img.size))
    logo_img = logo_img.resize(size, Image.Resampling.LANCZOS)
    
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    
    output = ImageOps.fit(logo_img, size, centering=(0.5, 0.5))
    output.putalpha(mask)
    return output

def get_top_logo() -> Image.Image:
    global CACHED_TOP_LOGO
    if CACHED_TOP_LOGO is None:
        CACHED_TOP_LOGO = get_circular_logo(TOP_LOGO_URL)
    return CACHED_TOP_LOGO.copy()

def get_middle_logo() -> Image.Image:
    global CACHED_MIDDLE_LOGO
    if CACHED_MIDDLE_LOGO is None:
        CACHED_MIDDLE_LOGO = get_circular_logo(MIDDLE_LOGO_URL)
    return CACHED_MIDDLE_LOGO.copy()

def add_watermarks(base_image_bytes: bytes) -> io.BytesIO:
    base_img = Image.open(io.BytesIO(base_image_bytes)).convert("RGBA")
    width, height = base_img.size

    # -------------------------------------------------------------
    # 1. TOP-LEFT LOGO
    # -------------------------------------------------------------
    top_logo = get_top_logo()
    top_w = int(width * 0.12)  # Base image ka 12% width
    top_logo = top_logo.resize((top_w, top_w), Image.Resampling.LANCZOS)
    
    margin = int(width * 0.03)
    base_img.paste(top_logo, (margin, margin), top_logo)

    # -------------------------------------------------------------
    # 2. MIDDLE LOGO (50% OPACITY)
    # -------------------------------------------------------------
    mid_logo = get_middle_logo()
    mid_w = int(width * 0.35)  # Center logo width = 35% of image width
    mid_logo = mid_logo.resize((mid_w, mid_w), Image.Resampling.LANCZOS)

    # Opacity 50% karne ke liye
    alpha = mid_logo.split()[3]
    alpha = ImageEnhance.Brightness(alpha).enhance(0.50)  # 50% opacity
    mid_logo.putalpha(alpha)

    # Center Position Calculate Karein
    mid_x = (width - mid_w) // 2
    mid_y = (height - mid_w) // 2
    
    base_img.paste(mid_logo, (mid_x, mid_y), mid_logo)

    # -------------------------------------------------------------
    # Output Buffer Save
    # -------------------------------------------------------------
    output_io = io.BytesIO()
    base_img.convert("RGB").save(output_io, format="JPEG", quality=95)
    output_io.seek(0)
    
    return output_io

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Mujhe koi bhi product image bhejiyen, main Top-Left aur Center me logo add karke bhej dunga."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Processing Image...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        processed_image = add_watermarks(image_bytes)

        await update.message.reply_photo(photo=processed_image)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("🤖 Bot Active hai... Telegram par photo bhej kar check karein!")
    app.run_polling()

if __name__ == "__main__":
    main()
