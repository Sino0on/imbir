from rest_framework import serializers

from .models import Specialization, SiteSettings, AccountStatus


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


class AccountStatusSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = AccountStatus
        fields = ('id', 'name', 'description', 'percent', 'image')

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url
