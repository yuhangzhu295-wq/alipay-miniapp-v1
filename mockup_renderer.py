# -*- coding: utf-8 -*-
"""
证件照生成器 - 高保真 UI Mockup 渲染器
Generates 6 mobile UI mockup images for WeChat mini-program.
"""

from PIL import Image, ImageDraw, ImageFont
import os, math

OUTPUT_DIR = r"C:\Users\zyu33\.openclaw-workspaces\assistant\projects\证件照生成器\mockups"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Colors ──
C_PRIMARY = "#667eea"
C_SECONDARY = "#764ba2"
C_GRADIENT_S = "#667eea"
C_GRADIENT_E = "#764ba2"
C_BG = "#f4f6fc"
C_WHITE = "#ffffff"
C_BLACK = "#1a1a2e"
C_GRAY = "#8e8ea0"
C_LIGHT_GRAY = "#f0f2f8"
C_BORDER = "#e0e5f2"
C_TAB_INACTIVE = "#999999"
C_GREEN = "#4ade80"
C_ORANGE = "#fb923c"
C_RED = "#ef4444"
C_TEAL = "#14b8a6"
C_YELLOW = "#facc15"
C_CARD_SHADOW = (0, 0, 0, 20)

# ── Dimensions (iPhone 15 Pro scale: 393x852 pt -> 2x = 786x1704, 3x = 1179x2556)
W = 1179  # 3x
H = 2556
SCALE = 3
PT = lambda x: int(x * SCALE)  # Convert from pt to px

def find_font(size_pt):
    """Find best available Chinese font."""
    size_px = PT(size_pt)
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",      # Microsoft YaHei
        r"C:\Windows\Fonts\msyhbd.ttc",     # Microsoft YaHei Bold
        r"C:\Windows\Fonts\msyhl.ttc",      # Microsoft YaHei Light
        r"C:\Windows\Fonts\SimSun.ttc",     # SimSun
        r"C:\Windows\Fonts\SIMLI.TTF",      # LiSu
        r"C:\Windows\Fonts\STXINWEI.TTF",   # STXinwei
        r"C:\Windows\Fonts\Arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size_px)
            except:
                continue
    return ImageFont.load_default()


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """Draw rounded rectangle."""
    x1, y1, x2, y2 = xy
    r = min(radius, (x2-x1)//2, (y2-y1)//2)
    draw.pieslice([x1, y1, x1+2*r, y1+2*r], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x2-2*r, y1, x2, y1+2*r], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x1, y2-2*r, x1+2*r, y2], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x2-2*r, y2-2*r, x2, y2], 0, 90, fill=fill, outline=outline, width=width)
    draw.rectangle([x1+r, y1, x2-r, y2], fill=fill, outline=outline, width=width)
    draw.rectangle([x1, y1+r, x2, y2-r], fill=fill, outline=outline, width=width)


def draw_gradient_rounded(draw, xy, radius, color_start, color_end):
    """Draw rounded rectangle with vertical gradient."""
    x1, y1, x2, y2 = xy
    steps = 100
    h_step = (y2 - y1) / steps
    r = min(radius, (x2-x1)//2, (y2-y1)//2)
    
    def lerp_color(c1, c2, t):
        r1, g1, b1 = int(c1[1:3],16), int(c1[3:5],16), int(c1[5:7],16)
        r2, g2, b2 = int(c2[1:3],16), int(c2[3:5],16), int(c2[5:7],16)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"
    
    for i in range(steps):
        cy1 = y1 + i * h_step
        cy2 = cy1 + h_step + 1
        color = lerp_color(color_start, color_end, i/steps)
        # Draw as strips, clipping at corners
        if cy1 < y1 + r:
            # top rounded area
            pass  # skip, draw full rect below
        elif cy2 > y2 - r:
            pass
        else:
            draw.rectangle([x1, cy1, x2, min(cy2, y2)], fill=color)
    
    # Now draw full rect for middle area
    mid_c = lerp_color(color_start, color_end, 0.5)
    
    # Better approach: draw the whole rounded rect with gradient
    # Use the middle fill and let the corner pieslice handle the rest
    # Actually let's use a simpler approach - draw the main rectangle with middle gradient
    
    # Top rounded corners
    top_c = color_start
    draw.pieslice([x1, y1, x1+2*r, y1+2*r], 180, 270, fill=top_c)
    draw.pieslice([x2-2*r, y1, x2, y1+2*r], 270, 360, fill=top_c)
    
    # Bottom rounded corners
    bot_c = color_end
    draw.pieslice([x1, y2-2*r, x1+2*r, y2], 90, 180, fill=bot_c)
    draw.pieslice([x2-2*r, y2-2*r, x2, y2], 0, 90, fill=bot_c)
    
    # Top strip
    draw.rectangle([x1+r, y1, x2-r, y1+r], fill=top_c)
    
    # Gradient middle
    for i in range(steps):
        cy1 = y1 + r + i * ((y2-y1-2*r)/steps)
        cy2 = cy1 + (y2-y1-2*r)/steps + 1
        color = lerp_color(color_start, color_end, i/steps)
        draw.rectangle([x1+r, cy1, x2-r, min(cy2, y2-r)], fill=color)
    
    # Bottom strip
    draw.rectangle([x1+r, y2-r, x2-r, y2], fill=bot_c)
    
    # Left/right edges
    for i in range(steps):
        ly = y1 + r + i * ((y2-y1-2*r)/steps)
        ly2 = ly + (y2-y1-2*r)/steps + 1
        color = lerp_color(color_start, color_end, i/steps)
        draw.rectangle([x1, ly, x1+r, min(ly2, y2-r)], fill=color)
        draw.rectangle([x2-r, ly, x2, min(ly2, y2-r)], fill=color)


def draw_shadow(draw, xy, radius, alpha=30):
    """Draw soft shadow under a rounded rect."""
    x1, y1, x2, y2 = xy
    offset = PT(4)
    blur = PT(8)
    for i in range(blur, 0, -2):
        a = alpha * (blur - i) // blur
        draw_rounded_rect(draw, 
            [x1+offset-i, y1+offset-i, x2+offset+i, y2+offset+i], 
            radius + i, 
            fill=f"rgba(0,0,0,{a/255:.2f})" if False else None,
            outline=f"rgba(0,0,0,{a//20})" if False else None)


def draw_card(draw, xy, radius=PT(16), shadow=True):
    """Draw a white card with shadow."""
    x1, y1, x2, y2 = xy
    if shadow:
        # Draw shadow
        for i in range(PT(6), 0, -1):
            alpha = 8 - i
            s = PT(1)
            draw_rounded_rect(draw, 
                [x1+i*s, y1+i*s, x2-i*s, y2-i*s], 
                radius + i, 
                fill=f"rgba(0,0,0,{alpha*.7:.0f})" if alpha > 0 else None)
    draw_rounded_rect(draw, xy, radius, fill=C_WHITE)


def draw_text_centered(draw, xy, text, font, fill=C_BLACK):
    """Draw text centered in rect."""
    x1, y1, x2, y2 = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    cx = (x1 + x2 - tw) // 2
    cy = (y1 + y2 - th) // 2
    draw.text((cx, cy), text, font=font, fill=fill)


def draw_tab_bar(draw, tabs, selected_idx=0):
    """Draw bottom tab bar."""
    bar_y = H - PT(120)
    bar_h = PT(120)
    safe_bottom = PT(34)
    
    # Background
    draw_rounded_rect(draw, [0, bar_y, W, H], 0, fill=C_WHITE)
    # Top border
    draw.line([(0, bar_y), (W, bar_y)], fill=C_BORDER, width=PT(1))
    
    tab_w = W // len(tabs)
    font_tab = find_font(11)
    font_tab_active = find_font(11)
    
    for i, (name, icon) in enumerate(tabs):
        tx = i * tab_w
        ty = bar_y + PT(8)
        
        is_active = i == selected_idx
        color = C_PRIMARY if is_active else C_TAB_INACTIVE
        
        # Icon circle
        icon_r = PT(18)
        icon_cx = tx + tab_w // 2
        icon_cy = ty + icon_r + PT(2)
        if is_active:
            # Filled circle for active
            draw_rounded_rect(draw, [icon_cx-icon_r, icon_cy-icon_r, icon_cx+icon_r, icon_cy+icon_r], icon_r, fill=color)
            draw.text((icon_cx-PT(6), icon_cy-PT(7)), icon, font=find_font(10), fill=C_WHITE)
        else:
            # Outline circle for inactive
            draw_rounded_rect(draw, [icon_cx-icon_r, icon_cy-icon_r, icon_cx+icon_r, icon_cy+icon_r], icon_r, fill=None, outline=color, width=PT(2))
            draw.text((icon_cx-PT(6), icon_cy-PT(7)), icon, font=find_font(10), fill=color)
        
        # Label
        draw_text_centered(draw, [tx, icon_cy+icon_r+PT(4), tx+tab_w, bar_y+PT(56)], name, font_tab, fill=color)


# ═══════════════════════════════════════════
#  PAGE 1: 首页 (Home)
# ═══════════════════════════════════════════
def render_home():
    img = Image.new('RGBA', (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    
    # ── Status bar ──
    draw_rounded_rect(draw, [0, 0, W, PT(100)], 0, fill=C_WHITE)
    font_time = find_font(14)
    draw.text((PT(30), PT(10)), "9:41", font=font_time, fill=C_BLACK)
    font_status = find_font(10)
    draw.text((W-PT(90), PT(12)), "📶 🔋", font=font_status, fill=C_BLACK)
    
    # ── Service notice ──
    notice_y = PT(100)
    draw_rounded_rect(draw, [0, notice_y, W, notice_y+PT(50)], 0, fill="#eef1ff")
    font_small = find_font(11)
    draw_text_centered(draw, [0, notice_y, W, notice_y+PT(50)], "📋 证件照生成器小程序提供服务", font_small, fill=C_PRIMARY)
    
    # ── Hero area ──
    hero_y = notice_y + PT(60)
    draw_rounded_rect(draw, [PT(30), hero_y, W-PT(30), hero_y+PT(280)], PT(24), fill=C_WHITE)
    
    font_title = find_font(36)
    draw.text((PT(60), hero_y+PT(40)), "证件照生成器", font=font_title, fill=C_BLACK)
    font_sub = find_font(18)
    draw.text((PT(60), hero_y+PT(100)), "3秒快速生成", font=font_sub, fill=C_GRAY)
    
    # Hero illustration (simple ID card icon)
    ill_x, ill_y = W-PT(280), hero_y+PT(50)
    draw_rounded_rect(draw, [ill_x, ill_y, ill_x+PT(180), ill_y+PT(190)], PT(16), fill="#eef1ff")
    # ID card shape inside
    cx, cy = ill_x+PT(90), ill_y+PT(95)
    draw_rounded_rect(draw, [cx-PT(50), cy-PT(35), cx+PT(50), cy+PT(35)], PT(6), fill=C_PRIMARY)
    draw.text((cx-PT(12), cy-PT(10)), "📷", font=find_font(28), fill=C_WHITE)
    
    # ── Hot specs section ──
    hot_y = hero_y + PT(320)
    # Section header
    font_section = find_font(16)
    font_more = find_font(12)
    draw.text((PT(40), hot_y), "🔥 热门证件照", font=font_section, fill=C_BLACK)
    draw.text((W-PT(170), hot_y+PT(4)), "更多规格 ›", font=font_more, fill=C_PRIMARY)
    
    # 3x2 grid of hot spec cards
    hot_specs = [
        ("一寸", "25×35mm", "📷"),
        ("二寸", "35×49mm", "📷"),
        ("大一寸", "33×48mm", "📷"),
        ("小一寸", "22×32mm", "📷"),
        ("简历照片", "25×35mm", "📷"),
        ("教师资格证", "报名照", "📷"),
    ]
    card_w = (W - PT(80)) // 3
    card_h = PT(160)
    card_gap = PT(10)
    
    for i, (name, size, icon) in enumerate(hot_specs):
        col = i % 3
        row = i // 3
        cx = PT(30) + col * (card_w + card_gap)
        cy = hot_y + PT(50) + row * (card_h + card_gap)
        
        draw_card(draw, [cx, cy, cx+card_w, cy+card_h], PT(12))
        
        # Icon circle
        ic = cx + card_w//2
        draw_rounded_rect(draw, [ic-PT(20), cy+PT(20), ic+PT(20), cy+PT(60)], PT(20), fill="#eef1ff")
        draw.text((ic-PT(10), cy+PT(23)), icon, font=find_font(18), fill=C_PRIMARY)
        
        # Name
        font_card = find_font(13)
        draw_text_centered(draw, [cx, cy+PT(65), cx+card_w, cy+PT(95)], name, font_card, fill=C_BLACK)
        # Size
        font_card_s = find_font(10)
        draw_text_centered(draw, [cx, cy+PT(95), cx+card_w, cy+PT(120)], size, font_card_s, fill=C_GRAY)
    
    # ── Categories ──
    cat_y = hot_y + PT(50) + 2 * (card_h + card_gap) + PT(30)
    draw.text((PT(40), cat_y), "📂 常用分类", font=font_section, fill=C_BLACK)
    
    cat_cards = [
        ("常用寸照", "一寸 二寸 大一寸 小一寸", "📸", C_GRADIENT_S, C_SECONDARY),
        ("学历/语言考试", "四六级 考研 雅思 托福", "🎓", "#06b6d4", "#14b8a6"),
    ]
    cat_h = PT(160)
    for i, (title, subtitle, icon, cs, ce) in enumerate(cat_cards):
        cy = cat_y + PT(50) + i * (cat_h + PT(12))
        draw_gradient_rounded(draw, [PT(30), cy, W-PT(30), cy+cat_h], PT(16), cs, ce)
        
        # Icon
        draw.text((PT(60), cy+PT(35)), icon, font=find_font(32), fill=C_WHITE)
        # Title
        draw.text((PT(120), cy+PT(40)), title, font=find_font(20), fill=C_WHITE)
        # Subtitle
        draw.text((PT(120), cy+PT(80)), subtitle, font=find_font(12), fill="rgba(255,255,255,0.8)" if False else "#ffffffaa")
        # Arrow
        draw.text((W-PT(80), cy+PT(45)), "›", font=find_font(28), fill=C_WHITE)
    
    # ── Tab bar ──
    draw_tab_bar(draw, [
        ("首页", "🏠"),
        ("小工具", "🔧"),
        ("电子照", "📄"),
        ("我的", "👤"),
    ], selected_idx=0)
    
    img.save(os.path.join(OUTPUT_DIR, "mockup_home.png"))
    print("✅ mockup_home.png")


# ═══════════════════════════════════════════
#  PAGE 2: 小工具 (Tools)
# ═══════════════════════════════════════════
def render_tools():
    img = Image.new('RGBA', (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    
    # Status bar
    draw_rounded_rect(draw, [0, 0, W, PT(100)], 0, fill=C_WHITE)
    draw.text((PT(30), PT(10)), "9:41", font=find_font(14), fill=C_BLACK)
    draw.text((W-PT(90), PT(12)), "📶 🔋", font=find_font(10), fill=C_BLACK)
    
    # Nav bar
    nav_y = PT(100)
    draw_rounded_rect(draw, [0, nav_y, W, nav_y+PT(80)], 0, fill=C_WHITE)
    draw.text((PT(40), nav_y+PT(20)), "实用工具", font=find_font(20), fill=C_BLACK)
    draw.text((W-PT(80), nav_y+PT(20)), "⋯", font=find_font(24), fill=C_GRAY)
    draw.line([(0, nav_y+PT(80)), (W, nav_y+PT(80))], fill=C_BORDER, width=PT(1))
    
    # 3-column grid of tools
    tools = [
        ("证件照更换底色", "一键更换背景色", "🎨", "#eef1ff", C_PRIMARY),
        ("自定义尺寸", "自由裁剪调整", "📐", "#fef3c7", "#f59e0b"),
        ("图片编辑", "裁剪/调色/美颜", "✏️", "#dbeafe", "#3b82f6"),
        ("图片格式转换", "JPG/PNG互转", "🔄", "#fce7f3", "#ec4899"),
        ("黑白图片上色", "AI智能上色", "🌈", "#e0f2fe", "#0284c7"),
        ("图片加水印", "文字/图片水印", "💧", "#f0fdf4", "#22c55e"),
        ("自定义排版", "多尺寸排版", "📋", "#fdf4ff", "#a855f7"),
        ("职业形象照", "专业形象照", "👔", "#fff7ed", "#f97316"),
        ("证件照采集", "批量采集录入", "📸", "#f0f9ff", "#0ea5e9"),
    ]
    
    grid_pad = PT(20)
    grid_w = (W - grid_pad * 4) // 3
    grid_h = PT(200)
    
    top_y = nav_y + PT(100)
    for i, (name, desc, icon, bg, color) in enumerate(tools):
        col = i % 3
        row = i // 3
        cx = grid_pad + col * (grid_w + grid_pad)
        cy = top_y + row * (grid_h + grid_pad)
        
        draw_card(draw, [cx, cy, cx+grid_w, cy+grid_h], PT(12))
        
        # Icon circle
        ic = cx + grid_w//2
        draw_rounded_rect(draw, [ic-PT(22), cy+PT(18), ic+PT(22), cy+PT(62)], PT(22), fill=bg)
        draw.text((ic-PT(11), cy+PT(21)), icon, font=find_font(20), fill=color)
        
        # Name
        draw_text_centered(draw, [cx+PT(5), cy+PT(70), cx+grid_w-PT(5), cy+PT(105)], name, find_font(11), fill=C_BLACK)
        # Description
        draw_text_centered(draw, [cx+PT(5), cy+PT(105), cx+grid_w-PT(5), cy+PT(135)], desc, find_font(8), fill=C_GRAY)
        
        # HOT badge for custom size
        if i == 1:
            draw_rounded_rect(draw, [cx+grid_w-PT(50), cy+PT(8), cx+grid_w-PT(8), cy+PT(28)], PT(6), fill=C_RED)
            draw_text_centered(draw, [cx+grid_w-PT(50), cy+PT(8), cx+grid_w-PT(8), cy+PT(28)], "HOT", find_font(8), fill=C_WHITE)
    
    # Floating share button (bottom-right)
    btn_r = PT(28)
    btn_x = W - PT(50)
    btn_y = H - PT(300)
    draw_rounded_rect(draw, [btn_x-btn_r, btn_y-btn_r, btn_x+btn_r, btn_y+btn_r], btn_r, fill=C_PRIMARY)
    draw.text((btn_x-PT(12), btn_y-PT(10)), "📤", font=find_font(20), fill=C_WHITE)
    
    # Tab bar
    draw_tab_bar(draw, [
        ("首页", "🏠"),
        ("小工具", "🔧"),
        ("电子照", "📄"),
        ("我的", "👤"),
    ], selected_idx=1)
    
    img.save(os.path.join(OUTPUT_DIR, "mockup_tools.png"))
    print("✅ mockup_tools.png")


# ═══════════════════════════════════════════
#  PAGE 3: 规格搜索页 (Specs)
# ═══════════════════════════════════════════
def render_specs():
    img = Image.new('RGBA', (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    
    # Status bar
    draw_rounded_rect(draw, [0, 0, W, PT(100)], 0, fill=C_WHITE)
    draw.text((PT(30), PT(10)), "9:41", font=find_font(14), fill=C_BLACK)
    draw.text((W-PT(90), PT(12)), "📶 🔋", font=find_font(10), fill=C_BLACK)
    
    # Nav bar
    nav_y = PT(100)
    draw_rounded_rect(draw, [0, nav_y, W, nav_y+PT(80)], 0, fill=C_WHITE)
    draw.text((PT(30), nav_y+PT(18)), "←", font=find_font(24), fill=C_BLACK)
    draw.text((PT(100), nav_y+PT(22)), "搜索证件照规格", font=find_font(18), fill=C_BLACK)
    draw.text((W-PT(80), nav_y+PT(20)), "⋯", font=find_font(24), fill=C_GRAY)
    draw.line([(0, nav_y+PT(80)), (W, nav_y+PT(80))], fill=C_BORDER, width=PT(1))
    
    # Search bar
    search_y = nav_y + PT(100)
    draw_rounded_rect(draw, [PT(30), search_y, W-PT(30), search_y+PT(60)], PT(30), fill=C_WHITE)
    draw.text((PT(60), search_y+PT(15)), "🔍", font=find_font(18), fill=C_GRAY)
    draw.text((PT(100), search_y+PT(16)), "搜索规格名称、尺寸或用途", font=find_font(12), fill=C_GRAY)
    draw_rounded_rect(draw, [W-PT(160), search_y+PT(10), W-PT(50), search_y+PT(50)], PT(20), fill="#eef1ff")
    draw_text_centered(draw, [W-PT(160), search_y+PT(10), W-PT(50), search_y+PT(50)], "🗂️ 筛选", find_font(11), fill=C_PRIMARY)
    
    # Spec cards grid (2 columns)
    specs = [
        ("一寸", "25×35mm", "295×413px", "#667eea", ["白","蓝","红"]),
        ("二寸", "35×49mm", "413×579px", "#764ba2", ["白","蓝","红"]),
        ("教师资格证", "多种尺寸", "点选后选择", "#f59e0b", ["白","蓝","红"]),
        ("自定义尺寸", "自己设置", "🔥 热门", "#ec4899", []),
        ("计算机等级考试", "33×48mm", "390×567px", "#06b6d4", ["白","蓝"]),
        ("初级会计考试", "25×35mm", "295×413px", "#14b8a6", ["白","蓝","红"]),
        ("驾驶证", "多种尺寸", "点选后选择", "#f97316", ["白","蓝"]),
        ("英语四六级", "33×48mm", "390×567px", "#3b82f6", ["白","蓝"]),
        ("大学生图像采集", "41×54mm", "480×640px", "#a855f7", ["白","蓝"]),
        ("成人自考", "25×35mm", "295×413px", "#22c55e", ["白","蓝","红"]),
    ]
    
    card_w2 = (W - PT(75)) // 2
    card_h2 = PT(150)
    list_y = search_y + PT(80)
    
    for i, (name, size, px, color, colors) in enumerate(specs):
        col = i % 2
        row = i // 2
        cx = PT(25) + col * (card_w2 + PT(10))
        cy = list_y + row * (card_h2 + PT(10))
        
        draw_card(draw, [cx, cy, cx+card_w2, cy+card_h2], PT(14))
        
        # Left: icon circle
        draw_rounded_rect(draw, [cx+PT(15), cy+PT(20), cx+PT(65), cy+PT(70)], PT(25), fill="#eef1ff")
        draw.text((cx+PT(22), cy+PT(25)), "📷", font=find_font(22), fill=color)
        
        # Name
        draw.text((cx+PT(80), cy+PT(18)), name, font=find_font(14), fill=C_BLACK)
        # Size
        draw.text((cx+PT(80), cy+PT(50)), size, font=find_font(10), fill=C_GRAY)
        # PX
        draw.text((cx+PT(80), cy+PT(72)), px, font=find_font(10), fill=color)
        
        # Color dots
        if colors:
            dot_x = cx + card_w2 - PT(90)
            for j, c in enumerate(colors):
                dot_color = {"白": "#ffffff", "蓝": "#3b82f6", "红": "#ef4444"}.get(c, "#ddd")
                dot_cy = cy + PT(110)
                dot_cx = dot_x + j * PT(28)
                if c == "白":
                    draw_rounded_rect(draw, [dot_cx, dot_cy, dot_cx+PT(18), dot_cy+PT(18)], PT(9), fill=dot_color, outline=C_BORDER, width=PT(2))
                else:
                    draw_rounded_rect(draw, [dot_cx, dot_cy, dot_cx+PT(18), dot_cy+PT(18)], PT(9), fill=dot_color)
    
    img.save(os.path.join(OUTPUT_DIR, "mockup_specs.png"))
    print("✅ mockup_specs.png")


# ═══════════════════════════════════════════
#  PAGE 4: 生成结果页 (Generate/Result)
# ═══════════════════════════════════════════
def render_generate():
    img = Image.new('RGBA', (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    
    # Status bar
    draw_rounded_rect(draw, [0, 0, W, PT(100)], 0, fill=C_WHITE)
    draw.text((PT(30), PT(10)), "9:41", font=find_font(14), fill=C_BLACK)
    draw.text((W-PT(90), PT(12)), "📶 🔋", font=find_font(10), fill=C_BLACK)
    
    # Nav bar
    nav_y = PT(100)
    draw_rounded_rect(draw, [0, nav_y, W, nav_y+PT(80)], 0, fill=C_WHITE)
    draw.text((PT(40), nav_y+PT(20)), "证件照生成器", font=find_font(18), fill=C_BLACK)
    draw.text((W-PT(80), nav_y+PT(20)), "⋯", font=find_font(24), fill=C_GRAY)
    draw.line([(0, nav_y+PT(80)), (W, nav_y+PT(80))], fill=C_BORDER, width=PT(1))
    
    # Preview card
    prev_y = nav_y + PT(30)
    draw_card(draw, [PT(80), prev_y, W-PT(80), prev_y+PT(340)], PT(20))
    draw_rounded_rect(draw, [PT(80), prev_y, W-PT(80), prev_y+PT(340)], PT(20), fill="#667eea")
    
    # ID photo white rectangle (simulating a generated photo on blue background)
    ph_w, ph_h = PT(130), PT(170)
    ph_cx, ph_cy = W//2, prev_y + PT(160)
    draw_rounded_rect(draw, [ph_cx-ph_w//2, ph_cy-ph_h//2, ph_cx+ph_w//2, ph_cy+ph_h//2], PT(8), fill=C_WHITE)
    draw_rounded_rect(draw, [ph_cx-PT(30), ph_cy-PT(40), ph_cx+PT(30), ph_cy+PT(40)], PT(10), fill="#667eea80")
    
    # Size label under photo
    draw_text_centered(draw, [PT(80), prev_y+PT(290), W-PT(80), prev_y+PT(340)], "25×35mm | 295×413px", find_font(11), fill=C_WHITE)
    
    # Action buttons
    act_y = prev_y + PT(370)
    btn_w = (W - PT(90)) // 2
    btn_h = PT(120)
    
    actions = [
        ("修改底色", "已有底色修改", "🎨", "#eef1ff", C_PRIMARY),
        ("图片编辑", "修改kb与dpi", "✏️", "#dbeafe", "#3b82f6"),
    ]
    for i, (title, desc, icon, bg, color) in enumerate(actions):
        cx = PT(30) + i * (btn_w + PT(10))
        draw_card(draw, [cx, act_y, cx+btn_w, act_y+btn_h], PT(14))
        
        draw_rounded_rect(draw, [cx+PT(15), act_y+PT(20), cx+PT(55), act_y+PT(60)], PT(20), fill=bg)
        draw.text((cx+PT(20), act_y+PT(22)), icon, font=find_font(18), fill=color)
        
        draw.text((cx+PT(70), act_y+PT(22)), title, font=find_font(14), fill=C_BLACK)
        draw.text((cx+PT(70), act_y+PT(52)), desc, font=find_font(10), fill=C_GRAY)
        
        # Arrow right
        draw.text((cx+btn_w-PT(35), act_y+PT(40)), "›", font=find_font(20), fill=C_GRAY)
    
    # Popular sizes section
    pop_y = act_y + btn_h + PT(30)
    font_section = find_font(16)
    draw.text((PT(40), pop_y), "🔥 热门尺寸", font=font_section, fill=C_BLACK)
    
    sizes = [
        ("二寸", "35×49mm | 413×579px"),
        ("小一寸", "22×32mm | 260×378px"),
        ("小二寸", "35×45mm | 413×531px"),
        ("教师资格证", "多种规格"),
    ]
    for i, (name, detail) in enumerate(sizes):
        sy = pop_y + PT(50) + i * PT(85)
        draw_card(draw, [PT(30), sy, W-PT(30), sy+PT(75)], PT(12))
        draw.text((PT(50), sy+PT(15)), name, font=find_font(14), fill=C_BLACK)
        draw.text((PT(50), sy+PT(42)), detail, font=find_font(10), fill=C_GRAY)
        # Action circle on right
        draw_rounded_rect(draw, [W-PT(100), sy+PT(18), W-PT(60), sy+PT(58)], PT(20), fill="#eef1ff")
        draw.text((W-PT(87), sy+PT(23)), "→", font=find_font(18), fill=C_PRIMARY)
    
    # Tab bar
    draw_tab_bar(draw, [
        ("首页", "🏠"),
        ("小工具", "🔧"),
        ("电子照", "📄"),
        ("我的", "👤"),
    ], selected_idx=0)
    
    img.save(os.path.join(OUTPUT_DIR, "mockup_generate.png"))
    print("✅ mockup_generate.png")


# ═══════════════════════════════════════════
#  PAGE 5: 电子照 (Photos)
# ═══════════════════════════════════════════
def render_photos():
    img = Image.new('RGBA', (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    
    # Status bar
    draw_rounded_rect(draw, [0, 0, W, PT(100)], 0, fill=C_WHITE)
    draw.text((PT(30), PT(10)), "9:41", font=find_font(14), fill=C_BLACK)
    draw.text((W-PT(90), PT(12)), "📶 🔋", font=find_font(10), fill=C_BLACK)
    
    # Nav bar
    nav_y = PT(100)
    draw_rounded_rect(draw, [0, nav_y, W, nav_y+PT(80)], 0, fill=C_WHITE)
    draw.text((PT(40), nav_y+PT(20)), "我的电子照", font=find_font(18), fill=C_BLACK)
    draw.text((W-PT(80), nav_y+PT(20)), "⋯", font=find_font(24), fill=C_GRAY)
    draw.line([(0, nav_y+PT(80)), (W, nav_y+PT(80))], fill=C_BORDER, width=PT(1))
    
    # Warning banner
    warn_y = nav_y + PT(100)
    draw_rounded_rect(draw, [PT(30), warn_y, W-PT(30), warn_y+PT(80)], PT(14), fill="#fef3c7")
    draw.text((PT(55), warn_y+PT(18)), "⚠️", font=find_font(18), fill="#f59e0b")
    draw.text((PT(90), warn_y+PT(12)), "本应用不提供照片永久存储", font=find_font(12), fill="#92400e")
    draw.text((PT(90), warn_y+PT(42)), "电子照自保存之日起7天后会删除，请尽早提取", font=find_font(10), fill="#a16207")
    
    # Empty state
    empty_y = warn_y + PT(130)
    # Decorative icon
    draw_rounded_rect(draw, [W//2-PT(70), empty_y, W//2+PT(70), empty_y+PT(140)], PT(35), fill="#eef1ff")
    draw.text((W//2-PT(25), empty_y+PT(35)), "📄", font=find_font(40), fill=C_PRIMARY)
    
    draw.text((W//2-PT(120), empty_y+PT(170)), "您当前还没有电子照哦~", font=find_font(16), fill=C_GRAY)
    
    # CTA button
    btn_y = empty_y + PT(260)
    btn_w2 = PT(350)
    draw_gradient_rounded(draw, 
        [W//2-btn_w2//2, btn_y, W//2+btn_w2//2, btn_y+PT(80)], 
        PT(40), C_GRADIENT_S, C_GRADIENT_E)
    draw_text_centered(draw, [W//2-btn_w2//2, btn_y, W//2+btn_w2//2, btn_y+PT(80)], "📷 立即拍摄", find_font(16), fill=C_WHITE)
    
    # Tab bar
    draw_tab_bar(draw, [
        ("首页", "🏠"),
        ("小工具", "🔧"),
        ("电子照", "📄"),
        ("我的", "👤"),
    ], selected_idx=2)
    
    img.save(os.path.join(OUTPUT_DIR, "mockup_photos.png"))
    print("✅ mockup_photos.png")


# ═══════════════════════════════════════════
#  PAGE 6: 个人中心 (Profile)
# ═══════════════════════════════════════════
def render_profile():
    img = Image.new('RGBA', (W, H), C_BG)
    draw = ImageDraw.Draw(img)
    
    # Status bar
    draw_rounded_rect(draw, [0, 0, W, PT(100)], 0, fill=C_WHITE)
    draw.text((PT(30), PT(10)), "9:41", font=find_font(14), fill=C_BLACK)
    draw.text((W-PT(90), PT(12)), "📶 🔋", font=find_font(10), fill=C_BLACK)
    
    # Nav bar
    nav_y = PT(100)
    draw_rounded_rect(draw, [0, nav_y, W, nav_y+PT(80)], 0, fill=C_WHITE)
    draw.text((PT(40), nav_y+PT(20)), "个人中心", font=find_font(18), fill=C_BLACK)
    draw.text((W-PT(80), nav_y+PT(20)), "⋯", font=find_font(24), fill=C_GRAY)
    draw.line([(0, nav_y+PT(80)), (W, nav_y+PT(80))], fill=C_BORDER, width=PT(1))
    
    # Profile card
    card_y = nav_y + PT(30)
    draw_gradient_rounded(draw, [PT(30), card_y, W-PT(30), card_y+PT(280)], PT(24), C_GRADIENT_S, C_GRADIENT_E)
    
    # Light spot decorations
    draw_rounded_rect(draw, [W-PT(180), card_y+PT(30), W-PT(80), card_y+PT(80)], PT(25), fill="#ffffff15")
    draw_rounded_rect(draw, [PT(60), card_y+PT(200), PT(130), card_y+PT(250)], PT(25), fill="#ffffff08")
    
    # Avatar
    av_r = PT(45)
    av_cx, av_cy = PT(100), card_y + PT(100)
    draw_rounded_rect(draw, [av_cx-av_r, av_cy-av_r, av_cx+av_r, av_cy+av_r], av_r, fill=C_WHITE)
    draw.text((av_cx-PT(17), av_cy-PT(18)), "👤", font=find_font(30), fill=C_PRIMARY)
    
    # Welcome text
    draw.text((PT(170), card_y+PT(75)), "Hi，微信用户", font=find_font(18), fill=C_WHITE)
    draw.text((PT(170), card_y+PT(115)), "欢迎使用证件照生成器", font=find_font(11), fill="#ffffffaa")
    
    # Settings icon (top right of card)
    draw.text((W-PT(90), card_y+PT(30)), "⚙️", font=find_font(18), fill=C_WHITE)
    
    # Menu list
    menu_y = card_y + PT(320)
    menus = [
        ("🛒", "我的订单", "查看已购买订单"),
        ("❓", "常见问题", "使用帮助与解答"),
        ("📸", "拍摄攻略", "拍出完美证件照"),
        ("💬", "联系客服", "在线客服工作时间"),
        ("📤", "分享小程序", "分享给好友"),
    ]
    for i, (icon, title, desc) in enumerate(menus):
        my = menu_y + i * PT(100)
        draw_card(draw, [PT(30), my, W-PT(30), my+PT(85)], PT(14))
        draw.text((PT(55), my+PT(22)), icon, font=find_font(20))
        draw.text((PT(100), my+PT(22)), title, font=find_font(14), fill=C_BLACK)
        draw.text((PT(100), my+PT(52)), desc, font=find_font(10), fill=C_GRAY)
        draw.text((W-PT(70), my+PT(28)), "›", font=find_font(20), fill=C_GRAY)
    
    # Tip card
    tip_y = menu_y + 5 * PT(100) + PT(20)
    draw_rounded_rect(draw, [PT(30), tip_y, W-PT(30), tip_y+PT(90)], PT(14), fill="#fef3c7")
    draw.text((PT(55), tip_y+PT(30)), "📌", font=find_font(18))
    draw.text((PT(90), tip_y+PT(22)), "添加到我的小程序，下次直接打开", font=find_font(12), fill="#92400e")
    draw.text((PT(90), tip_y+PT(55)), "点击右上角「⋯」→ 添加到我的小程序", font=find_font(10), fill="#a16207")
    
    # Tab bar
    draw_tab_bar(draw, [
        ("首页", "🏠"),
        ("小工具", "🔧"),
        ("电子照", "📄"),
        ("我的", "👤"),
    ], selected_idx=3)
    
    img.save(os.path.join(OUTPUT_DIR, "mockup_profile.png"))
    print("✅ mockup_profile.png")


if __name__ == "__main__":
    print("🎨 开始渲染 6 张高保真 Mockup...")
    render_home()
    render_tools()
    render_specs()
    render_generate()
    render_photos()
    render_profile()
    print(f"\n✅ 全部完成！文件保存在: {OUTPUT_DIR}")
