from rest_framework import status
from rest_framework.test import APITestCase

from users.models import (
    ClinicBranch, ClinicProfile, DoctorClinicLink, DoctorProfile, User,
)


def _create_doctor(email):
    user = User.objects.create_user(
        email=email,
        password='password123',
        first_name='Терапевт',
        last_name='Филиальный',
        role=User.Role.DOCTOR,
    )
    return DoctorProfile.objects.create(user=user, is_published=True, city='Бишкек')


def _create_clinic(email, name, address):
    user = User.objects.create_user(
        email=email,
        password='password123',
        first_name=name,
        last_name='Test',
        role=User.Role.CLINIC,
    )
    return ClinicProfile.objects.create(
        user=user, name=name, city='Бишкек', address=address, is_published=True,
    )


class DoctorWorkplaceBranchAddressTests(APITestCase):
    """K22: врач, принимающий в филиале, — пациенту нужен адрес филиала,
    а не основной адрес клиники."""

    def setUp(self):
        self.clinic = _create_clinic('c@example.com', 'Клиника', 'ул. Главная, 1')
        self.branch = ClinicBranch.objects.create(
            clinic=self.clinic, name='Филиал Восток', address='ул. Восточная, 5',
        )
        self.doctor = _create_doctor('d@example.com')
        DoctorClinicLink.objects.create(
            doctor=self.doctor, clinic=self.clinic, branch=self.branch,
        )

        self.other_clinic = _create_clinic('o@example.com', 'Другая', 'пр. Мира, 10')
        self.plain_doctor = _create_doctor('p@example.com')
        DoctorClinicLink.objects.create(doctor=self.plain_doctor, clinic=self.other_clinic)

    def _list_item(self, doctor):
        response = self.client.get('/api/doctors/', {'city': 'all'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return next(i for i in response.data['data'] if i['id'] == doctor.user_id)

    def test_list_workplace_uses_branch_address(self):
        item = self._list_item(self.doctor)

        workplace = item['workplaces'][0]
        self.assertEqual(workplace['id'], self.clinic.user_id)
        self.assertEqual(workplace['address'], 'ул. Восточная, 5')
        self.assertEqual(workplace['branch'], {
            'id': self.branch.id, 'name': 'Филиал Восток', 'address': 'ул. Восточная, 5',
        })
        self.assertEqual(item['clinic']['address'], 'ул. Восточная, 5')

    def test_detail_workplace_uses_branch_address(self):
        response = self.client.get(f'/api/doctors/{self.doctor.user_id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['workplaces'][0]['address'], 'ул. Восточная, 5')
        self.assertEqual(response.data['workplaces'][0]['branch']['name'], 'Филиал Восток')
        self.assertEqual(response.data['clinic']['address'], 'ул. Восточная, 5')

    def test_without_branch_keeps_clinic_address(self):
        item = self._list_item(self.plain_doctor)

        self.assertEqual(item['workplaces'][0]['address'], 'пр. Мира, 10')
        self.assertIsNone(item['workplaces'][0]['branch'])

    def test_branch_without_address_falls_back_to_clinic_address(self):
        self.branch.address = ''
        self.branch.save()

        item = self._list_item(self.doctor)

        self.assertEqual(item['workplaces'][0]['address'], 'ул. Главная, 1')
