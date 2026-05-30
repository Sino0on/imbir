from rest_framework import serializers
from users.models import ClinicBranch, ClinicInvite


class ClinicBranchUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicBranch
        fields = ('id', 'name', 'address', 'phone', 'schedule')
        read_only_fields = ('id',)


class ClinicInviteSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClinicInvite
        fields = ('id', 'branch', 'expires_at', 'is_active', 'is_valid', 'created_at')
        read_only_fields = ('id', 'is_valid', 'created_at')


class ClinicInviteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicInvite
        fields = ('branch', 'expires_at')

    def validate_branch(self, branch):
        clinic = self.context['clinic']
        if branch and branch.clinic_id != clinic.pk:
            raise serializers.ValidationError('Филиал не принадлежит этой клинике')
        return branch

    def create(self, validated_data):
        return ClinicInvite.objects.create(clinic=self.context['clinic'], **validated_data)
