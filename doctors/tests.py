from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from users.models import DoctorProfile
from doctors.models import Interview

User = get_user_model()

class DoctorAvailableSlotsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='doctor@example.com',
            password='password123',
            first_name='Doctor',
            last_name='Who',
            role=User.Role.DOCTOR
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.user,
            is_published=True,
            schedule={
                "friday": {"to": "17:00", "from": "09:00", "enabled": True},
                "monday": {"to": "18:00", "from": "09:00", "enabled": True},
                "sunday": {"to": None, "from": None, "enabled": False},
                "tuesday": {"to": "18:00", "from": "09:00", "enabled": True},
                "saturday": {"to": None, "from": None, "enabled": False},
                "thursday": {"to": "18:00", "from": "09:00", "enabled": True},
                "wednesday": {"to": "16:00", "from": "10:00", "enabled": True}
            },
            lunch_break={"from": "13:00", "to": "14:00"}
        )
        self.url = f'/api/doctors/{self.user.id}/available-slots/'

    def test_available_slots_monday_success(self):
        # 2026-07-06 is Monday, working 09:00 to 18:00
        response = self.client.get(self.url, {'date': '2026-07-06'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date'], '2026-07-06')
        
        slots = response.data['slots']
        self.assertEqual(len(slots), 18)
        
        self.assertEqual(slots[0]['time'], '09:00')
        self.assertEqual(slots[-1]['time'], '17:30')
        
        # Check lunch break slots (13:00 - 14:00 should not be available)
        lunch_slots = [s for s in slots if s['time'] in ['13:00', '13:30']]
        for s in lunch_slots:
            self.assertFalse(s['available'])

    def test_available_slots_sunday_disabled(self):
        # 2026-07-05 is Sunday
        response = self.client.get(self.url, {'date': '2026-07-05'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['slots']), 0)


class DoctorInterviewsAPITests(APITestCase):
    def setUp(self):
        # Create a doctor user and profile
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

        # Create a patient user
        self.patient_user = User.objects.create_user(
            email='patient@example.com',
            password='password123',
            first_name='John',
            last_name='Doe',
            role=User.Role.PATIENT
        )

        # URLs
        self.list_create_url = '/api/doctor/interviews/'
        self.public_detail_url = f'/api/doctors/{self.doctor_user.id}/'

    def test_interviews_access_permissions(self):
        # Try to list without login
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Try to list as patient
        self.client.force_authenticate(user=self.patient_user)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_interview_crud_lifecycle(self):
        self.client.force_authenticate(user=self.doctor_user)

        # 1. List (initially empty)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 0)

        # 2. Create
        data = {
            'title': 'Интервью о здоровье',
            'video_url': 'https://youtube.com/watch?v=12345',
            'priority': 2
        }
        response = self.client.post(self.list_create_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Интервью о здоровье')
        self.assertEqual(response.data['video_url'], 'https://youtube.com/watch?v=12345')
        self.assertEqual(response.data['priority'], 2)
        interview_id = response.data['id']

        # Verify in DB
        self.assertTrue(Interview.objects.filter(id=interview_id, doctor=self.doctor_profile).exists())

        # 3. Retrieve & Update
        detail_url = f'{self.list_create_url}{interview_id}/'
        update_data = {
            'title': 'Обновленное интервью',
            'video_url': 'https://youtube.com/watch?v=updated',
            'priority': 3
        }
        response = self.client.put(detail_url, update_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Обновленное интервью')
        self.assertEqual(response.data['priority'], 3)

        # 4. List now has 1 item
        response = self.client.get(self.list_create_url)
        self.assertEqual(len(response.data['data']), 1)

        # 5. Delete
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Interview.objects.filter(id=interview_id).exists())

    def test_interviews_ordering_and_public_api(self):
        # Create a few interviews
        Interview.objects.create(doctor=self.doctor_profile, title='Low', video_url='http://yt/low', priority=0)
        Interview.objects.create(doctor=self.doctor_profile, title='High', video_url='http://yt/high', priority=3)
        Interview.objects.create(doctor=self.doctor_profile, title='Medium', video_url='http://yt/med', priority=1)

        # Retrieve public detail
        response = self.client.get(self.public_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        interviews = response.data['interviews']
        self.assertEqual(len(interviews), 3)
        # Verify ordering: priority 3 -> 1 -> 0
        self.assertEqual(interviews[0]['title'], 'High')
        self.assertEqual(interviews[1]['title'], 'Medium')
        self.assertEqual(interviews[2]['title'], 'Low')

