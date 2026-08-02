from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_migrate_specialization_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='doctorprofile',
            name='primary_specializations',
        ),
        migrations.RemoveField(
            model_name='doctorprofile',
            name='narrow_specializations',
        ),
        migrations.RemoveField(
            model_name='clinicprofile',
            name='primary_specializations',
        ),
        migrations.RemoveField(
            model_name='clinicprofile',
            name='narrow_specializations',
        ),
        migrations.RenameField(
            model_name='doctorprofile',
            old_name='primary_specializations_new',
            new_name='primary_specializations',
        ),
        migrations.RenameField(
            model_name='doctorprofile',
            old_name='narrow_specializations_new',
            new_name='narrow_specializations',
        ),
        migrations.RenameField(
            model_name='clinicprofile',
            old_name='primary_specializations_new',
            new_name='primary_specializations',
        ),
        migrations.RenameField(
            model_name='clinicprofile',
            old_name='narrow_specializations_new',
            new_name='narrow_specializations',
        ),
    ]
