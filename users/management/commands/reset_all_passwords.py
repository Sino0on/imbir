from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from users.models import User

DEFAULT_PASSWORD = "Test1234!"


class Command(BaseCommand):
    help = 'Меняет пароль всех пользователей на заданное значение (по умолчанию Test1234!)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password', default=DEFAULT_PASSWORD,
            help=f'Новый пароль для всех пользователей (по умолчанию {DEFAULT_PASSWORD})',
        )
        parser.add_argument(
            '--yes', action='store_true',
            help='Подтвердить выполнение без интерактивного запроса',
        )

    def handle(self, *args, **options):
        password = options['password']
        confirmed = options['yes']

        users = User.objects.all()
        count = users.count()

        if not settings.DEBUG:
            self.stderr.write(self.style.WARNING(
                'DEBUG=False — похоже, это не dev/staging окружение.'
            ))

        if not confirmed:
            answer = input(
                f'Сменить пароль у ВСЕХ пользователей ({count} шт.) на "{password}"? [y/N]: '
            )
            if answer.strip().lower() != 'y':
                self.stdout.write('Отменено.')
                return

        hashed = make_password(password)
        updated = users.update(password=hashed)

        self.stdout.write(self.style.SUCCESS(
            f'Готово! Пароль обновлён у {updated} пользователей.'
        ))
