from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from reviews.admin import ReviewAdmin
from reviews.models import Review
from users.models import ClinicProfile, DoctorProfile, User


class ReviewAdminRatingTests(TestCase):
    """K57: правка и удаление отзыва в админке пересчитывают рейтинг цели."""

    def setUp(self):
        self.admin = ReviewAdmin(Review, AdminSite())
        self.request = RequestFactory().post('/admin/')
        self.doctor = self._doctor('doc1')
        self.other_doctor = self._doctor('doc2')
        clinic_user = User.objects.create_user(
            email='clinic@example.com', password='password123', first_name='Клиника',
            role=User.Role.CLINIC,
        )
        self.clinic = ClinicProfile.objects.create(user=clinic_user, name='Клиника')
        self.reviews = [
            self._review(f'p{i}', rating, doctor=self.doctor) for i, rating in enumerate((5, 3))
        ]
        self.clinic_review = self._review('pc', 4, clinic=self.clinic)

    def _doctor(self, name):
        user = User.objects.create_user(
            email=f'{name}@example.com', password='password123', first_name=name,
            role=User.Role.DOCTOR,
        )
        return DoctorProfile.objects.create(user=user)

    def _review(self, author_name, rating, *, doctor=None, clinic=None):
        author = User.objects.create_user(
            email=f'{author_name}@example.com', password='password123',
            first_name=author_name, role=User.Role.PATIENT,
        )
        review = Review.objects.create(
            author=author, rating=rating, doctor=doctor, clinic=clinic,
            target_type=Review.TargetType.DOCTOR if doctor else Review.TargetType.CLINIC,
        )
        # Как после создания через API: кэш рейтинга актуален.
        from reviews.serializers import _update_rating
        _update_rating(review)
        return review

    def _rating(self, profile):
        profile.refresh_from_db()
        return profile.rating, profile.reviews_count

    def test_edit_recalculates(self):
        review = self.reviews[1]
        review.rating = 1
        self.admin.save_model(self.request, review, form=None, change=True)
        self.assertEqual(self._rating(self.doctor), (Decimal('3.00'), 2))

    def test_moving_review_recalculates_both_targets(self):
        review = self.reviews[1]
        review.doctor = self.other_doctor
        self.admin.save_model(self.request, review, form=None, change=True)
        self.assertEqual(self._rating(self.doctor), (Decimal('5.00'), 1))
        self.assertEqual(self._rating(self.other_doctor), (Decimal('3.00'), 1))

    def test_delete_recalculates(self):
        self.admin.delete_model(self.request, self.reviews[0])
        self.assertEqual(self._rating(self.doctor), (Decimal('3.00'), 1))

    def test_bulk_delete_recalculates(self):
        self.admin.delete_queryset(self.request, Review.objects.all())
        self.assertEqual(self._rating(self.doctor), (Decimal('0.00'), 0))
        self.assertEqual(self._rating(self.clinic), (Decimal('0.00'), 0))
