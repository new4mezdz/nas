# create_icons.py - 创建PWA图标
from PIL import Image, ImageDraw, ImageFont
import os


def create_text_icon(size, text, bg_color, text_color, output_path):
    """创建文字图标"""
    # 创建图像
    img = Image.new('RGB', (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    # 计算字体大小
    font_size = max(size // 4, 12)

    # 尝试使用系统字体
    try:
        # Windows
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        try:
            # macOS
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
        except:
            try:
                # Linux
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                # 降级到默认字体
                font = ImageFont.load_default()

    # 计算文字位置（居中）
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2
    y = (size - text_height) // 2

    # 绘制文字
    draw.text((x, y), text, fill=text_color, font=font)

    # 保存图片
    img.save(output_path)
    print(f"✅ 创建图标: {output_path} ({size}x{size})")


def main():
    # 创建图标目录
    icon_dir = 'static/pwa/icons'
    os.makedirs(icon_dir, exist_ok=True)

    # 图标尺寸列表
    sizes = [72, 96, 128, 144, 152, 192, 384, 512]

    # 配置
    text = "NAS"
    bg_color = (44, 62, 80)  # #2c3e50 深蓝色
    text_color = (255, 255, 255)  # 白色文字

    print("🎨 开始创建PWA图标...")

    # 批量创建图标
    for size in sizes:
        output_path = os.path.join(icon_dir, f'icon-{size}.png')
        create_text_icon(size, text, bg_color, text_color, output_path)

    print(f"🎉 所有图标创建完成！共创建 {len(sizes)} 个图标")
    print(f"📁 图标保存位置: {icon_dir}/")

    # 显示下一步操作
    print("\n📋 下一步操作：")
    print("1. 重启您的Flask应用")
    print("2. 用手机浏览器访问您的NAS系统")
    print("3. 查看是否出现'添加到主屏幕'提示")
    print("4. 添加后从主屏幕打开，应该是全屏模式")


if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("❌ 缺少PIL库，请先安装：")
        print("   pip install Pillow")
    except Exception as e:
        print(f"❌ 创建图标失败: {e}")
        print("💡 您也可以手动创建图标文件，或暂时跳过图标步骤")