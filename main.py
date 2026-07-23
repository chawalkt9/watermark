import io
import os
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter
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

# Logo URL
TOP_LOGO_URL = os.getenv(
    "TOP_LOGO_URL", 
    "https://cdn5.telesco.pe/file/aSf192hYDvLjeIu3QeKrEm5d5xwzUYN5wKLLNfbvOpuz6PKzQPyZ4up71rfuxRSwujzDh-AsMI4xOSplp2HjZ7lsn9-s4L-99jJG7VlKtqcG_62mytf04QZet_QoVVWlxYscNDhofqiPec2HCXUsc7DSV0c8BBLA2muRkN6IGhA9XZhjrYJqLGbLH9HFaQwImozgwXi-lBD_89f8XoiqIMS9KZaW8udXb-aEPaBgFk_sRHPr_joYXxJnXlo1pJSV8dAQuEzoxfBTR1eppST0l-BpNTDeJaPyWslYguzSIC3rr5ePrqlQ3Yldmkc0uXQhe_68AlZ6Jzdwfku0UTrbZw.jpg"
)

# Caching for faster performance
CACHED_TOP_LOGO = None

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

def add_watermarks(base_image_bytes: bytes) -> io.BytesIO:
    base_img = Image.open(io.BytesIO(base_image_bytes)).convert("RGBA")
    width, height = base_img.size

    # -------------------------------------------------------------
    # 1. TOP-LEFT LOGO WITH BLACK BORDER & DROP SHADOW
    # -------------------------------------------------------------
    top_logo = get_top_logo()
    top_w = int(width * 0.12)  # Base image ka 12% width
    top_logo = top_logo.resize((top_w, top_w), Image.Resampling.LANCZOS)
    
    # Outer Canvas Canvas banayenge Shadow aur Border accommodate karne ke liye
    padding = int(top_w * 0.2)
    canvas_size = top_w + (padding * 2)
    logo_canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

    # Shadow layer banayein (Soft dark shadow offsetted to bottom-right)
    shadow_offset = (int(top_w * 0.04), int(top_w * 0.04))
    shadow_mask = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_mask)
    
    # Shadow circle draw
    shadow_draw.ellipse(
        [
            padding + shadow_offset[0], 
            padding + shadow_offset[1], 
            padding + top_w + shadow_offset[0], 
            padding + top_w + shadow_offset[1]
        ], 
        fill=(0, 0, 0, 160)
    )
    shadow = shadow_mask.filter(ImageFilter.GaussianBlur(radius=int(top_w * 0.05)))
    logo_canvas.paste(shadow, (0, 0), shadow)

    # Black Border Circle Draw Karein (3px thick outline)
    border_draw = ImageDraw.Draw(logo_canvas)
    border_thickness = max(2, int(top_w * 0.03))
    border_rect = [
        padding - border_thickness, 
        padding - border_thickness, 
        padding + top_w + border_thickness, 
        padding + top_w + border_thickness
    ]
    border_draw.ellipse(border_rect, fill=(0, 0, 0, 255))

    # Center Logo Paste Karein
    logo_canvas.paste(top_logo, (padding, padding), top_logo)

    # Base Image par apply karein
    margin = int(width * 0.03) - padding
    base_img.paste(logo_canvas, (margin, margin), logo_canvas)

    # -------------------------------------------------------------
    # 2. BOTTOM LOW OPACITY BLACK STRIP WITH TEXT
    # -------------------------------------------------------------
    strip_height = int(height * 0.08)  # Strip height (Image height ka 8%)
    
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Black banner (Alpha: 200)
    draw.rectangle(
        [(0, height - strip_height), (width, height)],
        fill=(0, 0, 0, 200)
    )

    # Text Settings
    text = "Join @kt_deals"
    font_size = max(14, int(strip_height * 0.45))
    
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    # Center text alignment
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    text_x = (width - text_w) // 2
    text_y = (height - strip_height) + (strip_height - text_h) // 2 - bbox[1]

    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    # Base Image ke saath Combine karein
    base_img = Image.alpha_composite(base_img, overlay)

    # -------------------------------------------------------------
    # Output Buffer Save
    # -------------------------------------------------------------
    output_io = io.BytesIO()
    base_img.convert("RGB").save(output_io, format="JPEG", quality=95)
    output_io.seek(0)
    
    return output_io

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Mujhe koi bhi product image bhejiyen, main Top-Left logo aur Bottom me banner add karke bhej dunga."
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
