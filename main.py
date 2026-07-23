import io
import os
import re
import requests
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image, ImageOps, ImageDraw, ImageFont
from telegram import Update
from telegram.constants import ParseMode
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

threading.Thread(target=run_dummy_server, daemon=True).start()
# ---------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Target Channels list
TARGET_CHANNELS = [
    -1002020215978,  # c1
    -1002487831408,  # c2
    -1002456123241,  # c3
    -1002362149730,  # c4
    -1003597769059   # c5
]

TOP_LOGO_URL = os.getenv(
    "TOP_LOGO_URL", 
    "https://cdn5.telesco.pe/file/aSf192hYDvLjeIu3QeKrEm5d5xwzUYN5wKLLNfbvOpuz6PKzQPyZ4up71rfuxRSwujzDh-AsMI4xOSplp2HjZ7lsn9-s4L-99jJG7VlKtqcG_62mytf04QZet_QoVVWlxYscNDhofqiPec2HCXUsc7DSV0c8BBLA2muRkN6IGhA9XZhjrYJqLGbLH9HFaQwImozgwXi-lBD_89f8XoiqIMS9KZaW8udXb-aEPaBgFk_sRHPr_joYXxJnXlo1pJSV8dAQuEzoxfBTR1eppST0l-BpNTDeJaPyWslYguzSIC3rr5ePrqlQ3Yldmkc0uXQhe_68AlZ6Jzdwfku0UTrbZw.jpg"
)

CACHED_TOP_LOGO = None

def get_circular_logo(url: str) -> Image.Image:
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

    # 1. TOP-LEFT LOGO
    top_logo = get_top_logo()
    top_w = int(width * 0.12)
    top_logo = top_logo.resize((top_w, top_w), Image.Resampling.LANCZOS)
    margin = int(width * 0.03)
    base_img.paste(top_logo, (margin, margin), top_logo)

    # 2. BOTTOM LOW OPACITY STRIP WITH LARGER TEXT
    # Strip ki height ko aur badhaya gaya hai bade text ke liye
    strip_height = int(height * 0.15) 
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    draw.rectangle(
        [(0, height - strip_height), (width, height)],
        fill=(0, 0, 0, 200)
    )

    text = "Join @kt_deals"
    # Text size aur bada kar diya gaya hai (ratio 0.75)
    font_size = max(48, int(strip_height * 0.75)) 
    
    try:
        # Aap chahein toh bolder font use kar sakte hain
        font = ImageFont.truetype("arial.ttf", font_size) 
    except IOError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    text_x = (width - text_w) // 2
    text_y = (height - strip_height) + (strip_height - text_h) // 2 - bbox[1]

    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    base_img = Image.alpha_composite(base_img, overlay)

    output_io = io.BytesIO()
    base_img.convert("RGB").save(output_io, format="JPEG", quality=95)
    output_io.seek(0)
    
    return output_io

def process_caption(caption: str) -> str:
    if not caption:
        return ""
    return re.sub(r'(@\s*\d+)', r'**\1**', caption)

async def send_to_single_channel(context, channel_id, image_bytes, final_caption, orig_caption, entities):
    try:
        photo_stream = io.BytesIO(image_bytes)
        
        if final_caption != orig_caption:
            await context.bot.send_photo(
                chat_id=channel_id,
                photo=photo_stream,
                caption=final_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await context.bot.send_photo(
                chat_id=channel_id,
                photo=photo_stream,
                caption=orig_caption,
                caption_entities=entities
            )
        return True
    except Exception as err:
        print(f"Failed to send to channel {channel_id}: {err}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Photo bhejiyen, main ek saath sabhi channels me fast-forward post kar dunga!"
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ Processing & Broadcasting in Parallel...")

    try:
        caption = update.message.caption or ""
        caption_entities = update.message.caption_entities

        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        processed_io = add_watermarks(image_bytes)
        processed_bytes = processed_io.getvalue()

        final_caption = process_caption(caption)

        # 1. USER KO PEHLE REPLY
        user_photo = io.BytesIO(processed_bytes)
        if final_caption != caption:
            await update.message.reply_photo(
                photo=user_photo,
                caption=final_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_photo(
                photo=user_photo,
                caption=caption,
                caption_entities=caption_entities
            )

        # 2. SABHI CHANNELS ME EK SAATH (PARALLEL) POSTING
        tasks = [
            send_to_single_channel(
                context, 
                channel_id, 
                processed_bytes, 
                final_caption, 
                caption, 
                caption_entities
            )
            for channel_id in TARGET_CHANNELS
        ]

        results = await asyncio.gather(*tasks)
        successful_posts = sum(1 for res in results if res)

        await status_msg.edit_text(
            f"🚀 **Fast Broadcast Done!**\nPosted to {successful_posts}/{len(TARGET_CHANNELS)} channels simultaneously."
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("🤖 Bot Active hai...")
    app.run_polling()

if __name__ == "__main__":
    main()
