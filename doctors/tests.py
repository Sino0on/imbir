from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from users.models import DoctorProfile

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
