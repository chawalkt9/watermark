import io
import os
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageOps, ImageDraw
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
LOGO_URL = os.getenv(
    "LOGO_URL", 
    "https://yt3.googleusercontent.com/LSfY1cV1wEWgXQOp3IMnKBVXo4Akr-FrNUqPa-RDo5Ls-o4YW0yqn_-ZHZzo40j8irSyLAc4=s160-c-k-c0x00ffffff-no-rj"
)

CACHED_LOGO = None

def get_logo_image() -> Image.Image:
    global CACHED_LOGO
    if CACHED_LOGO is not None:
        return CACHED_LOGO.copy()

    response = requests.get(LOGO_URL, timeout=10)
    logo_img = Image.open(io.BytesIO(response.content)).convert("RGBA")
    
    size = (min(logo_img.size), min(logo_img.size))
    logo_img = logo_img.resize(size, Image.Resampling.LANCZOS)
    
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    
    output = ImageOps.fit(logo_img, size, centering=(0.5, 0.5))
    output.putalpha(mask)
    
    CACHED_LOGO = output
    return CACHED_LOGO.copy()

def add_logo_watermark(base_image_bytes: bytes) -> io.BytesIO:
    base_img = Image.open(io.BytesIO(base_image_bytes)).convert("RGBA")
    width, height = base_img.size

    logo = get_logo_image()

    logo_w = int(width * 0.12)
    logo = logo.resize((logo_w, logo_w), Image.Resampling.LANCZOS)

    margin = int(width * 0.03)
    position = (margin, margin)

    base_img.paste(logo, position, logo)

    output_io = io.BytesIO()
    base_img.convert("RGB").save(output_io, format="JPEG", quality=95)
    output_io.seek(0)
    
    return output_io

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Mujhe koi bhi product image bhejiyen, main Top-Left corner me logo add karke bhej dunga."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Processing Image...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        processed_image = add_logo_watermark(image_bytes)

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
