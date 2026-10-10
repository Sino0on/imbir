from rest_framework import status
from rest_framework.test import APITestCase

from services.models import Service
from users.models import ClinicProfile, DoctorProfile, User


class FavoritesHideInvisibleTests(APITestCase):
    """K57: в избранном — только то, что сейчас видно в каталоге."""

    url = '/api/profile/favorites/'

    def setUp(self):
        self.patient = User.objects.create_user(
            email='fav@example.com', password='password123', first_name='Пациент',
            role=User.Role.PATIENT,
        )
        self.visible_doctor = self._doctor('visible')
        self.hidden_doctor = self._doctor('hidden', published=False)
        self.blocked_doctor = self._doctor('blocked', active=False)

        self.visible_clinic = self._clinic('Видимая')
        self.hidden_clinic = self._clinic('Скрытая', published=False)

        self.active_service = Service.objects.create(
            name='Активная', category='Приём', clinic=self.visible_clinic,
        )
        self.inactive_service = Service.objects.create(
            name='Отключённая', category='Приём', clinic=self.visible_clinic, is_active=False,
        )
        self.hidden_clinic_service = Service.objects.create(
            name='Услуга скрытой', category='Приём', clinic=self.hidden_clinic,
        )

        self.patient.favorite_doctors.add(
            self.visible_doctor, self.hidden_doctor, self.blocked_doctor,
        )
        self.patient.favorite_clinics.add(self.visible_clinic, self.hidden_clinic)
        self.patient.favorite_services.add(
            self.active_service, self.inactive_service, self.hidden_clinic_service,
        )
        self.client.force_authenticate(self.patient)

    def _doctor(self, name, *, published=True, active=True):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123', first_name=name,
            role=User.Role.DOCTOR,
        )
        if not active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        return DoctorProfile.objects.create(user=user, is_published=published)

    def _clinic(self, name, *, published=True):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123', first_name=name,
            role=User.Role.CLINIC,
        )
        return ClinicProfile.objects.create(user=user, name=name, is_published=published)

    def test_hides_unpublished_and_inactive(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(
            [item['id'] for item in data['doctors']], [self.visible_doctor.user_id],
        )
        self.assertEqual([item['name'] for item in data['clinics']], ['Видимая'])
        self.assertEqual([item['name'] for item in data['services']], ['Активная'])

    def test_post_response_uses_same_rule(self):
        another = self._doctor('another')
        response = self.client.post(
            self.url, {'target_type': 'doctor', 'target_id': another.user_id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            {item['id'] for item in response.data['data']['doctors']},
            {self.visible_doctor.user_id, another.user_id},
        )
