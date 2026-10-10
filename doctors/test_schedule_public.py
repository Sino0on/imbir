from rest_framework import status
from rest_framework.test import APITestCase

from users.models import DoctorProfile, User


class DoctorDetailScheduleTests(APITestCase):
    """K13: карточка врача отдаёт недельный график — календарь записи гасит по
    нему выходные, а не предлагает дни, где слотов не будет вовсе."""

    def make_doctor(self, **profile):
        user = User.objects.create_user(
            email=f'sched-{User.objects.count()}@example.com', password='password123',
            first_name='Doc', role=User.Role.DOCTOR,
        )
        DoctorProfile.objects.create(user=user, is_published=True, city='Бишкек', **profile)
        response = self.client.get(f'/api/doctors/{user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_schedule_marks_days_off_by_the_same_rules_as_slots(self):
        data = self.make_doctor(
            schedule={
                'monday': {'enabled': True, 'from': '09:00', 'to': '18:00'},
                'tuesday': {'enabled': False, 'from': '09:00', 'to': '18:00'},
                # Без времени — слотов не будет, значит и в календаре выходной.
                'wednesday': {'enabled': True, 'from': None, 'to': None},
                'friday': {'enabled': True, 'from': '00:00', 'to': '23:59'},
            },
            lunch_break={'from': '13:00', 'to': '14:00'},
        )
        schedule = data['schedule']
        self.assertEqual(
            list(schedule),
            ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
        )
        self.assertEqual(schedule['monday'], {'enabled': True, 'from': '09:00', 'to': '18:00'})
        self.assertFalse(schedule['tuesday']['enabled'])
        self.assertFalse(schedule['wednesday']['enabled'])
        self.assertFalse(schedule['thursday']['enabled'])
        self.assertEqual(schedule['friday'], {'enabled': True, 'from': '00:00', 'to': '24:00'})
        self.assertEqual(data['lunch_break'], {'from': '13:00', 'to': '14:00'})

    def test_doctor_without_schedule_has_no_working_days(self):
        data = self.make_doctor()
        self.assertTrue(all(not day['enabled'] for day in data['schedule'].values()))
        self.assertIsNone(data['lunch_break'])
