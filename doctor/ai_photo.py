import base64
import io
import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

_COAT_PHOTO_PROMPT = (
    'Отредактируй это фото врача: надень на человека белый медицинский халат поверх '
    'текущей одежды и помести его на чистом однотонном белом фоне, как для '
    'профессионального портрета врача в медицинской анкете. Лицо, причёску, черты '
    'и позу не меняй — только одежда и фон. Фотореалистично, без искажений.'
)


def generate_doctor_coat_photo(photo_bytes, filename='photo.jpg'):
    """Прогоняет фото врача через OpenAI (gpt-image-1): надевает белый халат,
    ставит белый фон. Возвращает bytes готового PNG, либо None при ошибке —
    вызывающий код должен в этом случае просто оставить исходное фото."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    source = io.BytesIO(photo_bytes)
    source.name = filename

    try:
        result = client.images.edit(
            model='gpt-image-1',
            image=source,
            prompt=_COAT_PHOTO_PROMPT,
        )
        return base64.b64decode(result.data[0].b64_json)
    except Exception as e:
        logger.error(f'Doctor photo AI processing failed: {e}')
        return None
