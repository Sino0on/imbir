from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from references.models import SiteSettings, Specialization
from reviews.models import Review
from users.models import ClinicProfile, DoctorProfile


class SpecializationReferenceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.unused = Specialization.objects.create(name='Флеболог')
        self.doctor_specialization = Specialization.objects.create(name='Кардиология')
        self.clinic_specialization = Specialization.objects.create(name='Эндокринология')
        doctor_user = get_user_model().objects.create_user(
            email='reference-doctor@example.com', password='Testpassword123!', role='doctor',
        )
        clinic_user = get_user_model().objects.create_user(
            email='reference-clinic@example.com', password='Testpassword123!', role='clinic',
        )
        doctor = DoctorProfile.objects.create(user=doctor_user, is_published=True)
        clinic = ClinicProfile.objects.create(user=clinic_user, name='Клиника', is_published=True)
        doctor.primary_specializations.add(self.doctor_specialization)
        clinic.primary_specializations.add(self.clinic_specialization)

    def ids(self, **params):
        response = self.client.get('/api/references/specializations/', params)
        self.assertEqual(response.status_code, 200)
        return {item['id'] for item in response.data['data']}

    def test_catalog_excludes_unused_specializations(self):
        self.assertEqual(self.ids(), {self.doctor_specialization.id, self.clinic_specialization.id})

    def test_role_filter_is_preserved(self):
        self.assertEqual(self.ids(type='doctor'), {self.doctor_specialization.id})
        self.assertEqual(self.ids(type='clinic'), {self.clinic_specialization.id})

    def test_registration_receives_full_reference(self):
        self.assertEqual(
            self.ids(include_unused='true'),
            {self.unused.id, self.doctor_specialization.id, self.clinic_specialization.id},
        )
        self.assertIn(self.unused.id, self.ids(type='doctor', include_unused='1'))

    def test_false_does_not_expand_catalog(self):
        self.assertNotIn(self.unused.id, self.ids(include_unused='false'))


class RegistrationSpecializationSeedTests(TestCase):
    def test_seed_reuses_existing_names_and_can_be_repeated(self):
        existing = Specialization.objects.create(name='Кардиология')
        fibroscan = Specialization.objects.create(name='фиброскан')
        call_command('seed_registration_specializations', verbosity=0)
        call_command('seed_registration_specializations', verbosity=0)
        self.assertEqual(Specialization.objects.count(), 14)
        self.assertEqual(Specialization.objects.get(name='Кардиология').id, existing.id)
        self.assertEqual(Specialization.objects.get(name='фиброскан').id, fibroscan.id)
        self.assertFalse(Specialization.objects.filter(name='Кардиолог').exists())


class UserAccountStatusPercentTests(TestCase):
    """Доля положительных/отрицательных отзывов считается по самим отзывам,
    а не выводится из среднего балла."""

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.author = User.objects.create_user(
            email='status-author@example.com', password='Testpassword123!', role='patient',
        )
        self.doctors = []
        for i in range(3):
            user = User.objects.create_user(
                email=f'status-doctor{i}@example.com', password='Testpassword123!', role='doctor',
            )
            self.doctors.append(DoctorProfile.objects.create(user=user, is_published=True))

    def leave(self, *ratings):
        for doctor, rating in zip(self.doctors, ratings):
            Review.objects.create(
                author=self.author, target_type='doctor', doctor=doctor, rating=rating,
            )

    def data(self):
        response = self.client.get(f'/api/references/user-status/{self.author.id}/')
        self.assertEqual(response.status_code, 200)
        return response.data['data']

    def test_only_four_star_reviews_have_no_negative_share(self):
        self.leave(4, 4)
        data = self.data()
        self.assertEqual(data['percent'], 80.0)
        self.assertEqual(data['positive_percent'], 100.0)
        self.assertEqual(data['negative_percent'], 0.0)

    def test_single_one_star_review_is_fully_negative(self):
        self.leave(1)
        data = self.data()
        self.assertEqual(data['positive_percent'], 0.0)
        self.assertEqual(data['negative_percent'], 100.0)

    def test_mixed_reviews_split_by_count_and_neutral_excluded(self):
        self.leave(5, 1, 3)
        data = self.data()
        self.assertEqual(data['positive_percent'], 33.33)
        self.assertEqual(data['negative_percent'], 33.33)

    def test_no_reviews_returns_nulls(self):
        data = self.data()
        self.assertIsNone(data['percent'])
        self.assertIsNone(data['positive_percent'])
        self.assertIsNone(data['negative_percent'])


class SiteSettingsUpdatedAtTests(TestCase):
    def test_site_settings_expose_updated_at(self):
        SiteSettings.load().save()
        response = APIClient().get('/api/references/site-settings/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('updated_at', response.data['data'])
        self.assertTrue(response.data['data']['updated_at'])
        # Старые поля остаются на месте — задеплоенный фронт их читает.
        self.assertIn('terms_text', response.data['data'])
