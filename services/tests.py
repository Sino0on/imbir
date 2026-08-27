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
