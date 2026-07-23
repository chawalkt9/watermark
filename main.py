import io
import requests
from PIL import Image, ImageOps, ImageDraw
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Aapka Logo URL
LOGO_URL = "https://yt3.googleusercontent.com/LSfY1cV1wEWgXQOp3IMnKBVXo4Akr-FrNUqPa-RDo5Ls-o4YW0yqn_-ZHZzo40j8irSyLAc4=s160-c-k-c0x00ffffff-no-rj"

# Telegram Bot Token yahan replace karein
BOT_TOKEN = "8067633045:AAHnEOXgHO48JPZKueURRnJadYdP_Dd_S1U"


def get_circular_logo(logo_img: Image.Image) -> Image.Image:
    """Logo ko bilkul circular crop aur transparent banane ke liye function"""
    logo_img = logo_img.convert("RGBA")
    size = (min(logo_img.size), min(logo_img.size))
    logo_img = logo_img.resize(size, Image.Resampling.LANCZOS)
    
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    
    output = ImageOps.fit(logo_img, size, centering=(0.5, 0.5))
    output.putalpha(mask)
    return output


def add_logo_watermark(base_image_bytes: bytes) -> io.BytesIO:
    # Main Product Image Open Karein
    base_img = Image.open(io.BytesIO(base_image_bytes)).convert("RGBA")
    width, height = base_img.size

    # URL se Logo Download Karein
    response = requests.get(LOGO_URL)
    logo_raw = Image.open(io.BytesIO(response.content))
    
    # Logo ko Circular Banayein
    logo = get_circular_logo(logo_raw)

    # -------------------------------------------------------------
    # Top-Left Logo Alignment Settings (No Crossing)
    # -------------------------------------------------------------
    # Base Image ki width ka 12% size rakhenge logo ka
    logo_w = int(width * 0.12)
    logo = logo.resize((logo_w, logo_w), Image.Resampling.LANCZOS)

    # Top aur Left se Margin (Image width ka 3%)
    margin = int(width * 0.03)
    
    # Logo Paste Position: (Top-Left Corner)
    position = (margin, margin)

    # Image Layer Overlay
    base_img.paste(logo, position, logo)

    # Output Buffer Output
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
        # Highest resolution photo download karein
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        # Watermark Process Karein
        processed_image = add_logo_watermark(image_bytes)

        # User ko watermarked image bhejein
        await update.message.reply_photo(photo=processed_image)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))

    print("🤖 Bot Active hai... Telegram par photo bhej kar check karein!")
    app.run_polling()


if __name__ == "__main__":
    main()