# IMBIR — Техническое задание для бэкенда

> Версия: 1.0 | Дата: 2026-05-20  
> Фронтенд-разработчик: Сейтек  
> Базовый URL (текущий дев): `http://155.212.216.197:8054`

---

## 0. Общие требования

### Авторизация
- **JWT**: два токена — `access_token` (короткоживущий) и `refresh_token` (долгоживущий)
- Все защищённые эндпоинты требуют заголовка `Authorization: Bearer <access_token>`
- При истёкшем `access_token` — 401, фронт делает `POST /api/auth/refresh/`

### Формат ответов
```json
// Успех
{ "data": { ... }, "message": "OK" }

// Ошибка
{ "error": "Текст ошибки", "code": "ERROR_CODE" }
```

### Пагинация (для списков)
```json
{
  "data": [ ... ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

### Файлы
- Все URL файлов (фото, документы) — абсолютные: `https://domain.com/media/...`
- Загрузка через `POST /api/upload/` → возвращает URL

### CORS
```python
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "https://imbir.kg"]
CORS_ALLOW_CREDENTIALS = True
# CORS_ALLOW_ALL_ORIGINS нельзя использовать вместе с credentials
```

---

## 1. Авторизация и регистрация

### 1.1 Регистрация — клиент
```
POST /api/auth/register/client/
```
**Body:**
```json
{
  "first_name": "Иван",
  "last_name": "Петров",
  "email": "ivan@mail.com",
  "password": "секрет123",
  "phone": "+996700123456"
}
```
**Ответ 201:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { "id": 1, "role": "client", "first_name": "Иван", "email": "ivan@mail.com" }
}
```

---

### 1.2 Регистрация — врач (7 шагов, все данные в одном запросе)
```
POST /api/auth/register/doctor/
Content-Type: multipart/form-data
```
**Body (все поля из 7 шагов формы):**
```json
{
  "step1": {
    "full_name": "Иванов Иван Иванович",
    "gender": "male",
    "birth_date": "1980-05-20",
    "city": "Бишкек",
    "languages": ["ru", "ky"],
    "phone": "+996700123456",
    "email": "doctor@mail.com",
    "photo": "<file>"
  },
  "step2": {
    "country": "Кыргызстан",
    "city": "Бишкек",
    "address": "ул. Чуй 100, офис 5",
    "phone": "+996700123456",
    "email": "doctor@mail.com",
    "website": "https://doctor.kg",
    "location": { "lat": 42.8746, "lng": 74.5698 }
  },
  "step3": {
    "schedule": {
      "monday":    { "from": "09:00", "to": "18:00", "enabled": true },
      "tuesday":   { "from": "09:00", "to": "18:00", "enabled": true },
      "wednesday": { "from": "09:00", "to": "18:00", "enabled": true },
      "thursday":  { "from": "09:00", "to": "18:00", "enabled": true },
      "friday":    { "from": "09:00", "to": "18:00", "enabled": true },
      "saturday":  { "from": "10:00", "to": "15:00", "enabled": true },
      "sunday":    { "from": null,    "to": null,     "enabled": false }
    },
    "lunch_break": { "from": "13:00", "to": "14:00" },
    "emergency_24_7": false
  },
  "step4": {
    "legal_name": "ИП Иванов И.И.",
    "reg_number": "123456789",
    "license_number": "МЗ-0001",
    "license_date": "2020-01-15",
    "license_authority": "Министерство здравоохранения КР",
    "documents": ["<file1>", "<file2>"]
  },
  "step5": {
    "primary_specializations": ["Терапия", "Общая практика"],
    "narrow_specializations": ["Кардиология"],
    "additional_services": "Выезд на дом, онлайн-консультации"
  },
  "step6": {
    "equipment": ["МРТ", "УЗИ", "ЭКГ"],
    "patient_conditions": ["Парковка", "Пандус", "Детская комната"],
    "payment_methods": ["Наличные", "Карта", "ОМС"]
  },
  "step7": {
    "agree_terms": true,
    "agree_privacy": true,
    "agree_data_processing": true,
    "agree_publishing": true
  },
  "password": "секрет123"
}
```
**Ответ 201:** аналогично клиенту, `"role": "doctor"`

---

### 1.3 Регистрация — клиника
```
POST /api/auth/register/clinic/
Content-Type: multipart/form-data
```
**Body:**
```json
{
  "step1": {
    "name": "Клиника Здоровье",
    "logo": "<file>",
    "type": "Многопрофильная клиника",
    "description": "Описание клиники...",
    "photos": ["<file1>", "<file2>"]
  },
  "step2": {
    "country": "Кыргызстан",
    "city": "Бишкек",
    "address": "ул. Манаса 50",
    "phone": "+996312123456",
    "email": "clinic@mail.com",
    "website": "https://clinic.kg",
    "location": { "lat": 42.8746, "lng": 74.5698 }
  },
  "step3": {
    "schedule": {
      "monday":    { "from": "08:00", "to": "20:00", "enabled": true },
      "tuesday":   { "from": "08:00", "to": "20:00", "enabled": true },
      "wednesday": { "from": "08:00", "to": "20:00", "enabled": true },
      "thursday":  { "from": "08:00", "to": "20:00", "enabled": true },
      "friday":    { "from": "08:00", "to": "20:00", "enabled": true },
      "saturday":  { "from": "09:00", "to": "18:00", "enabled": true },
      "sunday":    { "from": null,    "to": null,     "enabled": false }
    },
    "lunch_break": { "from": "13:00", "to": "14:00" },
    "emergency_24_7": false
  },
  "step4": {
    "legal_name": "ООО «Здоровье»",
    "reg_number": "123456789012",
    "license_number": "МЗ-КЛ-0001",
    "license_date": "2019-03-01",
    "license_authority": "Министерство здравоохранения КР",
    "documents": ["<file1>"]
  },
  "step5": {
    "primary_specializations": ["Терапия", "Хирургия"],
    "narrow_specializations": ["Кардиология", "Неврология"],
    "additional_services": "Лаборатория, дневной стационар"
  },
  "step6": {
    "equipment": ["МРТ", "КТ", "УЗИ", "Рентген"],
    "patient_conditions": ["Парковка", "Кафетерий", "Пандус"],
    "payment_methods": ["Наличные", "Карта", "ОМС", "ДМС"]
  },
  "step7": {
    "agree_terms": true,
    "agree_privacy": true,
    "agree_data_processing": true,
    "agree_publishing": true
  },
  "password": "секрет123"
}
```

---

### 1.4 Вход
```
POST /api/auth/login/
```
```json
{
  "email": "ivan@mail.com",
  "password": "секрет123"
}
```
**Ответ:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": {
    "id": 1,
    "role": "client | doctor | clinic",
    "first_name": "Иван",
    "last_name": "Петров",
    "email": "ivan@mail.com",
    "phone": "+996700123456",
    "avatar": "https://..."
  }
}
```

### 1.5 Обновление токена
```
POST /api/auth/refresh/
Body: { "refresh_token": "eyJ..." }
Ответ: { "access_token": "eyJ..." }
```

### 1.6 Выход
```
POST /api/auth/logout/
Body: { "refresh_token": "eyJ..." }
```

### 1.7 Текущий пользователь
```
GET /api/auth/me/         — требует Authorization
```

---

## 2. Загрузка файлов

```
POST /api/upload/
Content-Type: multipart/form-data
Authorization: Bearer <token>

Body: { "file": <file> }

Ответ: { "url": "https://domain.com/media/uploads/abc.jpg" }
```

---

## 3. Каталог — Врачи

### 3.1 Список врачей
```
GET /api/doctors/
```
**Query-параметры:**
| Параметр | Тип | Описание |
|---|---|---|
| `search` | string | Поиск по имени и специализации |
| `city` | string | Фильтр по городу |
| `specialization` | string | Фильтр по специализации |
| `min_price` | int | Минимальная цена приёма |
| `max_price` | int | Максимальная цена приёма |
| `min_rating` | float | Минимальный рейтинг (0–5) |
| `is_online` | bool | Принимает онлайн |
| `payment_method` | string | Способ оплаты |
| `page` | int | Страница (default: 1) |
| `page_size` | int | Размер страницы (default: 20) |

**Ответ:**
```json
{
  "data": [
    {
      "id": 1,
      "full_name": "Иванов Иван Иванович",
      "specialty": "Терапевт",
      "photo": "https://...",
      "rating": 4.8,
      "reviews_count": 120,
      "experience_years": 15,
      "is_online_available": true,
      "city": "Бишкек",
      "workplaces": [
        {
          "clinic_id": 1,
          "clinic_name": "Клиника Здоровье",
          "price": 1500,
          "schedule": "Пн–Пт 09:00–18:00"
        }
      ]
    }
  ],
  "pagination": { "page": 1, "page_size": 20, "total": 85, "total_pages": 5 }
}
```

### 3.2 Детальная страница врача
```
GET /api/doctors/{id}/
```
**Ответ:**
```json
{
  "id": 1,
  "full_name": "Иванов Иван Иванович",
  "specialty": "Терапевт",
  "photo": "https://...",
  "rating": 4.8,
  "reviews_count": 120,
  "experience_years": 15,
  "is_online_available": true,
  "city": "Бишкек",
  "languages": ["ru", "ky"],
  "about": "Врач высшей категории...",
  "education": [
    { "institution": "КГМУ", "degree": "Высшее медицинское", "year": 2005 }
  ],
  "work_experience": [
    { "clinic": "ГКБ №1", "position": "Терапевт", "from": 2005, "to": 2015 }
  ],
  "skills": ["Диагностика", "Лечение хронических заболеваний"],
  "workplaces": [
    {
      "clinic_id": 1,
      "clinic_name": "Клиника Здоровье",
      "clinic_address": "ул. Чуй 100",
      "price": 1500,
      "schedule": {
        "monday":    { "from": "09:00", "to": "18:00", "enabled": true },
        "saturday":  { "from": "10:00", "to": "15:00", "enabled": true },
        "sunday":    { "enabled": false }
      },
      "lunch_break": { "from": "13:00", "to": "14:00" }
    }
  ],
  "equipment": ["МРТ", "УЗИ"],
  "patient_conditions": ["Парковка"],
  "payment_methods": ["Наличные", "Карта"],
  "phone": "+996700123456",
  "email": "doctor@mail.com",
  "location": { "lat": 42.87, "lng": 74.57 }
}
```

---

## 4. Каталог — Клиники

### 4.1 Список клиник
```
GET /api/clinics/
```
**Query-параметры:** `search`, `city`, `specialization`, `min_rating`, `payment_method`, `page`, `page_size`

**Ответ:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Клиника Здоровье",
      "logo": "https://...",
      "rating": 4.7,
      "reviews_count": 250,
      "address": "ул. Манаса 50",
      "city": "Бишкек",
      "specialties": ["Терапия", "Хирургия", "Кардиология"],
      "experience_years": 10,
      "doctors_count": 25
    }
  ],
  "pagination": { ... }
}
```

### 4.2 Детальная страница клиники
```
GET /api/clinics/{id}/
```
**Ответ:**
```json
{
  "id": 1,
  "name": "Клиника Здоровье",
  "logo": "https://...",
  "photos": ["https://...", "https://..."],
  "rating": 4.7,
  "reviews_count": 250,
  "address": "ул. Манаса 50",
  "city": "Бишкек",
  "phone": "+996312123456",
  "email": "clinic@mail.com",
  "website": "https://clinic.kg",
  "about": "Многопрофильная клиника...",
  "specialties": ["Терапия", "Хирургия"],
  "experience_years": 10,
  "doctors_count": 25,
  "schedule": {
    "monday": { "from": "08:00", "to": "20:00", "enabled": true },
    "sunday": { "enabled": false }
  },
  "equipment": ["МРТ", "КТ"],
  "patient_conditions": ["Парковка", "Кафетерий"],
  "payment_methods": ["Наличные", "Карта", "ОМС"],
  "location": { "lat": 42.87, "lng": 74.57 }
}
```

---

## 5. Каталог — Услуги

### 5.1 Список услуг
```
GET /api/services/
```
**Query:** `search`, `category`, `clinic_id`, `doctor_id`, `min_price`, `max_price`, `page`, `page_size`

**Ответ:**
```json
{
  "data": [
    {
      "id": 1,
      "name": "Консультация терапевта",
      "category": "Консультации",
      "price": 1500,
      "image": "https://...",
      "rating": 4.9,
      "reviews_count": 80,
      "clinic": { "id": 1, "name": "Клиника Здоровье" },
      "doctors": [
        { "id": 1, "full_name": "Иванов И.И.", "photo": "https://..." }
      ],
      "schedule": "Пн–Пт 09:00–18:00"
    }
  ],
  "pagination": { ... }
}
```

### 5.2 Детальная услуга
```
GET /api/services/{id}/
```
Тот же объект + `"description": "Подробное описание..."`, полное расписание.

---

## 6. Отзывы

### 6.1 Получить отзывы
```
GET /api/reviews/?target_type=doctor&target_id=1
GET /api/reviews/?target_type=clinic&target_id=1
GET /api/reviews/?target_type=service&target_id=1
```
**Ответ:**
```json
{
  "data": [
    {
      "id": 1,
      "author": { "id": 2, "name": "Анна П.", "avatar": "https://..." },
      "rating": 5,
      "text": "Отличный врач, внимательный...",
      "created_at": "2026-04-10T14:30:00Z",
      "appointment_id": 15
    }
  ],
  "average_rating": 4.8,
  "total": 120
}
```

### 6.2 Добавить отзыв
```
POST /api/reviews/
Authorization: Bearer <token>
```
```json
{
  "target_type": "doctor | clinic | service",
  "target_id": 1,
  "rating": 5,
  "text": "Отличный врач...",
  "appointment_id": 15
}
```

---

## 7. Запись на приём

### 7.1 Создать запись
```
POST /api/appointments/
Authorization: Bearer <token> (опционально — гость тоже может)
```
```json
{
  "doctor_id": 1,
  "clinic_id": 1,
  "service_id": 1,
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+996700123456",
  "email": "ivan@mail.com",
  "date": "2026-05-30",
  "time": "10:00",
  "format": "offline | online",
  "notes": "Первичный приём"
}
```
**Ответ 201:**
```json
{
  "id": 42,
  "status": "confirmed",
  "doctor": { "id": 1, "full_name": "Иванов И.И.", "photo": "https://..." },
  "clinic": { "id": 1, "name": "Клиника Здоровье", "address": "ул. Чуй 100" },
  "service": { "id": 1, "name": "Консультация терапевта", "price": 1500 },
  "date": "2026-05-30",
  "time": "10:00",
  "format": "offline",
  "status": "confirmed"
}
```

### 7.2 Отменить запись
```
PATCH /api/appointments/{id}/
Authorization: Bearer <token>
Body: { "status": "cancelled" }
```

---

## 8. Блог

### 8.1 Список статей
```
GET /api/blog/
```
**Query:** `category`, `search`, `page`, `page_size`

**Ответ:**
```json
{
  "data": [
    {
      "id": 1,
      "slug": "kak-vybrat-vracha",
      "title": "Как выбрать врача",
      "description": "Краткое описание...",
      "category": { "id": 1, "name": "Здоровье", "slug": "health" },
      "date": "2026-04-15",
      "image": "https://...",
      "is_featured": true
    }
  ]
}
```

### 8.2 Список категорий блога
```
GET /api/blog/categories/
Ответ: [{ "id": 1, "name": "Здоровье", "slug": "health" }]
```

### 8.3 Статья
```
GET /api/blog/{slug}/
Ответ: полный объект с "content": "HTML или markdown текст статьи"
```

---

## 9. Личный кабинет — Пациент (`/profile`)

> Авторизованный пользователь с ролью `client`.

### 9.1 Профиль
```
GET  /api/profile/
PUT  /api/profile/
Authorization: Bearer <token>
```
**Объект:**
```json
{
  "id": 1,
  "first_name": "Иван",
  "last_name": "Петров",
  "middle_name": "Сергеевич",
  "email": "ivan@mail.com",
  "phone": "+996700123456",
  "avatar": "https://...",
  "birth_date": "1990-01-15",
  "gender": "male | female",
  "city": "Бишкек",
  "blood_type": "A+",
  "allergies": ["пенициллин"],
  "chronic_diseases": ["гипертония"],
  "emergency_contact": {
    "name": "Мария Петрова",
    "phone": "+996700999888"
  }
}
```

### 9.2 История записей пациента
```
GET /api/profile/appointments/
Query: status=upcoming|completed|cancelled, page, page_size
```
**Ответ:**
```json
{
  "data": [
    {
      "id": 42,
      "doctor": {
        "id": 1,
        "full_name": "Иванов Иван Иванович",
        "specialty": "Терапевт",
        "photo": "https://...",
        "rating": 4.8
      },
      "clinic": { "id": 1, "name": "Клиника Здоровье", "address": "ул. Чуй 100" },
      "service": { "id": 1, "name": "Консультация терапевта", "price": 1500 },
      "date": "2026-05-30",
      "time": "10:00",
      "format": "offline",
      "status": "upcoming | completed | cancelled",
      "can_review": true
    }
  ]
}
```

### 9.3 Избранное (сохранённые врачи, клиники, услуги)
```
GET    /api/profile/favorites/
POST   /api/profile/favorites/        Body: { "type": "doctor|clinic|service", "target_id": 1 }
DELETE /api/profile/favorites/{id}/
```
**Ответ GET:**
```json
{
  "data": [
    {
      "id": 1,
      "type": "doctor",
      "target": {
        "id": 1,
        "name": "Иванов Иван Иванович",
        "subtitle": "Терапевт",
        "photo": "https://...",
        "rating": 4.8
      }
    }
  ]
}
```

### 9.4 Отзывы пациента
```
GET /api/profile/reviews/
```
Список отзывов, которые написал этот пользователь. Каждый объект — тот же формат что в разделе 6.

---

## 10. Личный кабинет — Врач (`/doctor-profile`)

> Авторизованный пользователь с ролью `doctor`.

### 10.1 Профиль врача
```
GET /api/doctor/profile/
PUT /api/doctor/profile/
Authorization: Bearer <token>
```
Полный объект из раздела 3.2 (детальная страница) + поля, не показываемые публично:
```json
{
  "...все публичные поля...",
  "legal": {
    "company_name": "ИП Иванов И.И.",
    "reg_number": "123456789",
    "license_number": "МЗ-0001",
    "license_date": "2020-01-15",
    "license_authority": "Министерство здравоохранения КР",
    "documents": ["https://..."]
  },
  "is_published": true,
  "profile_views": 1250,
  "appointments_total": 340
}
```

### 10.2 Расписание врача
```
GET /api/doctor/schedule/
PUT /api/doctor/schedule/
```
Объект `schedule` из шага 3 регистрации.

### 10.3 Записи к врачу
```
GET /api/doctor/appointments/
Query: status=upcoming|completed|cancelled|all, date_from, date_to, page, page_size
```
**Ответ:**
```json
{
  "data": [
    {
      "id": 42,
      "patient": {
        "id": 2,
        "full_name": "Анна Смирнова",
        "phone": "+996700111222",
        "avatar": "https://..."
      },
      "service": { "id": 1, "name": "Консультация", "price": 1500 },
      "date": "2026-05-30",
      "time": "10:00",
      "format": "offline",
      "status": "upcoming",
      "notes": "Первичный приём"
    }
  ]
}
```

### 10.4 Список пациентов врача
```
GET /api/doctor/patients/
Query: search, page, page_size
```
```json
{
  "data": [
    {
      "id": 2,
      "full_name": "Анна Смирнова",
      "phone": "+996700111222",
      "avatar": "https://...",
      "last_visit": "2026-04-20",
      "total_visits": 5
    }
  ]
}
```

### 10.5 Статистика врача
```
GET /api/doctor/stats/
```
```json
{
  "profile_views": 1250,
  "profile_views_this_month": 85,
  "appointments_total": 340,
  "appointments_this_month": 28,
  "average_rating": 4.8,
  "reviews_count": 120,
  "patients_total": 180,
  "completion_rate": 0.96
}
```

### 10.6 Отзывы о враче
```
GET /api/doctor/reviews/
```
То же что `GET /api/reviews/?target_type=doctor&target_id={my_id}`.

---

## 11. Личный кабинет — Клиника (`/clinic-profile`)

> Авторизованный пользователь с ролью `clinic`.

### 11.1 Профиль клиники
```
GET /api/clinic/profile/
PUT /api/clinic/profile/
Authorization: Bearer <token>
```
Полный объект из раздела 4.2 + приватные поля:
```json
{
  "...все публичные поля...",
  "legal": {
    "company_name": "ООО «Здоровье»",
    "reg_number": "123456789012",
    "license_number": "МЗ-КЛ-0001",
    "license_date": "2019-03-01",
    "license_authority": "Министерство здравоохранения КР",
    "documents": ["https://..."]
  },
  "is_published": true,
  "profile_views": 4200,
  "appointments_total": 1800
}
```

### 11.2 Врачи клиники
```
GET    /api/clinic/doctors/
POST   /api/clinic/doctors/invite/   Body: { "email": "doctor@mail.com" }  — приглашение врача
DELETE /api/clinic/doctors/{id}/                                           — открепить врача
```
**Ответ GET:**
```json
{
  "data": [
    {
      "id": 1,
      "full_name": "Иванов Иван Иванович",
      "specialty": "Терапевт",
      "photo": "https://...",
      "rating": 4.8,
      "appointments_total": 340,
      "is_active": true
    }
  ]
}
```

### 11.3 Услуги клиники
```
GET    /api/clinic/services/
POST   /api/clinic/services/          — добавить услугу
PUT    /api/clinic/services/{id}/     — обновить
DELETE /api/clinic/services/{id}/
```
**Body POST/PUT:**
```json
{
  "name": "Консультация кардиолога",
  "category": "Консультации",
  "description": "Описание...",
  "price": 2000,
  "duration_minutes": 30,
  "image": "https://...",
  "doctor_ids": [1, 3],
  "schedule": "Пн–Пт 09:00–18:00"
}
```

### 11.4 Записи в клинику
```
GET /api/clinic/appointments/
Query: status, doctor_id, date_from, date_to, page, page_size
```
Аналогично 10.3, но с полем `doctor` в каждом объекте.

### 11.5 Статистика клиники
```
GET /api/clinic/stats/
```
```json
{
  "profile_views": 4200,
  "profile_views_this_month": 320,
  "appointments_total": 1800,
  "appointments_this_month": 145,
  "average_rating": 4.7,
  "reviews_count": 250,
  "doctors_count": 25,
  "patients_total": 980,
  "revenue_this_month": 217500
}
```

---

## 12. Чат

> Документация чата уже выдана бэк-разработчиком отдельно.  
> Базовый URL: `http://155.212.216.197:8054`

**Уже реализовано на бэке:**
- `POST /api/login/` — вход в чат по username (сессионная кука)
- `GET /api/messages/{room_name}/` — история сообщений
- `ws://.../ws/chat/{room_name}/` — WebSocket

**Нужно дополнительно:**
- `GET /api/chat/rooms/` — список активных чат-комнат пользователя (чтобы показывать реальный список чатов вместо мок-данных)
  ```json
  {
    "data": [
      {
        "room_name": "doctor_1_patient_2",
        "interlocutor": {
          "username": "dr_ivanov",
          "display_name": "Иванов Иван Иванович",
          "role": "doctor",
          "avatar": "https://..."
        },
        "last_message": {
          "content": "Добрый день!",
          "timestamp": "2026-05-19T14:55:00Z",
          "is_mine": false
        },
        "unread_count": 2
      }
    ]
  }
  ```
- `POST /api/chat/rooms/` — создать/открыть чат с пользователем
  ```json
  { "target_user_id": 1 }
  Ответ: { "room_name": "doctor_1_patient_2" }
  ```

---

## 13. Справочники (для дропдаунов)

```
GET /api/references/cities/          — список городов
GET /api/references/specializations/ — список специализаций
GET /api/references/clinic-types/    — типы клиник
GET /api/references/languages/       — языки (для врача)
GET /api/references/equipment/       — оборудование (чекбоксы)
GET /api/references/conditions/      — условия для пациентов
GET /api/references/payment-methods/ — способы оплаты
```
Формат каждого:
```json
[{ "id": 1, "name": "Бишкек" }, ...]
```

---

## 14. Уведомления

```
GET  /api/notifications/             — список уведомлений
PATCH /api/notifications/{id}/read/  — отметить прочитанным
PATCH /api/notifications/read-all/   — отметить все прочитанными
```
```json
{
  "data": [
    {
      "id": 1,
      "type": "appointment_reminder | new_review | new_message | system",
      "title": "Напоминание о записи",
      "body": "Завтра в 10:00 у вас приём у Иванова И.И.",
      "is_read": false,
      "created_at": "2026-05-29T12:00:00Z",
      "payload": { "appointment_id": 42 }
    }
  ],
  "unread_count": 3
}
```

---

## 15. Таблица приоритетов реализации

| Приоритет | Эндпоинты | Статус |
|---|---|---|
| 🔴 Высший | Auth (login, register, me, refresh) | Нужно |
| 🔴 Высший | Doctors, Clinics, Services (list + detail) | Нужно |
| 🔴 Высший | Upload | Нужно |
| 🟠 Высокий | Appointments (create, cancel) | Нужно |
| 🟠 Высокий | Profile (client) — GET/PUT + история записей | Нужно |
| 🟡 Средний | Doctor cabinet (profile, appointments, schedule) | Нужно |
| 🟡 Средний | Clinic cabinet (profile, doctors, services) | Нужно |
| 🟡 Средний | Reviews (list + create) | Нужно |
| 🟢 Низкий | Blog | Нужно |
| 🟢 Низкий | Favorites | Нужно |
| 🟢 Низкий | Notifications | Нужно |
| 🟢 Низкий | Chat rooms list / create | Нужно |
| 🟢 Низкий | References (справочники) | Нужно |
| ✅ Готово | Chat WebSocket + history | Готово |
