from django.urls import path
from .views import (
    CitiesView,
    SpecializationsView,
    ClinicTypesView,
    LanguagesView,
    EquipmentView,
    ConditionsView,
    PaymentMethodsView,
    CountryCodesView,
)

urlpatterns = [
    path('cities/', CitiesView.as_view(), name='ref-cities'),
    path('specializations/', SpecializationsView.as_view(), name='ref-specializations'),
    path('clinic-types/', ClinicTypesView.as_view(), name='ref-clinic-types'),
    path('languages/', LanguagesView.as_view(), name='ref-languages'),
    path('equipment/', EquipmentView.as_view(), name='ref-equipment'),
    path('conditions/', ConditionsView.as_view(), name='ref-conditions'),
    path('payment-methods/', PaymentMethodsView.as_view(), name='ref-payment-methods'),
    path('country-codes/', CountryCodesView.as_view(), name='ref-country-codes'),
]
