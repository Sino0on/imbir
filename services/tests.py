from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Service


class ServicePhotoApiTests(APITestCase):
    def setUp(self):
        self.service = Service.objects.create(
            name='Услуга с фотографией',
            category='Диагностика',
            photo=SimpleUploadedFile(
                'service.gif',
                b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;',
                content_type='image/gif',
            ),
        )

    def test_public_service_endpoints_return_the_service_photo(self):
        list_response = self.client.get('/api/services/')
        detail_response = self.client.get(f'/api/services/{self.service.id}/')

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

        list_item = next(
            item for item in list_response.data['data'] if item['id'] == self.service.id
        )
        self.assertIsNotNone(list_item['photo'])
        self.assertIn('/media/services/photos/', list_item['photo'])
        self.assertEqual(detail_response.data['photo'], list_item['photo'])


class ServiceBranchApiTests(APITestCase):
    """K22: процедура в филиале — список и карточка услуги отдают филиал,
    иначе пациент видел только основной адрес клиники."""

    def setUp(self):
        from users.models import ClinicBranch, ClinicProfile, User

        user = User.objects.create_user(
            email='clinic@example.com',
            password='password123',
            first_name='Клиника',
            last_name='Test',
            role=User.Role.CLINIC,
        )
        clinic = ClinicProfile.objects.create(
            user=user, name='Клиника', city='Бишкек',
            address='ул. Главная, 1', is_published=True,
        )
        self.branch = ClinicBranch.objects.create(
            clinic=clinic, name='Филиал Восток', address='ул. Восточная, 5',
        )
        self.in_branch = Service.objects.create(
            name='УЗИ в филиале', category='Диагностика',
            clinic=clinic, branch=self.branch,
        )
        self.main = Service.objects.create(
            name='УЗИ в главном здании', category='Диагностика', clinic=clinic,
        )

    def _list_item(self, service):
        response = self.client.get('/api/services/', {'clinic_id': service.clinic.user_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return next(i for i in response.data['data'] if i['id'] == service.id)

    def test_list_returns_branch(self):
        self.assertEqual(self._list_item(self.in_branch)['branch'], {
            'id': self.branch.id, 'name': 'Филиал Восток', 'address': 'ул. Восточная, 5',
        })

    def test_list_service_without_branch_returns_null(self):
        self.assertIsNone(self._list_item(self.main)['branch'])

    def test_detail_returns_branch(self):
        response = self.client.get(f'/api/services/{self.in_branch.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['branch']['address'], 'ул. Восточная, 5')
        self.assertEqual(response.data['branch']['name'], 'Филиал Восток')
