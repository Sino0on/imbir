from django.db import migrations


def blank_phones_to_null(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(phone='').update(phone=None)


def null_phones_to_blank(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(phone__isnull=True).update(phone='')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0014_user_phone_nullable'),
    ]

    operations = [
        migrations.RunPython(blank_phones_to_null, null_phones_to_blank),
    ]
