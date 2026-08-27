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

# Один "боевой" вариант картиночной модели на провайдера — не даём это выбирать
# через админку, чтобы не плодить комбинаторику; только сам провайдер.
_GEMINI_IMAGE_MODEL = 'gemini-3.1-flash-image'


def _generate_with_openai(photo_bytes, filename):
    """input_fidelity='high' — специальный режим gpt-image-1 именно для сохранения
    лица/узнаваемости при редактировании (без него модель куда свободнее
    перерисовывает черты). quality='high' — максимальная детализация."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    source = io.BytesIO(photo_bytes)
    source.name = filename

    result = client.images.edit(
        model='gpt-image-1',
        image=source,
        prompt=_COAT_PHOTO_PROMPT,
        input_fidelity='high',
        quality='high',
    )
    return base64.b64decode(result.data[0].b64_json)


def _generate_with_gemini(photo_bytes, filename):
    from google import genai
    from PIL import Image

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    source_image = Image.open(io.BytesIO(photo_bytes))

    response = client.models.generate_content(
        model=_GEMINI_IMAGE_MODEL,
        contents=[_COAT_PHOTO_PROMPT, source_image],
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data

    raise ValueError('Gemini не вернул изображение в ответе')


def generate_doctor_coat_photo(photo_bytes, filename='photo.jpg'):
    """Прогоняет фото врача через ИИ (OpenAI или Gemini — выбирается в админке,
    SiteSettings.ai_photo_provider): надевает белый халат, ставит белый фон.
    Возвращает bytes готового изображения, либо None при ошибке — вызывающий
    код должен в этом случае просто оставить исходное фото."""
    from references.models import SiteSettings

    provider = SiteSettings.load().ai_photo_provider

    try:
        if provider == SiteSettings.AiPhotoProvider.GEMINI:
            return _generate_with_gemini(photo_bytes, filename)
        return _generate_with_openai(photo_bytes, filename)
    except Exception as e:
        logger.error(f'Doctor photo AI processing failed (provider={provider}): {e}')
        return None
