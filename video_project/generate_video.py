"""
AI Real Estate Automation – Premium Cinematic Video Generator
1080x1920 | 30fps | 30 seconds | Navy/Gold palette
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
import math, os, random, subprocess, tempfile, shutil

# ─── CONFIG ─────────────────────────────────────────────────────────────────
W, H = 1080, 1920
FPS = 30
TOTAL_FRAMES = FPS * 30   # 30 seconds

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
FONT_AR_BOLD   = os.path.join(ASSETS, "NotoSansArabic-Bold.ttf")
FONT_AR_REG    = os.path.join(ASSETS, "NotoSansArabic-Regular.ttf")
FONT_EN_BOLD   = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_EN_REG    = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_MONO      = "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"

OUT_DIR = os.path.join(os.path.dirname(__file__), "frames")
os.makedirs(OUT_DIR, exist_ok=True)

# ─── PALETTE ─────────────────────────────────────────────────────────────────
BG_DARK     = (5, 8, 20)
NAVY        = (8, 15, 40)
NAVY_MID    = (12, 25, 65)
GOLD        = (212, 175, 55)
GOLD_LIGHT  = (255, 215, 80)
WHITE       = (255, 255, 255)
WHITE_DIM   = (200, 210, 230)
RED_PAIN    = (220, 40, 40)
GREEN_WA    = (37, 211, 102)
GREEN_DARK  = (7, 94, 84)
TEAL        = (0, 180, 160)
SILVER      = (160, 175, 195)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def fnt(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def ease_in_out(t):
    return t * t * (3 - 2 * t)

def ease_out(t):
    return 1 - (1 - t) ** 3

def ease_in(t):
    return t ** 3

def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def alpha_composite(base: Image.Image, overlay: Image.Image, pos=(0, 0)):
    tmp = Image.new("RGBA", base.size, (0, 0, 0, 0))
    tmp.paste(overlay, pos)
    return Image.alpha_composite(base.convert("RGBA"), tmp).convert("RGB")

def arabic_text(text):
    """Reshape + bidi Arabic text for proper display."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text

def draw_text_centered(draw, img, text, y, font, color, shadow=True, shadow_color=None, letter_spacing=0):
    if shadow_color is None:
        shadow_color = (0, 0, 0, 180)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    if shadow:
        for ox, oy in [(-2, 2), (0, 3), (2, 2), (0, -1)]:
            draw.text((x + ox, y + oy), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=color)

def draw_text_right(draw, text, x, y, font, color):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    draw.text((x - tw, y), text, font=font, fill=color)

def gradient_bg(w, h, top_color, bot_color):
    img = Image.new("RGB", (w, h))
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for i in range(h):
        t = i / h
        arr[i] = [
            int(lerp(top_color[c], bot_color[c], t))
            for c in range(3)
        ]
    return Image.fromarray(arr)

def radial_gradient_layer(w, h, center_color, edge_color, radius_factor=1.0):
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    cx, cy = w / 2, h / 2
    max_r = math.sqrt(cx**2 + cy**2) * radius_factor
    for y in range(h):
        for x in range(w):
            r = math.sqrt((x - cx)**2 + (y - cy)**2)
            t = clamp(r / max_r, 0, 1)
            col = [int(lerp(center_color[c], edge_color[c], t)) for c in range(3)]
            alpha = int(lerp(center_color[3] if len(center_color) > 3 else 255,
                             edge_color[3] if len(edge_color) > 3 else 0, t))
            arr[y, x] = col[:3] + [alpha]
    return Image.fromarray(arr, "RGBA")

def noise_layer(w, h, intensity=20, seed=0):
    rng = np.random.RandomState(seed)
    grain = rng.randint(-intensity, intensity, (h, w, 3)).astype(np.int16)
    arr = np.clip(128 + grain, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")

def add_film_grain(img, intensity=12, seed=0):
    rng = np.random.RandomState(seed)
    arr = np.array(img).astype(np.int16)
    grain = rng.randint(-intensity, intensity, arr.shape).astype(np.int16)
    arr = np.clip(arr + grain, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)

def add_vignette(img, strength=0.65):
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    Y, X = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    r = np.sqrt(((X - cx) / cx)**2 + ((Y - cy) / cy)**2)
    mask = 1 - np.clip(r * strength, 0, 1)
    mask = mask[:, :, np.newaxis]
    arr = (arr * mask).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr)

def chromatic_aberration(img, shift=3):
    arr = np.array(img)
    result = arr.copy()
    result[:, shift:, 0] = arr[:, :-shift, 0]   # R shift right
    result[:, :-shift, 2] = arr[:, shift:, 2]   # B shift left
    return Image.fromarray(result)

def draw_glow_circle(draw, cx, cy, r, color, alpha=80):
    for i in range(8, 0, -1):
        a = int(alpha * i / 8)
        r2 = r + (8 - i) * 6
        draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
                     fill=(*color[:3], a))

def rounded_rect(draw, x1, y1, x2, y2, radius, fill=None, outline=None, width=2):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=width)

def camera_shake(frame_i, intensity=8):
    """Returns (dx, dy) shake offset."""
    dx = int(math.sin(frame_i * 1.7) * intensity * random.uniform(0.5, 1.0))
    dy = int(math.cos(frame_i * 2.3) * intensity * random.uniform(0.5, 1.0))
    return dx, dy

def zoom_frame(img, scale, cx=None, cy=None):
    if cx is None: cx = W // 2
    if cy is None: cy = H // 2
    nw, nh = int(W / scale), int(H / scale)
    x1 = clamp(cx - nw // 2, 0, W - nw)
    y1 = clamp(cy - nh // 2, 0, H - nh)
    cropped = img.crop((x1, y1, x1 + nw, y1 + nh))
    return cropped.resize((W, H), Image.LANCZOS)

# ─── PARTICLE SYSTEM ─────────────────────────────────────────────────────────
class Particles:
    def __init__(self, n=40, seed=42):
        rng = np.random.RandomState(seed)
        self.x  = rng.randint(0, W, n).astype(float)
        self.y  = rng.randint(0, H, n).astype(float)
        self.vy = rng.uniform(-0.4, -1.2, n)
        self.vx = rng.uniform(-0.3, 0.3, n)
        self.r  = rng.uniform(1, 4, n)
        self.a  = rng.uniform(60, 180, n).astype(float)
        self.da = rng.uniform(-0.5, -1.5, n)
        self.color = [GOLD if rng.random() > 0.4 else WHITE for _ in range(n)]

    def step(self):
        self.x = (self.x + self.vx) % W
        self.y = (self.y + self.vy) % H
        self.a = np.clip(self.a + self.da, 20, 200)

    def draw(self, img):
        draw = ImageDraw.Draw(img, "RGBA")
        for i in range(len(self.x)):
            a = int(self.a[i])
            r = self.r[i]
            c = (*self.color[i][:3], a)
            cx, cy = int(self.x[i]), int(self.y[i])
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
        return img

particles = Particles(n=50)

# ─── SCENE RENDERERS ─────────────────────────────────────────────────────────

def make_base_bg(t_scene, shake_intensity=0, scene_tint=None):
    """Premium dark background with subtle gradient."""
    img = gradient_bg(W, H, NAVY, BG_DARK)
    arr = np.array(img).astype(np.float32)

    # Subtle animated diagonal light sweep
    sweep_x = int((t_scene * 0.3 % 1.0) * W * 2 - W // 2)
    for x in range(max(0, sweep_x - 200), min(W, sweep_x + 200)):
        dist = abs(x - sweep_x)
        a = max(0, 1 - dist / 200) * 0.08
        arr[:, x] = np.clip(arr[:, x] + a * 40, 0, 255)

    if scene_tint:
        tc = np.array(scene_tint, dtype=np.float32)
        arr = np.clip(arr * 0.85 + tc * 0.15, 0, 255)

    img = Image.fromarray(arr.astype(np.uint8))

    # Grid lines (subtle)
    d = ImageDraw.Draw(img, "RGBA")
    grid_alpha = 15
    for gx in range(0, W, 120):
        d.line([(gx, 0), (gx, H)], fill=(100, 130, 200, grid_alpha), width=1)
    for gy in range(0, H, 120):
        d.line([(0, gy), (W, gy)], fill=(100, 130, 200, grid_alpha), width=1)

    return img


def scene_hook(f, total=120, offset=0):
    """0-4s: Painful hook - notifications flooding, chaos, missed leads."""
    t = f / total
    img = make_base_bg(t, shake_intensity=6, scene_tint=(60, 5, 5))
    d = ImageDraw.Draw(img, "RGBA")

    # Red danger vignette pulse
    pulse = 0.5 + 0.5 * math.sin(t * math.pi * 8)
    for r in range(500, 0, -100):
        a = int(pulse * 35 * (500 - r) / 500)
        d.ellipse([W//2 - r, H//2 - r, W//2 + r, H//2 + r],
                  fill=(200, 30, 30, a))

    # Phone silhouette
    ph_x, ph_y, ph_w, ph_h = 340, 480, 400, 700
    shake_f = int(math.sin(f * 0.9) * 8)
    d.rounded_rectangle([ph_x + shake_f, ph_y, ph_x + ph_w + shake_f, ph_y + ph_h],
                         radius=40, fill=(15, 20, 45), outline=(60, 70, 100), width=3)
    # Screen
    d.rectangle([ph_x + 20 + shake_f, ph_y + 60, ph_x + ph_w - 20 + shake_f, ph_y + ph_h - 60],
                fill=(8, 12, 30))

    # Notification badges flooding in
    notif_data = [
        ("+971 50 123 4567", "شقة دبي مارينا", "منذ 3 دقائق"),
        ("+971 55 987 6543", "فيلا في أبوظبي", "منذ 12 دقيقة"),
        ("+971 52 456 7890", "بنتهاوس JBR", "منذ 31 دقيقة"),
        ("+971 56 111 2222", "شقة في الشارقة", "منذ 1 ساعة"),
        ("+971 50 333 4444", "استفسار عاجل", "منذ 2 ساعة"),
    ]

    fn_name  = fnt(FONT_AR_REG, 28)
    fn_msg   = fnt(FONT_AR_BOLD, 32)
    fn_time  = fnt(FONT_EN_REG, 24)
    fn_big   = fnt(FONT_EN_BOLD, 90)
    fn_sub   = fnt(FONT_EN_BOLD, 38)
    fn_tag   = fnt(FONT_EN_BOLD, 28)

    # Notification cards
    for i, (num, msg, time_ago) in enumerate(notif_data):
        nt = clamp((t * 5 - i * 0.3), 0, 1)
        if nt <= 0:
            continue
        slide_y = int(lerp(-120, 0, ease_out(min(nt * 3, 1))))
        card_y = ph_y + 80 + i * 108 + slide_y
        if card_y + 95 > ph_y + ph_h - 60:
            break

        # Card bg
        card_x = ph_x + 30 + shake_f
        d.rounded_rectangle([card_x, card_y, card_x + 340, card_y + 92],
                             radius=18, fill=(20, 28, 60, 230))
        # Green WA dot
        d.ellipse([card_x + 10, card_y + 30, card_x + 52, card_y + 72],
                  fill=GREEN_WA)
        # W letter
        fw = fnt(FONT_EN_BOLD, 28)
        d.text((card_x + 21, card_y + 36), "W", font=fw, fill=WHITE)
        # Text
        ar = arabic_text(msg)
        d.text((card_x + 320, card_y + 10), ar, font=fn_msg, fill=WHITE, anchor="ra")
        d.text((card_x + 320, card_y + 50), arabic_text(num[-8:]), font=fn_time,
               fill=SILVER, anchor="ra")
        # Red missed badge
        d.ellipse([card_x + 295, card_y + 5, card_x + 330, card_y + 32],
                  fill=RED_PAIN)
        d.text((card_x + 313, card_y + 8), "!", font=fnt(FONT_EN_BOLD, 22), fill=WHITE, anchor="mm")

    # Big pain text
    if t > 0.5:
        txt_alpha = int(ease_in_out(min((t - 0.5) * 2, 1)) * 255)
        pain_y = 1380

        # "47 LEADS" big number
        txt_47 = "47"
        d.text((W // 2, pain_y), txt_47, font=fn_big, fill=(*RED_PAIN, txt_alpha), anchor="mm")
        d.text((W // 2, pain_y + 95), "LEADS IGNORED THIS WEEK", font=fn_sub,
               fill=(*WHITE_DIM, txt_alpha), anchor="mm")

    # Top label
    d.text((W // 2, 90), arabic_text("هذا يحدث لعملائك كل يوم"), font=fnt(FONT_AR_BOLD, 44),
           fill=(*RED_PAIN, 200), anchor="mm")

    return img


def draw_whatsapp_chat(d, messages_shown, total_w=640, x0=220, y0=320):
    """Draw realistic WhatsApp dark chat interface."""
    # Chat bg
    d.rounded_rectangle([x0, y0, x0 + total_w, y0 + 1100],
                         radius=32, fill=(11, 20, 36), outline=(30, 45, 80), width=2)

    # Header
    d.rounded_rectangle([x0, y0, x0 + total_w, y0 + 90],
                         radius=32, fill=(18, 30, 58))
    d.rounded_rectangle([x0, y0 + 60, x0 + total_w, y0 + 90],
                         radius=0, fill=(18, 30, 58))

    # Avatar
    d.ellipse([x0 + 14, y0 + 14, x0 + 64, y0 + 64], fill=GREEN_DARK)
    d.text((x0 + 39, y0 + 39), "أ", font=fnt(FONT_AR_BOLD, 28), fill=WHITE, anchor="mm")

    fn_hdr  = fnt(FONT_EN_BOLD, 26)
    fn_stat = fnt(FONT_EN_REG, 20)
    d.text((x0 + 80, y0 + 16), "Ahmad Al-Mansouri", font=fn_hdr, fill=WHITE)
    d.text((x0 + 80, y0 + 50), "online", font=fn_stat, fill=(GREEN_WA))

    # Back arrow
    d.text((x0 + total_w - 30, y0 + 35), "⋮", font=fnt(FONT_EN_BOLD, 30), fill=SILVER, anchor="mm")

    # Messages
    msgs = [
        ("client", arabic_text("السلام عليكم، أبحث عن شقة"), "10:23"),
        ("client", arabic_text("3 غرف نوم في دبي مارينا"), "10:23"),
        ("client", arabic_text("الميزانية حوالي 2 مليون درهم"), "10:24"),
        ("client", arabic_text("للسكن الخاص, تسليم فوري"), "10:24"),
    ]

    my = y0 + 110
    fn_msg  = fnt(FONT_AR_BOLD, 30)
    fn_time = fnt(FONT_EN_REG, 20)

    for idx, (who, text, ts) in enumerate(msgs):
        if idx >= messages_shown:
            break
        bw = bbox_width(fn_msg, text) + 40
        bw = min(bw, total_w - 60)
        bh = 68

        if who == "client":
            bx = x0 + total_w - bw - 20
            bubble_color = (0, 92, 75)
        else:
            bx = x0 + 20
            bubble_color = (30, 45, 75)

        d.rounded_rectangle([bx, my, bx + bw, my + bh], radius=16, fill=bubble_color)
        d.text((bx + bw // 2, my + 22), text, font=fn_msg, fill=WHITE, anchor="mm")
        d.text((bx + bw - 12, my + bh - 14), ts, font=fn_time, fill=(180, 210, 180), anchor="ra")
        my += bh + 14

    # Typing indicator
    return my


def bbox_width(font, text):
    bb = font.getbbox(text)
    return bb[2] - bb[0]


def scene_whatsapp(f, total=120, offset=0):
    """4-8s: WhatsApp lead coming in with realistic UI."""
    t = f / total
    img = make_base_bg(t)
    d = ImageDraw.Draw(img, "RGBA")

    # Panel slide-in from bottom
    panel_y = int(lerp(H + 100, 150, ease_out(min(t * 2, 1))))

    # WhatsApp panel
    msg_count = int(t * 6) + 1

    draw_whatsapp_chat(d, msg_count, x0=220, y0=panel_y)

    # Typing dots animation
    if t > 0.6:
        dot_t = (t - 0.6) / 0.4
        ty = panel_y + 112 + min(msg_count - 1, 3) * 82 + 70
        dx = 260
        fn_dots = fnt(FONT_EN_BOLD, 40)
        for di in range(3):
            bounce = math.sin((dot_t * 6 + di * 0.8) * math.pi) * 8
            dot_a = int(clamp(dot_t * 255, 100, 255))
            d.ellipse([dx + di * 28, ty - 10 + bounce, dx + di * 28 + 14, ty + 4 + bounce],
                      fill=(*SILVER, dot_a))

    # Label
    fn_label = fnt(FONT_EN_BOLD, 42)
    fn_sub   = fnt(FONT_EN_REG, 30)
    label_a = int(ease_out(min(t * 3, 1)) * 255)
    d.text((W // 2, 80), "INCOMING LEAD", font=fn_label, fill=(*GOLD, label_a), anchor="mm")
    d.text((W // 2, 130), "Client request via WhatsApp", font=fn_sub, fill=(*SILVER, label_a), anchor="mm")

    # AI badge bottom
    if t > 0.7:
        ai_a = int(ease_out((t - 0.7) / 0.3) * 220)
        d.rounded_rectangle([240, 1700, 840, 1800], radius=24,
                              fill=(10, 180, 140, ai_a))
        d.text((W // 2, 1750), "AI is reading your client's request...",
               font=fnt(FONT_EN_BOLD, 32), fill=(*WHITE, ai_a), anchor="mm")

    return img


def draw_property_card(d, x, y, w, h, name_ar, specs, price, img_color, progress=1.0, score=None):
    """Draw a luxury property card."""
    alpha = int(ease_out(min(progress * 2, 1)) * 255)
    slide = int(lerp(60, 0, ease_out(min(progress, 1))))

    ry = y + slide
    # Card shadow
    d.rounded_rectangle([x + 6, ry + 6, x + w + 6, ry + h + 6],
                         radius=22, fill=(0, 0, 0, 80))
    # Card bg
    d.rounded_rectangle([x, ry, x + w, ry + h], radius=22,
                         fill=(14, 24, 54, alpha), outline=(*GOLD[:3], int(alpha * 0.4)), width=1)

    # Property image placeholder (gradient block)
    img_h = int(h * 0.45)
    img_arr = np.zeros((img_h, w - 4, 3), dtype=np.uint8)
    for row in range(img_h):
        t2 = row / img_h
        col = [int(lerp(img_color[c], max(0, img_color[c] - 40), t2)) for c in range(3)]
        img_arr[row] = col
    img_block = Image.fromarray(img_arr)
    d_tmp = ImageDraw.Draw(img_block)

    # City skyline silhouette hint
    for bx in range(0, w, 40):
        bh2 = 20 + (bx * 7 % 60)
        d_tmp.rectangle([bx, img_h - bh2, bx + 30, img_h], fill=(0, 0, 0, 60))

    # Paste image block
    img_pil = Image.fromarray(img_arr).convert("RGBA")
    # Round top corners
    mask = Image.new("L", (w - 4, img_h), 0)
    dm = ImageDraw.Draw(mask)
    dm.rounded_rectangle([0, 0, w - 4, img_h], radius=22, fill=255)
    img_pil.putalpha(mask)
    # We just draw via the main draw - approximate
    d.rectangle([x + 2, ry + 2, x + w - 2, ry + 2 + img_h], fill=(*img_color, alpha))

    # Skyline on image area
    sky_colors = [(0, 0, 0, 80)]
    for bx in range(x + 4, x + w - 4, 35):
        bh2 = 18 + ((bx * 11) % 55)
        d.rectangle([bx, ry + 2 + img_h - bh2, bx + 26, ry + 2 + img_h],
                     fill=(0, 0, 0, 80))

    # Score badge
    if score:
        d.rounded_rectangle([x + w - 100, ry + 10, x + w - 10, ry + 48],
                              radius=12, fill=(GOLD[0], GOLD[1], GOLD[2], alpha))
        d.text((x + w - 55, ry + 29), f"★ {score}%", font=fnt(FONT_EN_BOLD, 22),
               fill=(20, 15, 5, 230), anchor="mm")

    # Property name
    fn_nm = fnt(FONT_AR_BOLD, 36)
    name_y = ry + 2 + img_h + 18
    ar_name = arabic_text(name_ar)
    d.text((x + w - 18, name_y), ar_name, font=fn_nm, fill=(*WHITE, alpha), anchor="ra")

    # Specs
    fn_sp = fnt(FONT_EN_REG, 22)
    sy = name_y + 52
    for spec in specs:
        d.text((x + 16, sy), spec, font=fn_sp, fill=(*SILVER, alpha))
        sy += 32

    # Price
    fn_pr = fnt(FONT_EN_BOLD, 34)
    d.text((x + w - 16, ry + h - 44), price, font=fn_pr, fill=(*GOLD, alpha), anchor="ra")
    d.text((x + 16, ry + h - 30), "AED", font=fnt(FONT_EN_REG, 20), fill=(*SILVER, alpha))


def scene_ai_matching(f, total=180, offset=0):
    """8-14s: AI matching properties instantly."""
    t = f / total
    img = make_base_bg(t)
    d = ImageDraw.Draw(img, "RGBA")

    # AI brain / processing circle at top
    cx, cy = W // 2, 380
    ai_pulse = 0.7 + 0.3 * math.sin(t * math.pi * 6)

    for r in [140, 120, 100, 80]:
        a = int(ai_pulse * 50 * (160 - r) / 160)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*TEAL, a))

    d.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], fill=NAVY_MID)

    # AI icon - rotating ring
    for angle in range(0, 360, 20):
        rad = math.radians(angle + t * 360)
        px = cx + int(55 * math.cos(rad))
        py = cy + int(55 * math.sin(rad))
        dot_size = 5 + int(3 * math.sin(rad * 2))
        da = int(100 + 155 * (0.5 + 0.5 * math.sin(rad)))
        d.ellipse([px - dot_size, py - dot_size, px + dot_size, py + dot_size],
                  fill=(*TEAL, da))

    # AI text
    fn_ai = fnt(FONT_EN_BOLD, 34)
    d.text((cx, cy - 8), "AI", font=fn_ai, fill=TEAL, anchor="mm")
    d.text((cx, cy + 22), "ENGINE", font=fnt(FONT_EN_BOLD, 18), fill=SILVER, anchor="mm")

    # Scanning text
    scan_texts = ["Analyzing request...", "Scanning 12,400 listings...", "Matching criteria...", "Found 3 matches!"]
    scan_idx = min(int(t * 5), 3)
    fn_scan = fnt(FONT_EN_BOLD, 36)
    d.text((W // 2, 520), scan_texts[scan_idx], font=fn_scan, fill=GOLD, anchor="mm")

    # Speed counter
    if t > 0.1:
        speed_t = min((t - 0.1) / 0.4, 1.0)
        ms_shown = int(lerp(0, 847, ease_out(speed_t)))
        fn_speed = fnt(FONT_EN_BOLD, 58)
        d.text((W // 2, 620), f"{ms_shown}ms", font=fn_speed, fill=WHITE, anchor="mm")
        d.text((W // 2, 680), "PROCESSING TIME", font=fnt(FONT_EN_REG, 24), fill=SILVER, anchor="mm")

    # Property cards
    cards = [
        ("شقة دبي مارينا – برج الأمواج",
         ["🛏 3 غرف | 🛁 2", "📐 1,850 sqft", "🏙 Marina View"],
         "1,950,000", (20, 40, 80), 97),
        ("دبي مارينا ووك – أبراج الخور",
         ["🛏 3 غرف | 🛁 3", "📐 2,100 sqft", "🌊 Sea View"],
         "2,100,000", (15, 55, 70), 94),
        ("جميرا بيتش ريزيدنس",
         ["🛏 3 غرف | 🛁 2", "📐 1,950 sqft", "🏖 Beach Front"],
         "2,050,000", (30, 30, 75), 91),
    ]

    card_w, card_h = 880, 380
    card_x = (W - card_w) // 2

    for i, (name, specs, price, col, score) in enumerate(cards):
        card_t = clamp((t * 3 - i * 0.6) - 0.3, 0, 1)
        if card_t <= 0:
            continue
        cy2 = 740 + i * (card_h + 24)
        draw_property_card(d, card_x, cy2, card_w, card_h, name, specs, price, col, card_t, score)

    # Top label
    la = int(ease_out(min(t * 2, 1)) * 255)
    d.text((W // 2, 90), "AI PROPERTY MATCHING", font=fnt(FONT_EN_BOLD, 46), fill=(*GOLD, la), anchor="mm")
    d.text((W // 2, 145), arabic_text("يجد الذكاء الاصطناعي العقار المثالي فوراً"),
           font=fnt(FONT_AR_BOLD, 34), fill=(*WHITE_DIM, la), anchor="mm")

    return img


def draw_crm_row(d, x, y, w, label_ar, status, color, progress, row_h=72):
    """Draw one CRM data row."""
    a = int(ease_out(min(progress * 2, 1)) * 255)
    slide = int(lerp(-40, 0, ease_out(min(progress, 1))))

    d.rounded_rectangle([x, y + slide, x + w, y + row_h + slide],
                         radius=14, fill=(12, 22, 52, a), outline=(40, 60, 110, a), width=1)

    # Status dot
    d.ellipse([x + 16, y + 24 + slide, x + 40, y + 48 + slide], fill=(*color, a))

    # Arabic label
    ar = arabic_text(label_ar)
    d.text((x + w - 20, y + 20 + slide), ar, font=fnt(FONT_AR_BOLD, 28), fill=(*WHITE, a), anchor="ra")

    # Status badge
    badge_w = 220
    d.rounded_rectangle([x + 60, y + 16 + slide, x + 60 + badge_w, y + 56 + slide],
                         radius=10, fill=(*color[:3], int(a * 0.25)))
    d.text((x + 60 + badge_w // 2, y + 36 + slide), status, font=fnt(FONT_EN_BOLD, 22),
           fill=(*color, a), anchor="mm")


def scene_crm(f, total=150, offset=0):
    """14-19s: CRM automation updating live."""
    t = f / total
    img = make_base_bg(t)
    d = ImageDraw.Draw(img, "RGBA")

    # CRM Panel
    panel_x, panel_y = 60, 200
    panel_w, panel_h = 960, 1400

    la = int(ease_out(min(t * 2, 1)) * 255)
    d.rounded_rectangle([panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
                          radius=32, fill=(9, 16, 42, la), outline=(*GOLD[:3], int(la * 0.5)), width=2)

    # CRM header
    d.rounded_rectangle([panel_x, panel_y, panel_x + panel_w, panel_y + 80],
                          radius=32, fill=(16, 30, 72, la))
    d.rounded_rectangle([panel_x, panel_y + 50, panel_x + panel_w, panel_y + 80],
                          radius=0, fill=(16, 30, 72, la))
    d.text((panel_x + 30, panel_y + 22), "CRM Dashboard", font=fnt(FONT_EN_BOLD, 34),
           fill=(*GOLD, la))
    d.text((panel_x + panel_w - 30, panel_y + 22), "● LIVE", font=fnt(FONT_EN_BOLD, 26),
           fill=(*GREEN_WA, la), anchor="ra")

    # Stats row
    stats = [("47", "Leads Today"), ("12", "Qualified"), ("8", "Meetings"), ("3", "Closed")]
    sw = panel_w // 4
    for i, (val, lbl) in enumerate(stats):
        sx = panel_x + i * sw + sw // 2
        st = ease_out(min((t * 4 - i * 0.2), 1))
        shown_val = str(int(float(val) * max(st, 0))) if st > 0 else "0"
        d.text((sx, panel_y + 140), shown_val, font=fnt(FONT_EN_BOLD, 56), fill=(*GOLD, la), anchor="mm")
        d.text((sx, panel_y + 195), lbl, font=fnt(FONT_EN_REG, 22), fill=(*SILVER, la), anchor="mm")

    # Divider
    d.line([(panel_x + 20, panel_y + 220), (panel_x + panel_w - 20, panel_y + 220)],
           fill=(*NAVY_MID, la), width=1)

    # Lead rows
    leads = [
        ("أحمد المنصوري – شقة دبي مارينا", "✓ Qualified", GREEN_WA),
        ("سارة الأحمدي – فيلا ياس", "📅 Meeting Booked", GOLD),
        ("محمد الرشيد – بنتهاوس JBR", "🔍 AI Searching", TEAL),
        ("نورة الكندي – شقة العين", "✓ Qualified", GREEN_WA),
        ("خالد البلوشي – مكتب DIFC", "📤 Proposal Sent", (100, 160, 255)),
        ("فاطمة الزهراني – تاون هاوس", "⏳ Responding...", SILVER),
    ]

    row_y = panel_y + 240
    for i, (lead, status, color) in enumerate(leads):
        row_t = clamp(t * 4 - i * 0.35, 0, 1)
        if row_t <= 0:
            continue

        # Animate status change
        if i == 2 and t > 0.6:
            update_t = (t - 0.6) / 0.4
            status = "✓ Matched!" if update_t > 0.5 else "🔍 AI Searching"
            color = GREEN_WA if update_t > 0.5 else TEAL

        draw_crm_row(d, panel_x + 20, row_y, panel_w - 40, lead.split("–")[0],
                     status, color, row_t)
        row_y += 84

    # Auto-update badge
    if t > 0.5:
        upd_a = int(ease_out((t - 0.5) / 0.5) * 220)
        pulse2 = int(200 + 55 * math.sin(t * math.pi * 8))
        d.rounded_rectangle([panel_x + 20, panel_y + panel_h - 80,
                              panel_x + panel_w - 20, panel_y + panel_h - 14],
                              radius=18, fill=(0, 120, 100, upd_a))
        d.text((W // 2, panel_y + panel_h - 47),
               "✓  CRM updated automatically — zero manual work",
               font=fnt(FONT_EN_BOLD, 28), fill=(*WHITE, upd_a), anchor="mm")

    # Top heading
    d.text((W // 2, 100), "AUTOMATED CRM", font=fnt(FONT_EN_BOLD, 50), fill=(*GOLD, la), anchor="mm")
    d.text((W // 2, 160), arabic_text("يتحدّث مع العميل ويحدّث السجلات تلقائياً"),
           font=fnt(FONT_AR_BOLD, 34), fill=(*WHITE_DIM, la), anchor="mm")

    return img


def scene_transformation(f, total=210, offset=0):
    """19-26s: Business transformation - before/after split."""
    t = f / total
    img = make_base_bg(t)
    d = ImageDraw.Draw(img, "RGBA")

    la = int(ease_out(min(t * 2, 1)) * 255)

    # Split divider (animated from center)
    divider_height = int(lerp(0, H * 0.65, ease_out(min(t * 2, 1))))
    div_y = (H - divider_height) // 2
    d.rectangle([W // 2 - 2, div_y, W // 2 + 2, div_y + divider_height],
                fill=(*GOLD, la))

    # LEFT: BEFORE
    left_a = int(ease_out(min(t * 2, 1)) * 200)
    bx = 40
    by = 250

    d.text((W // 4, by - 70), "BEFORE", font=fnt(FONT_EN_BOLD, 42), fill=(*RED_PAIN, left_a), anchor="mm")
    d.text((W // 4, by - 20), arabic_text("بدون AI"), font=fnt(FONT_AR_BOLD, 30),
           fill=(*SILVER, left_a), anchor="mm")

    pains = [
        "× Leads ignored",
        "× 3-hour response",
        "× Manual follow-up",
        "× Lost clients",
        "× CRM chaos",
    ]
    pain_font = fnt(FONT_EN_BOLD, 28)
    for i, pain in enumerate(pains):
        pt = clamp(t * 5 - i * 0.3 - 0.2, 0, 1)
        pa = int(pt * 200)
        d.text((bx + 10, by + i * 72), pain, font=pain_font, fill=(*RED_PAIN, pa))

    # RIGHT: AFTER
    rx = W // 2 + 30
    d.text((W // 4 * 3, by - 70), "AFTER", font=fnt(FONT_EN_BOLD, 42), fill=(*GREEN_WA, left_a), anchor="mm")
    d.text((W // 4 * 3, by - 20), arabic_text("مع AI"), font=fnt(FONT_AR_BOLD, 30),
           fill=(*SILVER, left_a), anchor="mm")

    wins = [
        "✓ Instant reply",
        "✓ 24/7 response",
        "✓ Auto follow-up",
        "✓ 3× more closings",
        "✓ CRM synced",
    ]
    for i, win in enumerate(wins):
        pt = clamp(t * 5 - i * 0.3 - 0.5, 0, 1)
        pa = int(pt * 230)
        d.text((rx + 10, by + i * 72), win, font=pain_font, fill=(*GREEN_WA, pa))

    # Center metrics block
    met_y = by + 420
    metrics = [
        ("3×", "More Leads Closed"),
        ("0s", "Response Delay"),
        ("100%", "Leads Captured"),
    ]
    mw = (W - 80) // 3
    for i, (val, lbl) in enumerate(metrics):
        mt = clamp(t * 3 - i * 0.4 - 0.8, 0, 1)
        ma = int(ease_out(mt) * 255)
        mx = 40 + i * mw + mw // 2

        # Glow bg
        d.ellipse([mx - 80, met_y - 20, mx + 80, met_y + 140], fill=(20, 80, 60, int(ma * 0.4)))
        d.text((mx, met_y + 40), val, font=fnt(FONT_EN_BOLD, 72), fill=(*GOLD, ma), anchor="mm")
        d.text((mx, met_y + 95), lbl, font=fnt(FONT_EN_REG, 24), fill=(*SILVER, ma), anchor="mm")

    # Big bottom line
    if t > 0.7:
        bt = ease_out((t - 0.7) / 0.3)
        ba = int(bt * 255)
        d.text((W // 2, 1650), arabic_text("لا تخسر عميلاً آخر أبداً"),
               font=fnt(FONT_AR_BOLD, 56), fill=(*GOLD, ba), anchor="mm")
        d.text((W // 2, 1730), "NEVER MISS A LEAD AGAIN",
               font=fnt(FONT_EN_BOLD, 36), fill=(*WHITE_DIM, ba), anchor="mm")

    # Top heading
    d.text((W // 2, 100), "BUSINESS TRANSFORMATION",
           font=fnt(FONT_EN_BOLD, 44), fill=(*GOLD, la), anchor="mm")
    d.text((W // 2, 160), arabic_text("كيف يتغير عملك بالكامل"),
           font=fnt(FONT_AR_BOLD, 34), fill=(*WHITE_DIM, la), anchor="mm")

    return img


def scene_cta(f, total=120, offset=0):
    """26-30s: Powerful CTA."""
    t = f / total
    img = make_base_bg(t, scene_tint=(20, 15, 5))
    d = ImageDraw.Draw(img, "RGBA")

    la = int(ease_out(min(t * 2.5, 1)) * 255)

    # Golden glow from center
    for r in range(700, 50, -80):
        a = int(la * 0.12 * (700 - r) / 700)
        d.ellipse([W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r],
                  fill=(*GOLD[:3], a))

    # Logo area
    logo_y = 380
    d.ellipse([W // 2 - 90, logo_y - 90, W // 2 + 90, logo_y + 90],
              fill=NAVY_MID, outline=GOLD, width=3)

    # AI icon in logo
    fn_logo = fnt(FONT_EN_BOLD, 52)
    d.text((W // 2, logo_y), "AI", font=fn_logo, fill=GOLD, anchor="mm")

    # Rotating gold ring around logo
    for angle in range(0, 360, 15):
        rad = math.radians(angle + t * 180)
        px = W // 2 + int(105 * math.cos(rad))
        py = logo_y + int(105 * math.sin(rad))
        dot_a = int(la * 0.6 * (0.5 + 0.5 * math.sin(rad * 3)))
        d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(*GOLD, dot_a))

    # Brand name
    brand_y = logo_y + 140
    d.text((W // 2, brand_y), "PropAI",
           font=fnt(FONT_EN_BOLD, 82), fill=(*WHITE, la), anchor="mm")
    d.text((W // 2, brand_y + 90), arabic_text("نظام الذكاء الاصطناعي للعقارات"),
           font=fnt(FONT_AR_BOLD, 40), fill=(*GOLD, la), anchor="mm")

    # Divider
    dw = int(lerp(0, 600, ease_out(min(t * 3, 1))))
    d.rectangle([W // 2 - dw // 2, brand_y + 150, W // 2 + dw // 2, brand_y + 153],
                fill=(*GOLD, la))

    # Key value props
    props = [
        ("🤖", "AI-Powered WhatsApp Agent"),
        ("🏠", "Instant Property Matching"),
        ("📊", "Automated CRM Updates"),
    ]
    prop_y = brand_y + 190
    for i, (icon, text) in enumerate(props):
        pt = clamp(t * 4 - i * 0.3 - 0.5, 0, 1)
        pa = int(ease_out(pt) * 230)
        d.text((W // 2 - 220, prop_y + i * 68), icon, font=fnt(FONT_EN_BOLD, 36), fill=(*WHITE, pa))
        d.text((W // 2 - 160, prop_y + i * 68 + 6), text, font=fnt(FONT_EN_BOLD, 30), fill=(*WHITE_DIM, pa))

    # CTA button
    cta_y = prop_y + 260
    btn_pulse = 0.92 + 0.08 * math.sin(t * math.pi * 8)
    btn_w, btn_h = int(700 * btn_pulse), int(120 * btn_pulse)
    btn_x = W // 2 - btn_w // 2
    d.rounded_rectangle([btn_x, cta_y, btn_x + btn_w, cta_y + btn_h],
                          radius=btn_h // 2, fill=(*GOLD, la))
    d.text((W // 2, cta_y + btn_h // 2),
           arabic_text("ابدأ تجربتك المجانية الآن"),
           font=fnt(FONT_AR_BOLD, 36), fill=(10, 8, 2, 240), anchor="mm")

    # Subtext CTA
    cta2_y = cta_y + btn_h + 40
    d.text((W // 2, cta2_y), "Start Free Today  •  No Setup Required",
           font=fnt(FONT_EN_REG, 28), fill=(*SILVER, la), anchor="mm")

    # WhatsApp contact
    if t > 0.5:
        ct = ease_out((t - 0.5) / 0.5)
        ca = int(ct * 220)
        wa_y = cta2_y + 90
        d.rounded_rectangle([W // 2 - 300, wa_y, W // 2 + 300, wa_y + 70],
                              radius=35, fill=(0, 120, 80, ca))
        d.text((W // 2, wa_y + 35), "📱  WhatsApp Us Now",
               font=fnt(FONT_EN_BOLD, 32), fill=(*WHITE, ca), anchor="mm")

    return img


# ─── TRANSITION EFFECTS ──────────────────────────────────────────────────────

def cross_dissolve(img_a, img_b, t):
    a = np.array(img_a).astype(np.float32)
    b = np.array(img_b).astype(np.float32)
    return Image.fromarray((a * (1 - t) + b * t).clip(0, 255).astype(np.uint8))


def flash_frame(color=(255, 255, 255)):
    return Image.new("RGB", (W, H), color)


def motion_blur_h(img, strength=12):
    return img.filter(ImageFilter.GaussianBlur(radius=strength // 3))


def apply_color_grade(img, scene_name):
    """Scene-specific color grading."""
    enhancer_c = ImageEnhance.Color(img)
    enhancer_b = ImageEnhance.Brightness(img)
    enhancer_cn = ImageEnhance.Contrast(img)

    if scene_name == "hook":
        img = enhancer_c.enhance(0.75)
        img = enhancer_cn.enhance(1.3)
    elif scene_name == "whatsapp":
        img = enhancer_c.enhance(0.9)
        img = enhancer_cn.enhance(1.15)
    elif scene_name == "ai":
        img = enhancer_c.enhance(1.1)
        img = enhancer_b.enhance(0.95)
    elif scene_name == "crm":
        img = enhancer_c.enhance(0.95)
    elif scene_name == "transform":
        img = enhancer_c.enhance(1.05)
        img = enhancer_cn.enhance(1.1)
    elif scene_name == "cta":
        img = enhancer_c.enhance(0.9)
        img = enhancer_b.enhance(1.05)
    return img


# ─── MAIN RENDER LOOP ────────────────────────────────────────────────────────
# Scene timing (frame ranges):
# 0    - 119  : Scene 1 – Hook          (0-4s,   120f)
# 120  - 239  : Scene 2 – WhatsApp      (4-8s,   120f)
# 240  - 419  : Scene 3 – AI Matching   (8-14s,  180f)
# 420  - 569  : Scene 4 – CRM           (14-19s, 150f)
# 570  - 779  : Scene 5 – Transform     (19-26s, 210f)
# 780  - 899  : Scene 6 – CTA           (26-30s, 120f)

SCENE_RANGES = [
    (0,    120,  "hook",      scene_hook),
    (120,  240,  "whatsapp",  scene_whatsapp),
    (240,  420,  "ai",        scene_ai_matching),
    (420,  570,  "crm",       scene_crm),
    (570,  780,  "transform", scene_transformation),
    (780,  900,  "cta",       scene_cta),
]

FLASH_FRAMES = {119, 120, 239, 240, 419, 420, 569, 570, 779, 780}
TRANSITION_FRAMES = 12  # overlap for dissolves


def get_scene_frame(f):
    for start, end, name, renderer in SCENE_RANGES:
        if start <= f < end:
            local_f = f - start
            total = end - start
            return renderer(local_f, total, start), name
    return Image.new("RGB", (W, H), BG_DARK), "hook"


def render_all_frames():
    print(f"Rendering {TOTAL_FRAMES} frames at {W}x{H} @ {FPS}fps...")
    particles_inst = Particles(n=60, seed=99)

    prev_img = None
    prev_name = None

    for f in range(TOTAL_FRAMES):
        if f % 30 == 0:
            pct = f / TOTAL_FRAMES * 100
            print(f"  {pct:.0f}% – frame {f}/{TOTAL_FRAMES}")

        img, name = get_scene_frame(f)

        # Color grade per scene
        img = apply_color_grade(img, name)

        # Scene transition flash + dissolve
        if f in FLASH_FRAMES and f > 0 and prev_img is not None:
            if f % 2 == 1:  # flash white on cut
                fl = flash_frame((230, 235, 255))
                img = cross_dissolve(fl, img, 0.5)
        elif prev_img is not None and prev_name != name:
            # We're just past a boundary - check if within transition window
            for start, end, sc_name, _ in SCENE_RANGES:
                if f == start and f > 0:
                    t2 = min((f - start) / TRANSITION_FRAMES, 1)
                    img = cross_dissolve(prev_img, img, ease_in_out(t2))
                    break

        # Camera zoom drift for cinematic feel
        for start, end, sc_name, _ in SCENE_RANGES:
            if start <= f < end:
                local_f = f - start
                total = end - start
                lt = local_f / total
                drift = 1.0 + 0.02 * math.sin(lt * math.pi)
                if sc_name == "hook":
                    # Camera shake during hook
                    shake = camera_shake(f, 5)
                    shake_arr = np.array(img)
                    shake_arr = np.roll(shake_arr, shake[0], axis=1)
                    shake_arr = np.roll(shake_arr, shake[1], axis=0)
                    img = Image.fromarray(shake_arr.astype(np.uint8))
                else:
                    img = zoom_frame(img, drift)
                break

        # Film grain
        img = add_film_grain(img, intensity=10, seed=f)

        # Vignette
        img = add_vignette(img, strength=0.55)

        # Chromatic aberration on flash moments
        if f in FLASH_FRAMES:
            img = chromatic_aberration(img, shift=5)

        # Particles overlay
        particles_inst.step()
        img_rgba = img.convert("RGBA")
        particles_inst.draw(img_rgba)
        img = img_rgba.convert("RGB")

        prev_img = img
        prev_name = name

        # Save frame
        frame_path = os.path.join(OUT_DIR, f"frame_{f:05d}.png")
        img.save(frame_path, "PNG", optimize=False)

    print("Frame rendering complete!")


def compile_video():
    out_path = os.path.join(os.path.dirname(__file__), "propai_real_estate.mp4")
    frame_pattern = os.path.join(OUT_DIR, "frame_%05d.png")

    # Use ffmpeg to compile frames + add audio
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", frame_pattern,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "16",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        out_path
    ]
    print("Compiling video with ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg error:", result.stderr[-1000:])
    else:
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"Video compiled: {out_path} ({size_mb:.1f} MB)")
    return out_path


if __name__ == "__main__":
    render_all_frames()
    compile_video()
    print("Done! Output: video_project/propai_real_estate.mp4")
