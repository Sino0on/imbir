from rest_framework import status
from rest_framework.test import APITestCase

from users.models import ClinicProfile, DoctorClinicLink, DoctorProfile, User


class ClinicDoctorListActiveLinksTests(APITestCase):
    """K57: в списке врачей кабинета клиники — только действующие связи."""

    def setUp(self):
        clinic_user = User.objects.create_user(
            email='clinic@example.com', password='password123', first_name='Клиника',
            role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=clinic_user, name='Клиника')
        self.active = self._doctor('active')
        self.inactive = self._doctor('inactive')
        DoctorClinicLink.objects.create(doctor=self.active, clinic=self.clinic)
        DoctorClinicLink.objects.create(doctor=self.inactive, clinic=self.clinic, is_active=False)
        self.client.force_authenticate(clinic_user)

    def _doctor(self, name):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123', first_name=name,
            role=User.Role.DOCTOR,
        )
        return DoctorProfile.objects.create(user=user)

    def test_inactive_link_hidden(self):
        response = self.client.get('/api/clinic/doctors/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item['id'] for item in response.data['data']], [self.active.user_id],
        )
