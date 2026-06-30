# Модель данных

Ниже рабочая схема сущностей для PostgreSQL. Это не финальная миграция, а зафиксированная структура из переписки.

## users

- `id`
- `telegram_id`
- `full_name`
- `phone`
- `role`
- `default_shift_number`
- `status`: pending / active / blocked
- `created_at`

## machines

- `id`
- `name`
- `is_active`

Начальные значения:

- `Г-1`
- `Г-2`
- `Г-3`
- `С-3`
- `Г-4`
- `С-1`
- `Г-6`
- `С-4`
- `С-5`
- `С-6`

## shifts

- `id`
- `work_date`
- `shift_type`: day / night
- `shift_number`
- `started_at`
- `ended_at`
- `status`: open / closed

## shift_members

- `id`
- `shift_id`
- `user_id`
- `role_in_shift`
- `machine_id`, nullable для наладчиков и мастеров
- `is_overtime`

## rails

- `id`
- `name`
- `short_name`
- `rail_type`
- `article_code`
- `color`
- `metal`
- `piece_length_m`
- `pieces_per_package`
- `is_active`

Пример:

- `name`: `Grigliato GL15 мама 75x75 h37 b15`
- `short_name`: `GL15 мама 75x75 h37 b15`
- `rail_type`: `мама`
- `article_code`: `A903.0ц01`
- `color`: `белый оц`
- `piece_length_m`: `0.6`
- `pieces_per_package`: `192`

## machine_rail_rates

- `id`
- `machine_id`
- `rail_id`
- `operator_rate_per_1000`
- `setup_rate_per_1000`
- `valid_from`
- `valid_to`

## production_entries

- `id`
- `shift_id`
- `machine_id`
- `rail_id`
- `operator_user_id`
- `created_by_user_id`
- `packages`
- `pieces_per_package`
- `pieces_from_packages`
- `pieces_from_task`
- `accepted_pieces`
- `accepted_pieces_source`: packages / task / manual
- `piece_length_m`
- `linear_meters`
- `operator_rate_per_1000`
- `setup_rate_per_1000`
- `operator_pay`
- `setup_total_pay`
- `created_at`

## photo_reports

- `id`
- `shift_id`
- `machine_id`, nullable
- `uploaded_by_user_id`
- `file_id`
- `file_path`
- `ocr_status`: not_started / recognized / confirmed / failed
- `recognized_payload`
- `confirmed_entry_id`
- `created_at`

## shift_reports

- `id`
- `shift_id`
- `payload`
- `created_at`
- `sent_at`
