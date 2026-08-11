from rest_framework import serializers

from .models import Specialization, SiteSettings


class SpecializationSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Specialization
        fields = ('id', 'name', 'photo')

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = (
            'facebook_url', 'instagram_url', 'twitter_url', 'linkedin_url',
            'contact_email', 'contact_phone', 'address',
            'terms_text', 'privacy_policy_text',
        )
