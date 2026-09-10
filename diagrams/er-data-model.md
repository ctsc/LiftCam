# ER — data model

Canonical schema for V1. Must match `backend/liftcam/core/models.py` column for column.

```mermaid
erDiagram
  users ||--o{ uploads : owns
  users ||--o{ refresh_tokens : has
  uploads ||--o{ segments : has
  segments ||--o{ reps : has

  users {
    uuid id PK
    string email UK
    string username UK
    string password_hash "nullable"
    string auth_provider "email|google|apple"
    string apple_user_id UK "nullable"
    date dob
    float height
    string height_unit "in|cm"
    float weight
    string weight_unit "lb|kg"
    string sex "male|female"
    float squat_max
    float bench_max
    float deadlift_max
    string favorite_lift "nullable"
    string tier "default free"
    string expo_push_token "nullable, one per user"
    timestamptz created_at
  }

  refresh_tokens {
    uuid id PK
    uuid user_id FK
    string token_hash UK
    timestamptz created_at
    timestamptz expires_at
  }

  uploads {
    uuid id PK
    uuid user_id FK
    string status "uploading|queued|processing|ready|failed|no_lift"
    string r2_original_key "nullable"
    string r2_overlay_key "nullable"
    string multipart_upload_id "nullable"
    float weight
    string weight_unit "lb|kg"
    int user_reps
    string failed_stage "nullable"
    string failure_code "nullable"
    string failure_message "nullable"
    timestamptz created_at
    timestamptz claimed_at "nullable"
    timestamptz finished_at "nullable"
    float duration_s "nullable"
    float fps "nullable"
    int width "nullable"
    int height "nullable"
    int rotation_deg "nullable"
  }

  segments {
    uuid id PK
    uuid upload_id FK
    int ord
    float start_s
    float end_s
    float camera_angle_deg "nullable"
    float angle_confidence "nullable"
    float px_per_m "nullable"
    float calibration_confidence "nullable"
  }

  reps {
    uuid id PK
    uuid segment_id FK
    int ord
    float start_s
    float end_s
    float velocity "nullable"
    jsonb faults "nullable"
    float confidence "nullable"
    float force_estimate "nullable"
    float work_estimate "nullable"
    float lockout_ratio "nullable"
    jsonb series "nullable"
  }
```

Indexes:

- `uploads (user_id, created_at DESC)` — History
- partial `uploads (status) WHERE status = 'queued'` — worker claim
- unique `(upload_id, ord)` on segments; unique `(segment_id, ord)` on reps
