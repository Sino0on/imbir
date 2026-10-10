from rest_framework import status
from rest_framework.test import APITestCase

from services.models import Service
from users.models import ClinicProfile, DoctorClinicLink, DoctorProfile, User


class ClinicDetailDoctorsAndServicesTests(APITestCase):
    """GET /api/clinics/{id}/ — врачи и услуги самой клиники: страница клиники
    берёт их отсюда, а не из общего каталога."""

    def setUp(self):
        clinic_user = User.objects.create_user(
            email='clinic@example.com', password='password123',
            first_name='Клиника', last_name='Тест', role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(
            user=clinic_user, name='Клиника', city='Ош', is_published=True,
        )
        self.url = f'/api/clinics/{clinic_user.id}/'

    def _doctor(self, name, *, published=True, active=True, rating=0,
                reviews=0, online=False, link_active=True):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123',
            first_name=name, last_name='Врач', role=User.Role.DOCTOR,
        )
        if not active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        doctor = DoctorProfile.objects.create(
            user=user, city='Ош', is_published=published, rating=rating,
            reviews_count=reviews, is_online_available=online,
        )
        DoctorClinicLink.objects.create(
            doctor=doctor, clinic=self.clinic, is_active=link_active,
        )
        return doctor

    def _get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_hides_unpublished_and_inactive_doctors(self):
        visible = self._doctor('visible')
        self._doctor('hidden', published=False)
        self._doctor('blocked', active=False)
        self._doctor('detached', link_active=False)

        ids = [d['id'] for d in self._get()['doctors']]
        self.assertEqual(ids, [visible.user_id])

    def test_doctors_have_card_fields_and_rating_order(self):
        self._doctor('low', rating='3.50', reviews=2)
        top = self._doctor('top', rating='4.90', reviews=7, online=True)

        doctors = self._get()['doctors']
        self.assertEqual(doctors[0]['id'], top.user_id)
        self.assertEqual(doctors[0]['reviews_count'], 7)
        self.assertIs(doctors[0]['is_online_available'], True)
        self.assertIs(doctors[1]['is_online_available'], False)

    def test_services_have_photo_field(self):
        Service.objects.create(name='УЗИ', category='Диагностика', clinic=self.clinic, duration=30)
        Service.objects.create(name='Старое', category='Диагностика', clinic=self.clinic, is_active=False)

        services = self._get()['services']
        self.assertEqual([s['name'] for s in services], ['УЗИ'])
        self.assertIn('photo', services[0])
        self.assertIsNone(services[0]['photo'])
        self.assertEqual(services[0]['duration'], 30)
