from rest_framework import status
from rest_framework.test import APITestCase

from references.models import Specialization
from users.models import ClinicProfile, User


class ClinicSpecializationFilterTests(APITestCase):
    url = '/api/clinics/'

    def setUp(self):
        self.cardiology = Specialization.objects.create(name='Кардиология')
        self.therapy = Specialization.objects.create(name='Терапия')
        self.dermatology = Specialization.objects.create(name='Дерматология')

        self.cardiology_clinic = self._create_clinic('Кардио Клиника')
        self.cardiology_clinic.primary_specializations.add(self.cardiology)

        self.therapy_clinic = self._create_clinic('Терапия Клиника')
        self.therapy_clinic.narrow_specializations.add(self.therapy)

        self.other_clinic = self._create_clinic('Дерма Клиника')
        self.other_clinic.primary_specializations.add(self.dermatology)

    def _create_clinic(self, name):
        user = User.objects.create_user(
            email=f'{name}@example.com',
            password='password123',
            first_name=name,
            last_name='Test',
            role=User.Role.CLINIC,
        )
        return ClinicProfile.objects.create(
            user=user,
            name=name,
            city='Бишкек',
            is_published=True,
        )

    def _get_names(self, params):
        response = self.client.get(self.url, {'city': 'Бишкек', **params})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {clinic['name'] for clinic in response.data['data']}

    def test_csv_specialization_filter_uses_or(self):
        names = self._get_names({'specialization': 'Кардиология,Терапия'})

        self.assertEqual(names, {'Кардио Клиника', 'Терапия Клиника'})

    def test_repeated_specialization_parameters_use_or(self):
        response = self.client.get(
            self.url,
            [
                ('city', 'Бишкек'),
                ('specialization', 'Кардиология'),
                ('specialization', 'Терапия'),
            ],
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {clinic['name'] for clinic in response.data['data']},
            {'Кардио Клиника', 'Терапия Клиника'},
        )

    def test_empty_specialization_does_not_filter(self):
        names = self._get_names({'specialization': ''})

        self.assertEqual(
            names,
            {'Кардио Клиника', 'Терапия Клиника', 'Дерма Клиника'},
        )


class ClinicPriceFilterTests(APITestCase):
    """K37/K57: клиника проходит фильтр по цене, только если у неё есть одна
    активная услуга, цена которой попадает в диапазон целиком."""
    url = '/api/clinics/'

    def setUp(self):
        from services.models import Service

        self.in_range = self._clinic('В диапазоне')
        Service.objects.create(name='Приём', category='Приём', price=700, clinic=self.in_range)

        # Одна услуга дешевле, другая дороже — ни одной внутри 500–1000.
        self.split = self._clinic('Разброс')
        Service.objects.create(name='Дешёвая', category='Приём', price=100, clinic=self.split)
        Service.objects.create(name='Дорогая', category='Приём', price=10000, clinic=self.split)

        self.inactive = self._clinic('Отключённая услуга')
        Service.objects.create(
            name='Отключена', category='Приём', price=700, clinic=self.inactive, is_active=False,
        )

    def _clinic(self, name):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123', first_name=name,
            role=User.Role.CLINIC,
        )
        return ClinicProfile.objects.create(user=user, name=name, city='Бишкек', is_published=True)

    def _names(self, params):
        response = self.client.get(self.url, {'city': 'Бишкек', **params})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [clinic['name'] for clinic in response.data['data']]

    def test_range_requires_single_service_inside(self):
        self.assertEqual(self._names({'min_price': 500, 'max_price': 1000}), ['В диапазоне'])

    def test_inactive_services_ignored(self):
        self.assertNotIn('Отключённая услуга', self._names({'min_price': 500}))

    def test_clinic_listed_once_with_several_matching_services(self):
        from services.models import Service
        Service.objects.create(name='Ещё приём', category='Приём', price=800, clinic=self.in_range)
        self.assertEqual(self._names({'min_price': 500, 'max_price': 1000}), ['В диапазоне'])
