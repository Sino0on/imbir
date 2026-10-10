from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from references.models import Specialization
from users.models import ClinicProfile, DoctorProfile, User


def _doctor(email, first, last, patronymic='', *, specs=(), narrow=(), rating=0, reviews=0,
            city='Бишкек', published=True):
    user = User.objects.create_user(
        email=email, password='password123', first_name=first, last_name=last,
        patronymic=patronymic, role=User.Role.DOCTOR,
    )
    doctor = DoctorProfile.objects.create(
        user=user, city=city, is_published=published, rating=rating, reviews_count=reviews,
    )
    doctor.primary_specializations.set(specs)
    doctor.narrow_specializations.set(narrow)
    return doctor


def _clinic(name, *, specs=(), narrow=(), rating=0, reviews=0, city='Бишкек'):
    user = User.objects.create_user(
        email=f'{name}@example.com', password='password123', first_name=name,
        role=User.Role.CLINIC,
    )
    clinic = ClinicProfile.objects.create(
        user=user, name=name, city=city, is_published=True, rating=rating, reviews_count=reviews,
    )
    clinic.primary_specializations.set(specs)
    clinic.narrow_specializations.set(narrow)
    return clinic


class DoctorFullNameSearchTests(APITestCase):
    """K34: поиск по нескольким словам — каждое слово ищется в фамилии, имени,
    отчестве или специализации."""

    def setUp(self):
        cardio = Specialization.objects.create(name='Кардиолог')
        therapist = Specialization.objects.create(name='Терапевт')
        _doctor('ivanov@example.com', 'Иван', 'Иванов', 'Петрович', specs=[cardio])
        _doctor('petrov@example.com', 'Пётр', 'Петров', 'Олегович', specs=[therapist])
        _doctor('sidorov@example.com', 'Иван', 'Сидоров', 'Сергеевич', specs=[therapist])

    def _list_names(self, search):
        response = self.client.get('/api/doctors/', {'city': 'all', 'search': search})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {item['full_name'] for item in response.data['data']}

    def _search_names(self, url, q):
        response = self.client.get(url, {'q': q})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {item['full_name'] for item in response.data['doctors']}

    def test_last_and_first_name(self):
        self.assertEqual(self._list_names('Иванов Иван'), {'Иван Петрович Иванов'})

    def test_words_in_any_order(self):
        self.assertEqual(self._list_names('Иван Сидоров'), {'Иван Сергеевич Сидоров'})

    def test_patronymic(self):
        self.assertEqual(self._list_names('Сергеевич'), {'Иван Сергеевич Сидоров'})

    def test_name_and_specialization(self):
        self.assertEqual(self._list_names('Иван Терапевт'), {'Иван Сергеевич Сидоров'})

    def test_search_and_suggest_use_same_rule(self):
        for url in ('/api/search/', '/api/search/suggest/'):
            with self.subTest(url=url):
                self.assertEqual(
                    self._search_names(url, 'Иванов Иван'), {'Иван Петрович Иванов'},
                )


class SpecializationExactFilterTests(APITestCase):
    """K41: фильтр по специализации — точное название, а не подстрока."""

    def setUp(self):
        surgeon = Specialization.objects.create(name='Хирург')
        neuro = Specialization.objects.create(name='Нейрохирург')
        _doctor('surgeon@example.com', 'Анна', 'Хирургова', specs=[surgeon])
        _doctor('neuro@example.com', 'Борис', 'Нейронов', narrow=[neuro])
        _clinic('Хирургия', specs=[surgeon])
        _clinic('Нейроцентр', narrow=[neuro])

    def test_doctor_filter_is_exact(self):
        response = self.client.get('/api/doctors/', {'city': 'all', 'specialization': 'Хирург'})
        self.assertEqual(
            {item['full_name'] for item in response.data['data']}, {'Анна Хирургова'},
        )

    def test_clinic_filter_is_exact(self):
        response = self.client.get('/api/clinics/', {'city': 'all', 'specialization': 'Хирург'})
        self.assertEqual({item['name'] for item in response.data['data']}, {'Хирургия'})

    def test_clinic_search_matches_specialization(self):
        response = self.client.get('/api/clinics/', {'city': 'all', 'search': 'Нейрохирург'})
        self.assertEqual({item['name'] for item in response.data['data']}, {'Нейроцентр'})

    def test_global_search_finds_clinic_by_specialization(self):
        response = self.client.get('/api/search/', {'q': 'Нейрохирург'})
        self.assertEqual({item['name'] for item in response.data['clinics']}, {'Нейроцентр'})


class CatalogStableOrderingTests(APITestCase):
    """K40: при равных рейтинге и числе отзывов страницы не пересекаются."""

    def test_doctor_pages_do_not_overlap(self):
        for i in range(7):
            _doctor(f'd{i}@example.com', f'Имя{i}', f'Фамилия{i}', rating=4.5, reviews=3)
        seen = []
        for page in (1, 2, 3):
            response = self.client.get('/api/doctors/', {'city': 'all', 'page_size': 3, 'page': page})
            seen.extend(item['id'] for item in response.data['data'])
        self.assertEqual(len(seen), 7)
        self.assertEqual(seen, sorted(seen))

    def test_clinic_pages_do_not_overlap(self):
        for i in range(7):
            _clinic(f'Клиника {i}', rating=4.5, reviews=3)
        seen = []
        for page in (1, 2, 3):
            response = self.client.get('/api/clinics/', {'city': 'all', 'page_size': 3, 'page': page})
            seen.extend(item['id'] for item in response.data['data'])
        self.assertEqual(len(seen), 7)
        self.assertEqual(seen, sorted(seen))

    def test_ordering_ends_with_unique_id(self):
        # На SQLite порядок при равных ключах и так совпадает с порядком
        # вставки, поэтому тесты выше проходят и без хвоста id. Проверяем
        # саму сортировку: на Postgres без неё страницы пересекаются.
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        from clinics.views import ClinicListView
        from doctors.views import DoctorListView

        for view_class in (DoctorListView, ClinicListView):
            with self.subTest(view=view_class.__name__):
                view = view_class()
                view.request = Request(APIRequestFactory().get('/', {'city': 'all'}))
                self.assertEqual(
                    view.get_queryset().query.order_by[-1], 'id',
                )


class ProfileViewCounterTests(APITestCase):
    """K42: просмотр засчитывает POST .../view/, а не GET детальной."""

    def setUp(self):
        cache.clear()
        self.doctor = _doctor('viewed@example.com', 'Вера', 'Смотрова')
        self.clinic = _clinic('Просмотры')

    def _views(self, profile):
        profile.refresh_from_db()
        return profile.profile_views

    def test_doctor_view_counts(self):
        response = self.client.post(f'/api/doctors/{self.doctor.user_id}/view/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._views(self.doctor), 1)

    def test_clinic_view_counts(self):
        response = self.client.post(f'/api/clinics/{self.clinic.user_id}/view/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._views(self.clinic), 1)

    def test_detail_get_does_not_count(self):
        self.client.get(f'/api/doctors/{self.doctor.user_id}/')
        self.client.get(f'/api/clinics/{self.clinic.user_id}/')
        self.assertEqual(self._views(self.doctor), 0)
        self.assertEqual(self._views(self.clinic), 0)

    def test_owner_view_not_counted(self):
        self.client.force_authenticate(self.doctor.user)
        response = self.client.post(f'/api/doctors/{self.doctor.user_id}/view/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._views(self.doctor), 0)

    def test_unpublished_is_404(self):
        self.doctor.is_published = False
        self.doctor.save(update_fields=['is_published'])
        response = self.client.post(f'/api/doctors/{self.doctor.user_id}/view/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_throttled_per_profile(self):
        for _ in range(10):
            self.client.post(f'/api/doctors/{self.doctor.user_id}/view/')
        response = self.client.post(f'/api/doctors/{self.doctor.user_id}/view/')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(self._views(self.doctor), 10)
        # Лимит — на анкету, другая анкета считается.
        response = self.client.post(f'/api/clinics/{self.clinic.user_id}/view/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
