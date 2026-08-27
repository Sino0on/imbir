import base64
import io
import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

_COAT_PHOTO_PROMPT = (
    'Edit this photo of a doctor: dress the person in a white medical coat over their '
    'existing clothing, and place them on a plain, seamless white studio background, '
    'suitable for a professional medical profile portrait. Do not change the face, '
    'facial features, expression, skin tone, hairstyle, or body pose in any way — '
    "preserve the person's identity and likeness exactly as in the original photo. "
    'Only change the clothing (add the white coat) and the background. Photorealistic, '
    'natural studio lighting, high detail.'
)


def generate_doctor_coat_photo(photo_bytes, filename='photo.jpg'):
    """Прогоняет фото врача через OpenAI (gpt-image-1): надевает белый халат,
    ставит белый фон. Возвращает bytes готового PNG, либо None при ошибке —
    вызывающий код должен в этом случае просто оставить исходное фото.

    input_fidelity='high' — специальный режим gpt-image-1 именно для сохранения
    лица/узнаваемости при редактировании (без него модель куда свободнее
    перерисовывает черты). quality='high' — максимальная детализация."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    source = io.BytesIO(photo_bytes)
    source.name = filename

    try:
        result = client.images.edit(
            model='gpt-image-1',
            image=source,
            prompt=_COAT_PHOTO_PROMPT,
            input_fidelity='high',
            quality='high',
        )
        return base64.b64decode(result.data[0].b64_json)
    except Exception as e:
        logger.error(f'Doctor photo AI processing failed: {e}')
        return None
