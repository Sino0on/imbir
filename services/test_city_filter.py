from rest_framework import status
from rest_framework.test import APITestCase

from users.models import ClinicProfile, DoctorProfile, User

from .models import Service


class ServiceListCityFilterTests(APITestCase):
    url = '/api/services/'

    def setUp(self):
        bishkek_clinic = self._create_clinic('Клиника Бишкек', 'Бишкек')
        osh_clinic = self._create_clinic('Клиника Ош', 'Ош')
        osh_doctor = self._create_doctor('Ош')

        Service.objects.create(name='УЗИ Бишкек', category='Диагностика', clinic=bishkek_clinic)
        Service.objects.create(name='УЗИ Ош', category='Диагностика', clinic=osh_clinic)
        # Частная услуга врача без клиники — город берётся у врача.
        private = Service.objects.create(name='Выезд на дом', category='Выезд')
        private.doctors.add(osh_doctor)
        # Услуга клиники Бишкека, которую ведёт врач из Оша, остаётся в Бишкеке.
        mixed = Service.objects.create(name='Консультация', category='Приём', clinic=bishkek_clinic)
        mixed.doctors.add(osh_doctor)

    def _create_clinic(self, name, city):
        user = User.objects.create_user(
            email=f'clinic-{city}@example.com',
            password='password123',
            first_name=name,
            last_name='Test',
            role=User.Role.CLINIC,
        )
        return ClinicProfile.objects.create(user=user, name=name, city=city, is_published=True)

    def _create_doctor(self, city):
        user = User.objects.create_user(
            email=f'doctor-{city}@example.com',
            password='password123',
            first_name='Врач',
            last_name=city,
            role=User.Role.DOCTOR,
        )
        return DoctorProfile.objects.create(user=user, city=city, is_published=True)

    def _names(self, params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {item['name'] for item in response.data['data']}

    def test_city_filters_by_clinic_or_private_doctor_city(self):
        self.assertEqual(self._names({'city': 'Ош'}), {'УЗИ Ош', 'Выезд на дом'})
        self.assertEqual(
            self._names({'city': 'Бишкек'}), {'УЗИ Бишкек', 'Консультация'},
        )

    def test_without_city_returns_every_city(self):
        self.assertEqual(
            self._names({}),
            {'УЗИ Бишкек', 'УЗИ Ош', 'Выезд на дом', 'Консультация'},
        )

    def test_city_all_returns_every_city(self):
        self.assertEqual(len(self._names({'city': 'all'})), 4)

    def test_city_combines_with_search(self):
        self.assertEqual(self._names({'city': 'Ош', 'search': 'УЗИ'}), {'УЗИ Ош'})
