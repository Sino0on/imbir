"""Профиль клиники: частичный PUT, нормализация сайта/координат, имена
документов и порядок фото (K24, N17, N56, N62, N82)."""
import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from urllib.parse import unquote

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from references.models import Specialization
from users.models import (
    ClinicDocument, ClinicPhoto, ClinicProfile, DoctorClinicLink, DoctorDocument, DoctorProfile, User,
)

PROFILE_URL = '/api/clinic/profile/'


def _png(name='logo.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), (10, 120, 200)).save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


class _MediaTestCase(APITestCase):
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
            email='clinic-media@example.com', password='password123',
            first_name='Клиника', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=self.user, name='Клиника', city='Бишкек', emergency_24_7=True,
            website='https://old.kg', phone='+996700111222',
        )
        self.spec = Specialization.objects.create(name='Терапия')
        self.clinic.primary_specializations.set([self.spec])
        self.client.force_authenticate(user=self.user)


class ClinicProfilePartialPutTests(_MediaTestCase):
    def test_logo_multipart_put_keeps_booleans_and_specializations(self):
        response = self.client.put(PROFILE_URL, {'logo': _png()}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertTrue(self.clinic.logo)
        self.assertTrue(self.clinic.emergency_24_7)
        self.assertEqual(list(self.clinic.primary_specializations.all()), [self.spec])

    def test_json_put_without_name_is_accepted(self):
        response = self.client.put(PROFILE_URL, {'description': 'Новое описание'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.description, 'Новое описание')
        self.assertEqual(self.clinic.name, 'Клиника')

    def test_empty_strings_clear_fields(self):
        response = self.client.put(
            PROFILE_URL, {'website': '', 'phone': '', 'latitude': None, 'longitude': ''}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.website, '')
        self.assertEqual(self.clinic.phone, '')
        self.assertIsNone(self.clinic.latitude)
        self.assertIsNone(self.clinic.longitude)


class ClinicProfileNormalizationTests(_MediaTestCase):
    def test_website_without_scheme_gets_https(self):
        response = self.client.put(PROFILE_URL, {'website': 'imbir.kg'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.website, 'https://imbir.kg')
        self.assertEqual(response.data['website'], 'https://imbir.kg')

    def test_website_with_url_in_query_gets_https(self):
        response = self.client.put(PROFILE_URL, {'website': 'imbir.kg/?ref=https://x.kg'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.website, 'https://imbir.kg/?ref=https://x.kg')

    def test_invalid_website_names_the_field(self):
        response = self.client.put(PROFILE_URL, {'website': 'не сайт'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('website', response.data)

    def test_google_maps_coordinates_are_rounded(self):
        response = self.client.put(
            PROFILE_URL, {'latitude': '42.87462134712345', 'longitude': 74.5698111111111}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.latitude, Decimal('42.874621'))
        self.assertEqual(self.clinic.longitude, Decimal('74.569811'))

    def test_non_numeric_coordinate_is_rejected(self):
        response = self.client.put(PROFILE_URL, {'latitude': 'abc'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('latitude', response.data)


class ClinicDocumentNameTests(_MediaTestCase):
    def test_clinic_document_url_keeps_original_name(self):
        upload = SimpleUploadedFile('Лицензия клиники.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        response = self.client.post('/api/clinic/documents/', {'file': upload}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(unquote(response.data['url']).endswith('/Лицензия_клиники.pdf'), response.data['url'])
        doc = ClinicDocument.objects.get(pk=response.data['id'])
        self.assertTrue(doc.file.name.startswith('clinics/documents/'))
        self.assertLessEqual(len(doc.file.name), 100)

    def test_two_documents_with_same_name_do_not_collide(self):
        for _ in range(2):
            upload = SimpleUploadedFile('scan.pdf', b'%PDF-1.4', content_type='application/pdf')
            self.client.post('/api/clinic/documents/', {'file': upload}, format='multipart')
        names = list(ClinicDocument.objects.values_list('file', flat=True))
        self.assertEqual(len(set(names)), 2)
        self.assertTrue(all(name.endswith('/scan.pdf') for name in names))

    def test_long_name_fits_file_field(self):
        upload = SimpleUploadedFile('a' * 200 + '.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = self.client.post('/api/clinic/documents/', {'file': upload}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        doc = ClinicDocument.objects.get(pk=response.data['id'])
        self.assertLessEqual(len(doc.file.name), 100)
        self.assertTrue(doc.file.name.endswith('.pdf'))

    def test_clinic_doctor_document_keeps_original_name(self):
        doctor_user = User.objects.create_user(
            email='doc-media@example.com', password='password123', first_name='Врач', role=User.Role.DOCTOR,
        )
        doctor = DoctorProfile.objects.create(user=doctor_user)
        DoctorClinicLink.objects.create(doctor=doctor, clinic=self.clinic, is_active=True)
        upload = SimpleUploadedFile('Сертификат.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = self.client.post(f'/api/clinic/doctors/{doctor_user.id}/documents/', {'file': upload}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(unquote(response.data['url']).endswith('/Сертификат.pdf'), response.data['url'])
        self.assertTrue(DoctorDocument.objects.get(pk=response.data['id']).file.name.startswith('doctors/documents/'))


class ClinicPhotoOrderTests(_MediaTestCase):
    def test_photos_ordered_by_upload_in_own_and_public_profile(self):
        later = ClinicPhoto.objects.create(clinic=self.clinic, image='clinics/photos/later.png')
        earlier = ClinicPhoto.objects.create(clinic=self.clinic, image='clinics/photos/earlier.png')
        # Строка с меньшим id загружена позже — порядок задаёт uploaded_at, а не порядок строк
        ClinicPhoto.objects.filter(pk=earlier.pk).update(uploaded_at=later.uploaded_at - timedelta(minutes=5))

        own = self.client.get(PROFILE_URL)
        self.assertEqual([p['id'] for p in own.data['photos']], [earlier.pk, later.pk])

        public = self.client.get(f'/api/clinics/{self.user.id}/')
        self.assertEqual(public.status_code, 200)
        self.assertTrue(public.data['photos'][0].endswith('earlier.png'), public.data['photos'])
        self.assertTrue(public.data['photos'][1].endswith('later.png'), public.data['photos'])

    def test_photo_delete(self):
        photo = ClinicPhoto.objects.create(clinic=self.clinic, image='clinics/photos/wrong.png')
        response = self.client.delete(f'/api/clinic/photos/{photo.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ClinicPhoto.objects.filter(pk=photo.pk).exists())
