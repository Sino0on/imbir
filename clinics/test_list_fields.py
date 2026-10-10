"""Список клиник отдаёт адрес и стаж — их показывают карточки каталога,
поиска, главной и выпадающий список клиник в форме записи (N84)."""
from rest_framework.test import APITestCase

from users.models import ClinicProfile, User


class ClinicListFieldsTests(APITestCase):
    def test_list_contains_address_and_experience_years(self):
        user = User.objects.create_user(
            email='clinic-list@example.com', password='password123',
            first_name='Клиника', role=User.Role.CLINIC,
        )
        ClinicProfile.objects.create(
            user=user, name='Клиника на Чуй', city='Бишкек',
            address='пр. Чуй, 100', experience_years=12, is_published=True,
        )
        response = self.client.get('/api/clinics/', {'city': 'all'})
        self.assertEqual(response.status_code, 200, response.data)
        item = next(c for c in response.data['data'] if c['id'] == user.id)
        self.assertEqual(item['address'], 'пр. Чуй, 100')
        self.assertEqual(item['experience_years'], 12)
