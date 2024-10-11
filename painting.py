from PIL import Image, ImageDraw, ImageFont
import io
from aiogram.types import InputFile

from server_info import timing_decorator


@timing_decorator
async def process_image(registration_info: dict, service_name: str):
    _price_limit_color = '#967026'

    if service_name == "Лепка":
        service_name = "modeling"
    elif service_name == "Живопись":
        service_name = "painting"

    image_path = f'media/img/inspira-registration-{service_name}.png'

    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)

    font_bold_path = 'media/fonts/MAK.otf'
    font_semi_bold_path = 'media/fonts/'

    def draw_func(type_font, size_font, color, text_text, coord_x, coord_y):
        font = ImageFont.truetype(type_font, size_font)
        draw.text((coord_x, coord_y), text_text, font=font, fill=color)

    # День - прим. 19
    draw_func(font_bold_path, 350, '#3B3628', registration_info['date']['day'], 32, 1164)
    # Время - прим. 15:00
    draw_func(font_bold_path, 153, '#3B3628', registration_info['time'], 460, 1331)
    # Месяц - прим. ОКТ
    draw_func(font_bold_path, 158, '#3B3628', registration_info['date']['month'], 460, 1180)

    output = io.BytesIO()
    image.save(output, format='PNG')
    output.seek(0)

    return {"output_file": output, "output_filename": image_path}
