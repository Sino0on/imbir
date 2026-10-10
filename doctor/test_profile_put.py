"""PUT /api/doctor/profile/ — частичное обновление (K24) и имена документов (N62).

Смена фото уходит multipart-запросом только с полем photo: булевы поля и
специализации, которых нет в теле, не должны сбрасываться.
"""
import io
import shutil
import tempfile
from urllib.parse import unquote

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from references.models import Specialization
from users.models import DoctorDocument, DoctorProfile, User


def _png(name='me.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), (200, 30, 30)).save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class DoctorProfilePartialPutTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            email='doctor-put@example.com', password='password123',
            first_name='Алина', last_name='Садыкова', role=User.Role.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(
            user=self.user, is_online_available=True, emergency_24_7=True,
        )
        self.spec = Specialization.objects.create(name='Кардиолог')
        self.profile.primary_specializations.set([self.spec])
        self.client.force_authenticate(user=self.user)

    def test_photo_only_multipart_put_keeps_booleans_and_specializations(self):
        response = self.client.put('/api/doctor/profile/', {'photo': _png()}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.photo)
        self.assertTrue(self.profile.is_online_available)
        self.assertTrue(self.profile.emergency_24_7)
        self.assertEqual(list(self.profile.primary_specializations.all()), [self.spec])
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Алина')

    def test_explicit_false_still_turns_flag_off(self):
        response = self.client.put(
            '/api/doctor/profile/', {'is_online_available': 'false', 'photo': _png()}, format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_online_available)
        self.assertTrue(self.profile.emergency_24_7)

    def test_explicit_empty_specializations_clear_them(self):
        response = self.client.put('/api/doctor/profile/', {'primary_specialization_ids': []}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.profile.primary_specializations.count(), 0)

    def test_document_url_keeps_original_name(self):
        upload = SimpleUploadedFile('Диплом врача.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = self.client.post('/api/doctor/documents/', {'file': upload}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(unquote(response.data['url']).endswith('/Диплом_врача.pdf'), response.data['url'])
        doc = DoctorDocument.objects.get(pk=response.data['id'])
        self.assertTrue(doc.file.name.startswith('doctors/documents/'))

    def test_document_reupload_by_encoded_url_keeps_path(self):
        upload = SimpleUploadedFile('Диплом.pdf', b'%PDF-1.4', content_type='application/pdf')
        first = self.client.post('/api/doctor/documents/', {'file': upload}, format='multipart')
        second = self.client.post('/api/doctor/documents/', {'url': first.data['url']}, format='json')
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(
            DoctorDocument.objects.get(pk=second.data['id']).file.name,
            DoctorDocument.objects.get(pk=first.data['id']).file.name,
        )
