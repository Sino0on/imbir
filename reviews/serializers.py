from django.db.models import Avg, Count
from rest_framework import serializers
from .models import Review


def _update_rating(review):
    """Пересчитывает кэшированный рейтинг и кол-во отзывов у цели."""
    if review.target_type == Review.TargetType.DOCTOR and review.doctor:
        profile = review.doctor
        agg = Review.objects.filter(doctor=profile).aggregate(avg=Avg('rating'), cnt=Count('id'))
        profile.rating = round(agg['avg'] or 0, 2)
        profile.reviews_count = agg['cnt']
        profile.save(update_fields=['rating', 'reviews_count'])
    elif review.target_type == Review.TargetType.CLINIC and review.clinic:
        profile = review.clinic
        agg = Review.objects.filter(clinic=profile).aggregate(avg=Avg('rating'), cnt=Count('id'))
        profile.rating = round(agg['avg'] or 0, 2)
        profile.reviews_count = agg['cnt']
        profile.save(update_fields=['rating', 'reviews_count'])


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'author', 'target_type', 'target_id', 'rating', 'text', 'reply', 'created_at')
        read_only_fields = ('id', 'author', 'target_type', 'target_id', 'reply', 'created_at')

    def get_author(self, obj):
        return {
            'id': obj.author.id,
            'full_name': obj.author.full_name,
        }

    def get_target_id(self, obj):
        if obj.target_type == Review.TargetType.DOCTOR and obj.doctor:
            return obj.doctor.user_id
        elif obj.target_type == Review.TargetType.CLINIC and obj.clinic:
            return obj.clinic.user_id
        return None

    def get_reply(self, obj):
        if obj.reply_text:
            return {
                'text': obj.reply_text,
                'created_at': obj.reply_created_at,
            }
        return None

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        _update_rating(instance)
        return instance


class ReviewCreateSerializer(serializers.ModelSerializer):
    target_id = serializers.IntegerField(write_only=True)
    appointment_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Review
        fields = ('target_type', 'target_id', 'appointment_id', 'rating', 'text')

    def validate(self, data):
        from users.models import DoctorProfile, ClinicProfile
        from appointments.models import Appointment

        request = self.context['request']
        target_type = data['target_type']
        target_id = data.pop('target_id')
        appointment_id = data.pop('appointment_id', None)

        if target_type == Review.TargetType.DOCTOR:
            try:
                data['doctor'] = DoctorProfile.objects.get(user_id=target_id, is_published=True)
            except DoctorProfile.DoesNotExist:
                raise serializers.ValidationError({'target_id': 'Врач не найден.'})
        elif target_type == Review.TargetType.CLINIC:
            try:
                data['clinic'] = ClinicProfile.objects.get(user_id=target_id, is_published=True)
            except ClinicProfile.DoesNotExist:
                raise serializers.ValidationError({'target_id': 'Клиника не найдена.'})

        if appointment_id is not None:
            try:
                appt = Appointment.objects.get(id=appointment_id, patient=request.user)
            except Appointment.DoesNotExist:
                raise serializers.ValidationError(
                    {'appointment_id': 'Запись не найдена или не принадлежит вам.'}
                )
            if Review.objects.filter(appointment=appt).exists():
                raise serializers.ValidationError('На эту запись уже оставлен отзыв.')
            data['appointment'] = appt

        return data

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        review = Review.objects.create(**validated_data)
        _update_rating(review)
        return review
