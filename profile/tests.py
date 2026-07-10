from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from users.models import DoctorProfile, ClinicProfile
from services.models import Service

User = get_user_model()


class ProfileFavoritesTests(APITestCase):
    def setUp(self):
        # Create user
        self.user = User.objects.create_user(
            email='patient@example.com',
            password='password123',
            first_name='John',
            last_name='Doe',
            role=User.Role.PATIENT
        )

        # Create doctor profile
        self.doctor_user = User.objects.create_user(
            email='doctor@example.com',
            password='password123',
            first_name='Doctor',
            last_name='Who',
            role=User.Role.DOCTOR
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            is_published=True
        )

        # Create clinic profile
        self.clinic_user = User.objects.create_user(
            email='clinic@example.com',
            password='password123',
            first_name='Clinic',
            last_name='One',
            role=User.Role.CLINIC
        )
        self.clinic_profile = ClinicProfile.objects.create(
            user=self.clinic_user,
            name='Clinic One',
            is_published=True
        )

        # Create service
        self.service = Service.objects.create(
            name='Ультразвук',
            price=1500.00,
            category='diagnostics',
            is_active=True
        )

        self.favorites_url = '/api/profile/favorites/'

    def test_unauthenticated_access(self):
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_favorites_crud_lifecycle(self):
        self.client.force_authenticate(user=self.user)

        # 1. Get initial empty favorites
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['doctors']), 0)
        self.assertEqual(len(response.data['data']['clinics']), 0)
        self.assertEqual(len(response.data['data']['services']), 0)

        # 2. Add doctor
        response = self.client.post(self.favorites_url, {'target_type': 'doctor', 'target_id': self.doctor_user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['doctors']), 1)
        self.assertEqual(response.data['doctors'][0]['id'], self.doctor_user.id)

        # 3. Add clinic
        response = self.client.post(self.favorites_url, {'target_type': 'clinic', 'target_id': self.clinic_user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['clinics']), 1)
        self.assertEqual(response.data['clinics'][0]['id'], self.clinic_user.id)

        # 4. Add service
        response = self.client.post(self.favorites_url, {'target_type': 'service', 'target_id': self.service.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['services']), 1)
        self.assertEqual(response.data['services'][0]['id'], self.service.id)

        # 5. Retrieve list again and verify M2M
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['doctors']), 1)
        self.assertEqual(len(response.data['data']['clinics']), 1)
        self.assertEqual(len(response.data['data']['services']), 1)

        # 6. Delete doctor using body
        response = self.client.delete(self.favorites_url, {'target_type': 'doctor', 'target_id': self.doctor_user.id})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 7. Delete clinic using query parameters
        response = self.client.delete(f'{self.favorites_url}?target_type=clinic&target_id={self.clinic_user.id}')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 8. Check remaining service in favorites
        response = self.client.get(self.favorites_url)
        self.assertEqual(len(response.data['data']['doctors']), 0)
        self.assertEqual(len(response.data['data']['clinics']), 0)
        self.assertEqual(len(response.data['data']['services']), 1)

    def test_validation_errors(self):
        self.client.force_authenticate(user=self.user)

        # Non-existent doctor
        response = self.client.post(self.favorites_url, {'target_type': 'doctor', 'target_id': 9999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-existent clinic
        response = self.client.post(self.favorites_url, {'target_type': 'clinic', 'target_id': 9999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-existent service
        response = self.client.post(self.favorites_url, {'target_type': 'service', 'target_id': 9999})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
