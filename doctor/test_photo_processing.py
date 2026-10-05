"""Фоновая ИИ-обработка фото врача (doctor/tasks.py).

Запросы с process_photo=true отвечают сразу и только ставят задачу; сама
обработка идёт в воркере и подменяет фото, не затирая того, что врач успел
изменить за время работы ИИ.
"""
import io
import json
import shutil
import tempfile
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from doctor.tasks import process_doctor_photo
from references.models import SiteSettings, Specialization
from users.models import DoctorProfile, PhoneVerificationCode, User

_AI = 'doctor.ai_photo.generate_doctor_coat_photo'
_DELAY = 'doctor.tasks.process_doctor_photo.delay'


def _image_bytes(color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(buffer, 'PNG')
    return buffer.getvalue()


def _upload(name='me.png'):
    return SimpleUploadedFile(name, _image_bytes(), content_type='image/png')


def _ai_must_not_run(*args, **kwargs):
    raise AssertionError('ИИ-обработка не должна выполняться внутри запроса')


class _IsolatedMedia:
    """Файлы тестов — во временном каталоге, а не в media/ проекта."""

    def setUp(self):
        super().setUp()
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

    @staticmethod
    def set_ai_enabled(enabled):
        site = SiteSettings.load()
        site.ai_doctor_photo_processing_enabled = enabled
        site.save()


class DoctorProfilePhotoRequestTests(_IsolatedMedia, APITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            email='photo-doctor@example.com', password='password123',
            first_name='Алина', last_name='Садыкова', role=User.Role.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user)
        self.set_ai_enabled(True)

    def put_photo(self, query='?process_photo=true'):
        return self.client.put(
            f'/api/doctor/profile/{query}',
            {'first_name': 'Алина', 'last_name': 'Садыкова', 'photo': _upload()},
            format='multipart',
        )

    def test_ai_request_answers_immediately_and_queues_processing(self):
        with mock.patch(_DELAY) as delay, mock.patch(_AI, side_effect=_ai_must_not_run) as ai:
            response = self.put_photo()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['photo_ai_processing'], 'queued')
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo.name.startswith('doctors/photos/'))
        delay.assert_called_once_with(self.profile.pk, self.profile.photo.name)
        ai.assert_not_called()

    def test_disabled_ai_saves_original_without_queueing(self):
        self.set_ai_enabled(False)
        with mock.patch(_DELAY) as delay:
            response = self.put_photo()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['photo_ai_processing'], 'disabled')
        delay.assert_not_called()
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo)

    def test_plain_photo_upload_never_queues(self):
        with mock.patch(_DELAY) as delay:
            response = self.put_photo(query='')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn('photo_ai_processing', response.data)
        delay.assert_not_called()

    def test_process_flag_without_new_photo_never_queues(self):
        with mock.patch(_DELAY) as delay:
            response = self.client.put(
                '/api/doctor/profile/?process_photo=true',
                {'first_name': 'Алина', 'last_name': 'Садыкова'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn('photo_ai_processing', response.data)
        delay.assert_not_called()

    def test_unavailable_queue_keeps_original_and_reports_failed(self):
        with mock.patch(_DELAY, side_effect=ConnectionError('broker down')), \
                self.assertLogs('doctor.tasks', level='ERROR'):
            response = self.put_photo()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['photo_ai_processing'], 'failed')
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo)


class DoctorRegistrationPhotoTests(_IsolatedMedia, APITestCase):
    def setUp(self):
        super().setUp()
        self.set_ai_enabled(True)
        phone = '+996700000002'
        PhoneVerificationCode.objects.create(phone=phone, code='1234', is_used=True)
        specialization = Specialization.objects.create(name='Флеболог')
        self.payload = {
            'password': 'DoctorTest123!',
            'step1': json.dumps({
                'full_name': 'Тестовый Врач', 'email': 'doctor-photo@example.com',
                'phone': phone, 'birth_date': '1990-01-01',
            }),
            'step2': '{}', 'step3': '{}', 'step4': '{}',
            'step5': json.dumps({'primary_specializations': [specialization.id]}),
            'step6': '{}',
            'step7': json.dumps({
                'agree_terms': True, 'agree_privacy': True,
                'agree_data_processing': True, 'agree_publishing': True,
            }),
            'process_photo': 'true',
        }

    def register(self):
        return self.client.post(
            '/api/auth/register/doctor/',
            {**self.payload, 'photo': _upload('doctor.png')},
            format='multipart',
        )

    def test_registration_with_ai_photo_does_not_wait_for_ai(self):
        with mock.patch(_DELAY) as delay, mock.patch(_AI, side_effect=_ai_must_not_run) as ai:
            response = self.register()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['photo_ai_processing'], 'queued')
        profile = DoctorProfile.objects.get(user__email='doctor-photo@example.com')
        delay.assert_called_once_with(profile.pk, profile.photo.name)
        ai.assert_not_called()

    def test_registration_with_ai_disabled_reports_disabled(self):
        self.set_ai_enabled(False)
        with mock.patch(_DELAY) as delay:
            response = self.register()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['photo_ai_processing'], 'disabled')
        delay.assert_not_called()


class ProcessDoctorPhotoTaskTests(_IsolatedMedia, TestCase):
    def setUp(self):
        super().setUp()
        user = User.objects.create_user(
            email='task-doctor@example.com', password='password123',
            first_name='Алина', last_name='Садыкова', role=User.Role.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(user=user, city='Бишкек')
        self.profile.photo.save('original.png', ContentFile(_image_bytes()), save=True)
        self.original = self.profile.photo.name
        self.processed = _image_bytes((10, 20, 230))

    def stored_photo(self):
        self.profile.refresh_from_db()
        with self.profile.photo.open('rb') as source:
            return source.read()

    def coat_files(self):
        _, files = self.profile.photo.storage.listdir('doctors/photos')
        return [name for name in files if '_coat' in name]

    def test_task_name_is_stable_for_already_queued_jobs(self):
        self.assertEqual(process_doctor_photo.name, 'doctor.process_doctor_photo')

    def test_replaces_photo_with_processed_version(self):
        with mock.patch(_AI, return_value=self.processed) as ai:
            process_doctor_photo(self.profile.pk, self.original)

        self.assertEqual(ai.call_args.args[0], _image_bytes())  # обрабатывали именно оригинал
        self.assertEqual(self.stored_photo(), self.processed)
        self.assertIn('_coat', self.profile.photo.name)

    def test_keeps_original_when_ai_fails(self):
        with mock.patch(_AI, return_value=None):
            process_doctor_photo(self.profile.pk, self.original)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo.name, self.original)
        self.assertEqual(self.coat_files(), [])

    def test_discards_result_when_photo_was_replaced_during_processing(self):
        def doctor_uploads_another_photo(*args, **kwargs):
            DoctorProfile.objects.filter(pk=self.profile.pk).update(photo='doctors/photos/newer.png')
            return self.processed

        with mock.patch(_AI, side_effect=doctor_uploads_another_photo):
            process_doctor_photo(self.profile.pk, self.original)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo.name, 'doctors/photos/newer.png')
        self.assertEqual(self.coat_files(), [])  # отброшенный результат не оставляет файла

    def test_other_profile_fields_edited_during_processing_are_preserved(self):
        def doctor_edits_city(*args, **kwargs):
            DoctorProfile.objects.filter(pk=self.profile.pk).update(city='Ош')
            return self.processed

        with mock.patch(_AI, side_effect=doctor_edits_city):
            process_doctor_photo(self.profile.pk, self.original)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.city, 'Ош')
        self.assertIn('_coat', self.profile.photo.name)

    def test_stale_task_for_previous_photo_does_nothing(self):
        with mock.patch(_AI) as ai:
            process_doctor_photo(self.profile.pk, 'doctors/photos/some-older.png')

        ai.assert_not_called()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo.name, self.original)

    def test_deleted_profile_is_ignored(self):
        with mock.patch(_AI) as ai:
            process_doctor_photo(999999, self.original)

        ai.assert_not_called()

    def test_missing_source_file_is_ignored(self):
        self.profile.photo.storage.delete(self.original)
        with mock.patch(_AI) as ai:
            process_doctor_photo(self.profile.pk, self.original)

        ai.assert_not_called()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.photo.name, self.original)
