from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('references', '0002_add_specialization'),
        ('users', '0006_clinicprofile_tags_doctorprofile_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='doctorprofile',
            name='primary_specializations_new',
            field=models.ManyToManyField(blank=True, related_name='doctors_primary', to='references.specialization'),
        ),
        migrations.AddField(
            model_name='doctorprofile',
            name='narrow_specializations_new',
            field=models.ManyToManyField(blank=True, related_name='doctors_narrow', to='references.specialization'),
        ),
        migrations.AddField(
            model_name='clinicprofile',
            name='primary_specializations_new',
            field=models.ManyToManyField(blank=True, related_name='clinics_primary', to='references.specialization'),
        ),
        migrations.AddField(
            model_name='clinicprofile',
            name='narrow_specializations_new',
            field=models.ManyToManyField(blank=True, related_name='clinics_narrow', to='references.specialization'),
        ),
    ]
