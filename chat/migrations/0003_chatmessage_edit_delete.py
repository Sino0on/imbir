from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatmessage',
            name='edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
    ]
