from rest_framework import serializers

MAX_SERVICE_DURATION_MINUTES = 24 * 60


def validate_service_duration(value):
    """Длительность услуги в минутах: пусто (null) или целое от 1 до суток.
    0 модель пропускает, но запись с такой услугой всё равно считалась бы
    30-минутной (appointments.utils.appointment_duration_minutes)."""
    if value is not None and not 1 <= value <= MAX_SERVICE_DURATION_MINUTES:
        raise serializers.ValidationError(
            f'Длительность — от 1 до {MAX_SERVICE_DURATION_MINUTES} минут.'
        )
    return value
