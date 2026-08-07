"""
Pillow-Based Dynamic Movie Poster Generator
Downloads backdrops, composite title artwork, movie details, custom watermarks/logos,
and renders a clean 16:9 or custom banner image for auto-posting to channels.
"""

import io
import os
import logging
from typing import Optional
import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

logger = logging.getLogger("PosterGenerator")


class DynamicPosterGenerator:
    def __init__(self) -> None:
        self.default_width = 1280
        self.default_height = 720
        self.font_path_bold = os.path.join("fonts", "Roboto-Bold.ttf")
        self.font_path_regular = os.path.join("fonts", "Roboto-Regular.ttf")

    def _get_font(self, path: str, size: int) -> ImageFont.FreeTypeFont:
        """Loads TTF font or falls back to system default."""
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    async def _fetch_image(self, url: str) -> Optional[Image.Image]:
        """Async downloads image and converts to RGBA PIL Image."""
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.read()
                        return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as e:
            logger.error(f"Error fetching image from {url}: {e}")
        return None

    def _apply_dark_gradient(self, base_img: Image.Image) -> Image.Image:
        """Applies a dark gradient overlay from left to right for text readability."""
        width, height = base_img.size
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(gradient)

        for x in range(width):
            # Smooth dark gradient transitioning from 85% opacity on left to 40% on right
            alpha = int(220 - (x / width) * 120)
            draw.line([(x, 0), (x, height)], fill=(10, 10, 15, alpha))

        return Image.alpha_composite(base_img, gradient)

    async def create_poster(
        self,
        backdrop_url: str,
        poster_url: str,
        title: str,
        year: str,
        rating: str,
        genres: str,
        language: str,
        runtime: str,
        logo_text: str = "MOVIE BOT",
    ) -> io.BytesIO:
        """
        Renders a high-resolution 1280x720 banner composite image.
        Returns bytes in JPEG format inside a BytesIO buffer.
        """
        # Create base canvas (1280x720 dark fallback)
        canvas = Image.new("RGBA", (self.default_width, self.default_height), (15, 15, 20, 255))

        # 1. Background Backdrop Image
        backdrop = await self._fetch_image(backdrop_url)
        if backdrop:
            backdrop = backdrop.resize((self.default_width, self.default_height), Image.Resampling.LANCZOS)
            # Add slight blur to background
            backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=3))
            canvas.paste(backdrop, (0, 0))

        # 2. Apply Dark Overlay
        canvas = self._apply_dark_gradient(canvas)

        # 3. Main Poster Overlay (Left Side)
        poster = await self._fetch_image(poster_url)
        if poster:
            p_width = 320
            p_height = 480
            poster = poster.resize((p_width, p_height), Image.Resampling.LANCZOS)
            
            # Draw rounded corners / border shadow
            mask = Image.new("L", (p_width, p_height), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle([(0, 0), (p_width, p_height)], radius=16, fill=255)
            
            canvas.paste(poster, (60, 120), mask)

        # 4. Render Text Details
        draw = ImageDraw.Draw(canvas)

        font_logo = self._get_font(self.font_path_bold, 24)
        font_title = self._get_font(self.font_path_bold, 42)
        font_details = self._get_font(self.font_path_regular, 26)
        font_rating = self._get_font(self.font_path_bold, 30)

        # Top Watermark / Custom Logo
        draw.text((420, 60), f"🎬 {logo_text.upper()}", fill=(230, 180, 0, 255), font=font_logo)

        # Title Formatting (Truncate if too long)
        display_title = title[:32] + "..." if len(title) > 32 else title
        draw.text((420, 120), display_title, fill=(255, 255, 255, 255), font=font_title)

        # Metadata Details Stack
        text_y = 200
        draw.text((420, text_y), f"📅 Year: {year}", fill=(220, 220, 220, 255), font=font_details)
        text_y += 45
        draw.text((420, text_y), f"⭐ Rating: {rating} / 10", fill=(255, 215, 0, 255), font=font_rating)
        text_y += 50
        draw.text((420, text_y), f"🎭 Genre: {genres}", fill=(200, 200, 200, 255), font=font_details)
        text_y += 45
        draw.text((420, text_y), f"🌐 Language: {language}", fill=(200, 200, 200, 255), font=font_details)
        text_y += 45
        draw.text((420, text_y), f"⏱ Runtime: {runtime}", fill=(200, 200, 200, 255), font=font_details)

        # Bottom Call to Action Badge
        draw.rounded_rectangle([(420, 520), (760, 580)], radius=10, fill=(220, 38, 38, 255))
        draw.text((450, 535), "AVAILABLE NOW", fill=(255, 255, 255, 255), font=font_logo)

        # 5. Convert final RGB Image to BytesIO Buffer
        final_img = canvas.convert("RGB")
        buffer = io.BytesIO()
        final_img.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)

        return buffer


# Singleton instance
poster_generator = DynamicPosterGenerator()
