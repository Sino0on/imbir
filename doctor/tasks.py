"""
Celery-задачи кабинета врача.

process_doctor_photo ставится в очередь из DoctorProfileView.update
(PUT /api/doctor/profile/?process_photo=true — кабинет и регистрация на сайте)
и DoctorRegisterView.post, когда врач просит обработать новое фото ИИ (белый
халат, белый фон). Раньше обработка (около минуты) шла прямо в запросе: nginx
обрывает ответ на 60-й секунде, клиент видел ошибку, хотя сервер дорабатывал и
подменял фото. Теперь запрос сохраняет оригинал и сразу отвечает
"photo_ai_processing": "queued", а подмену делает воркер.
"""
import logging
import os

from celery import shared_task
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


def queue_doctor_photo_processing(profile) -> bool:
    """Ставит обработку текущего фото профиля в очередь. False — очередь
    недоступна (брокер Redis): тогда остаётся оригинал, и вызывающий код
    отвечает клиенту "failed", как при неудачной обработке."""
    try:
        process_doctor_photo.delay(profile.pk, profile.photo.name)
    except Exception:
        logger.exception(
            'queue_doctor_photo_processing: не удалось поставить задачу (profile=%s)', profile.pk,
        )
        return False
    return True


@shared_task(name='doctor.process_doctor_photo')
def process_doctor_photo(profile_id: int, photo_name: str) -> None:
    from users.models import DoctorProfile

    from .ai_photo import generate_doctor_coat_photo

    profile = DoctorProfile.objects.filter(pk=profile_id).first()
    if profile is None or profile.photo.name != photo_name:
        logger.info(
            'process_doctor_photo: profile=%s — профиля нет или фото уже другое, пропускаем', profile_id,
        )
        return

    storage = profile.photo.storage
    try:
        with storage.open(photo_name, 'rb') as source:
            photo_bytes = source.read()
    except OSError:
        logger.warning('process_doctor_photo: файл %s не найден (profile=%s)', photo_name, profile_id)
        return

    processed = generate_doctor_coat_photo(photo_bytes, os.path.basename(photo_name))
    if not processed:
        # Причину уже записал generate_doctor_coat_photo; в профиле остаётся оригинал.
        return

    target = profile.photo.field.generate_filename(profile, f'{profile.user_id}_coat.png')
    new_name = storage.save(target, ContentFile(processed))

    # Пока ИИ работал (около минуты), врач мог загрузить другое фото или изменить
    # другие поля профиля. Поэтому не save() всей модели, а один UPDATE только
    # поля photo — и только если в профиле всё ещё то фото, что обрабатывали.
    updated = DoctorProfile.objects.filter(pk=profile_id, photo=photo_name).update(photo=new_name)
    if not updated:
        storage.delete(new_name)
        logger.info(
            'process_doctor_photo: profile=%s — фото заменили во время обработки, результат отброшен',
            profile_id,
        )
