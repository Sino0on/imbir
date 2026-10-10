"""GET /api/doctor/profile/ — места работы врача (N10).

Форма услуги в кабинете берёт список клиник отсюда, а не из публичной
карточки: снятому с публикации врачу та отдаёт 404, и выбрать клинику
было нельзя — сохранение падало с 400 «укажите clinic_id».
"""
from rest_framework.test import APITestCase

from users.models import ClinicBranch, ClinicProfile, DoctorClinicLink, DoctorProfile, User


class DoctorOwnProfileClinicsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='doctor-own-clinics@example.com', password='password123',
            first_name='Алина', last_name='Садыкова', role=User.Role.DOCTOR,
        )
        # Не опубликован: публичный /api/doctors/{id}/ для него — 404.
        self.profile = DoctorProfile.objects.create(user=self.user, is_published=False)
        self.client.force_authenticate(user=self.user)

    def _clinic(self, email, name):
        owner = User.objects.create_user(
            email=email, password='password123', role=User.Role.CLINIC,
        )
        return ClinicProfile.objects.create(user=owner, name=name)

    def test_unpublished_doctor_sees_active_clinic_links(self):
        first = self._clinic('clinic-a@example.com', 'Клиника А')
        second = self._clinic('clinic-b@example.com', 'Клиника Б')
        third = self._clinic('clinic-c@example.com', 'Клиника В')
        branch = ClinicBranch.objects.create(clinic=second, name='Филиал 1', address='ул. Токтогула, 1')
        DoctorClinicLink.objects.create(doctor=self.profile, clinic=first)
        DoctorClinicLink.objects.create(doctor=self.profile, clinic=second, branch=branch)
        DoctorClinicLink.objects.create(doctor=self.profile, clinic=third, is_active=False)

        response = self.client.get('/api/doctor/profile/')
        self.assertEqual(response.status_code, 200, response.data)
        clinics = sorted(response.data['clinics'], key=lambda c: c['name'])
        self.assertEqual(clinics, [
            {'id': first.user_id, 'name': 'Клиника А', 'branch': None},
            {
                'id': second.user_id, 'name': 'Клиника Б',
                'branch': {'id': branch.id, 'name': 'Филиал 1', 'address': 'ул. Токтогула, 1'},
            },
        ])

    def test_clinic_id_from_profile_is_accepted_by_service_form(self):
        first = self._clinic('clinic-d@example.com', 'Клиника Г')
        second = self._clinic('clinic-e@example.com', 'Клиника Д')
        DoctorClinicLink.objects.create(doctor=self.profile, clinic=first)
        DoctorClinicLink.objects.create(doctor=self.profile, clinic=second)

        clinics = self.client.get('/api/doctor/profile/').data['clinics']
        target = next(c for c in clinics if c['name'] == 'Клиника Д')
        response = self.client.post(
            '/api/doctor/services/',
            {'name': 'Массаж', 'category': 'procedures', 'clinic_id': target['id']},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['clinic'], {'id': second.user_id, 'name': 'Клиника Д'})

    def test_clinics_is_read_only(self):
        response = self.client.put(
            '/api/doctor/profile/',
            {'first_name': 'Алина', 'last_name': 'Садыкова', 'clinics': [{'id': 1}]},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['clinics'], [])
