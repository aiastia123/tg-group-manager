"""验证码生成"""
import random
import io
import math
from PIL import Image, ImageDraw, ImageFont


def generate_image_captcha(length: int = 5) -> tuple[bytes, str]:
    """
    生成图片验证码，返回 (图片bytes, 答案文本)
    带扭曲线条和噪点，防止 OCR 识别
    """
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉容易混淆的 I/O/0/1
    answer = "".join(random.choices(chars, k=length))

    # 图片尺寸
    width, height = 200, 80
    bg_color = (random.randint(230, 255), random.randint(230, 255), random.randint(230, 255))

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # 尝试加载字体
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        except (IOError, OSError):
            font = ImageFont.load_default(size=36)

    # 绘制每个字符（随机颜色、轻微旋转）
    char_width = width // (length + 1)
    for i, ch in enumerate(answer):
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 150))
        x = char_width * (i + 0.3) + random.randint(-5, 5)
        y = random.randint(5, 20)

        # 创建单字符图片用于旋转
        char_img = Image.new("RGBA", (char_width, height), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((5, y), ch, fill=color, font=font)

        # 随机旋转 -15~15 度
        angle = random.randint(-15, 15)
        char_img = char_img.rotate(angle, resample=Image.BICUBIC, expand=False)

        # 粘贴到主图
        img.paste(char_img, (int(x), 0), char_img if char_img.mode == "RGBA" else None)

    # 添加干扰线
    draw = ImageDraw.Draw(img)
    for _ in range(4):
        line_color = (random.randint(50, 180), random.randint(50, 180), random.randint(50, 180))
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=2)

    # 添加干扰点
    for _ in range(100):
        dot_color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        draw.point((x, y), fill=dot_color)

    # 添加波浪扭曲效果
    img = _apply_wave(img)

    # 转为 bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), answer


def _apply_wave(img: Image.Image) -> Image.Image:
    """对图片应用波浪扭曲"""
    width, height = img.size
    result = Image.new("RGB", (width, height))
    pixels = img.load()
    result_pixels = result.load()

    amplitude = random.uniform(2, 5)
    frequency = random.uniform(0.02, 0.06)
    phase = random.uniform(0, 2 * math.pi)

    for x in range(width):
        offset = int(amplitude * math.sin(frequency * x + phase))
        for y in range(height):
            src_y = y + offset
            if 0 <= src_y < height:
                result_pixels[x, y] = pixels[x, src_y]
            else:
                result_pixels[x, y] = (255, 255, 255)

    return result