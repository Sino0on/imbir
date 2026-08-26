# Регистрация клиники — как правильно отправлять данные

`POST /api/auth/register/clinic/`

## Главное, что нужно понимать

1. Это **многошаговая форма** (7 шагов), но на бэкенд она отправляется **одним запросом**.
2. Каждый шаг (`step1`...`step7`) передаётся как **строка с JSON** (не вложенный объект, а именно `JSON.stringify(...)`), даже если запрос идёт как `multipart/form-data`.
3. Перед отправкой формы **обязательно** нужно подтвердить email или телефон кодом — иначе на финальном шаге придёт ошибка. Это отдельный шаг ДО вызова `register/clinic/`.
4. `Content-Type`: `multipart/form-data`, если прикладываете файлы (лого/фото/документы) напрямую. Если файлов нет — можно и `application/json`.

---

## Шаг 0 (обязательный): подтверждение email или телефона

Без этого `register/clinic/` вернёт 400 с текстом «Подтвердите email или телефон кодом перед регистрацией».

**Email:**
```http
POST /api/auth/verify/email/request/
Content-Type: application/json

{ "email": "clinic@example.com" }
```
Пользователю на почту придёт 4-значный код. Дальше:
```http
POST /api/auth/verify/email/confirm/
Content-Type: application/json

{ "email": "clinic@example.com", "code": "1234" }
```

**Телефон** — то же самое, но:
```http
POST /api/auth/verify/phone/request/
{ "phone": "+996700123456" }

POST /api/auth/verify/phone/confirm/
{ "phone": "+996700123456", "code": "1234" }
```

Подтверждение действительно **24 часа** — за это время нужно успеть отправить `register/clinic/` с тем же email (или телефоном), который подтверждали. Проверять можно как email, так и телефон — достаточно одного из них.

> Перед `verify/email/request/` email/телефон должны быть свободны — если уже заняты существующим аккаунтом, `register/clinic/` тоже отклонит их отдельной проверкой на уникальность. Можно заранее спросить `POST /api/auth/email/check/` — `{"email": "..."}` → `{"data": {"available": true/false}}`.

---

## Сам запрос

```
POST /api/auth/register/clinic/
Content-Type: multipart/form-data
```

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `password` | string | да | Пароль аккаунта клиники, минимум 8 символов |
| `step1` | JSON-строка | да | См. ниже |
| `step2` | JSON-строка | да | См. ниже |
| `step3` | JSON-строка | да | См. ниже |
| `step4` | JSON-строка | да | См. ниже |
| `step5` | JSON-строка | да | См. ниже |
| `step6` | JSON-строка | да | См. ниже |
| `step7` | JSON-строка | да | См. ниже |
| `logo` | файл или URL-строка | нет | Лого клиники — прикладывается как обычный файл в multipart, либо строкой-URL, если файл уже где-то загружен |
| `photos` | файл(ы) | нет | Фото клиники — можно приложить несколько (поле `photos` повторить для каждого файла) |
| `documents` | файл(ы) | нет | Юридические документы клиники — аналогично `photos` |

### step1 — основная информация
```json
{
  "name": "Клиника Ромашка",
  "type": "Многопрофильная",
  "description": "Современная клиника полного цикла"
}
```
- `name` — обязательно, непустая строка.
- `type`, `description` — опционально, произвольный текст (готового справочника типов нет).

### step2 — контакты и локация
```json
{
  "email": "clinic@example.com",
  "phone": "+996700123456",
  "country": "Кыргызстан",
  "city": "Бишкек",
  "address": "ул. Чуй 123",
  "website": "https://clinic.example.com",
  "location": { "lat": 42.8746, "lng": 74.5698 }
}
```
- `email` — обязательно, должен совпадать с тем, что подтверждали на шаге 0 (или быть подтверждённым телефоном).
- `phone` — опционально, но если указан — должен быть свободен (уникален по всей платформе).
- `location` — опционально, `lat`/`lng` — числа.

### step3 — расписание
```json
{
  "schedule": {
    "monday":    { "enabled": true,  "from": "09:00", "to": "18:00" },
    "tuesday":   { "enabled": true,  "from": "09:00", "to": "18:00" },
    "wednesday": { "enabled": true,  "from": "09:00", "to": "18:00" },
    "thursday":  { "enabled": true,  "from": "09:00", "to": "18:00" },
    "friday":    { "enabled": true,  "from": "09:00", "to": "18:00" },
    "saturday":  { "enabled": false, "from": "10:00", "to": "15:00" },
    "sunday":    { "enabled": false, "from": "10:00", "to": "15:00" }
  },
  "lunch_break": { "from": "13:00", "to": "14:00" },
  "emergency_24_7": false
}
```
- Ключи `schedule` — дни недели на английском, нижний регистр (`monday`...`sunday`).
- Время — строка `"HH:MM"`.
- `lunch_break` — один общий перерыв на все рабочие дни (не по дням).

### step4 — юридические данные
```json
{
  "legal_name": "ОсОО Ромашка Мед",
  "reg_number": "123456789",
  "license_number": "LIC-000111",
  "license_date": "2020-05-01",
  "license_authority": "Минздрав КР"
}
```
- Все поля опциональны (текст/дата в формате `YYYY-MM-DD`).
- Файлы документов — через multipart-поле `documents` (см. таблицу выше), а не внутри этого JSON.

### step5 — специализации
```json
{
  "additional_services": "Лабораторная диагностика, вызов врача на дом",
  "primary_specializations": [3, 7],
  "narrow_specializations": [12]
}
```
- `primary_specializations` / `narrow_specializations` — массивы **числовых ID** из справочника `GET /api/references/specializations/`, не текст.

### step6 — оборудование и условия
```json
{
  "equipment": ["УЗИ-аппарат", "Рентген"],
  "patient_conditions": ["Парковка", "Доступ для маломобильных"],
  "payment_methods": ["Наличные", "Карта", "Страховка"]
}
```
- Все три поля — массивы произвольных строк, готового справочника нет.

### step7 — согласия
```json
{
  "agree_terms": true,
  "agree_privacy": true,
  "agree_data_processing": true,
  "agree_publishing": true
}
```
- Все четыре поля **обязательно `true`** — иначе 400 с указанием, какое именно согласие не отмечено.

---

## Пример полного запроса (curl, multipart)

```bash
curl -X POST https://api.imbir.kg/api/auth/register/clinic/ \
  -F 'password=SuperSecret123' \
  -F 'step1={"name":"Клиника Ромашка","type":"Многопрофильная","description":"..."}' \
  -F 'step2={"email":"clinic@example.com","phone":"+996700123456","country":"Кыргызстан","city":"Бишкек","address":"ул. Чуй 123"}' \
  -F 'step3={"schedule":{"monday":{"enabled":true,"from":"09:00","to":"18:00"}},"lunch_break":{"from":"13:00","to":"14:00"},"emergency_24_7":false}' \
  -F 'step4={"legal_name":"ОсОО Ромашка Мед","reg_number":"123456789"}' \
  -F 'step5={"additional_services":"","primary_specializations":[3],"narrow_specializations":[]}' \
  -F 'step6={"equipment":[],"patient_conditions":[],"payment_methods":["Наличные","Карта"]}' \
  -F 'step7={"agree_terms":true,"agree_privacy":true,"agree_data_processing":true,"agree_publishing":true}' \
  -F 'logo=@/path/to/logo.png' \
  -F 'photos=@/path/to/photo1.jpg' \
  -F 'photos=@/path/to/photo2.jpg'
```

## Успешный ответ — `201 Created`

```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": {
    "id": 42,
    "email": "clinic@example.com",
    "first_name": "Клиника Ромашка",
    "role": "clinic",
    "...": "..."
  }
}
```
`access`/`refresh` — обычные JWT-токены, клиника сразу залогинена, дальше работает как любой авторизованный пользователь (`Authorization: Bearer <access>`).

## Частые ошибки

| Ошибка | Причина |
|---|---|
| `"Подтвердите email или телефон кодом перед регистрацией..."` | Пропущен шаг 0, либо прошло больше 24 часов с момента подтверждения |
| `"Пользователь с таким email уже существует"` | Email уже зарегистрирован — проверить заранее через `/api/auth/email/check/` |
| `"Пользователь с таким номером телефона уже зарегистрирован"` | Телефон занят другим аккаунтом |
| `"Ожидается JSON-строка"` в поле `stepN` | Шаг отправлен как объект/массив напрямую, а не как `JSON.stringify(...)` строка |
| `{"step7": "Необходимо принять условия использования"}` (и т.п.) | Одно из полей `agree_*` не `true` |
