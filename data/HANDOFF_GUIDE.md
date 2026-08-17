# DAL Handoff Guide

Use this when you send the project to another person.

## What to send

Send these three things together:

- The zipped `dal` folder
- The `.env` file
- `dal_metadata.backup`
- `dal_operational.backup`

If you send only the zip, they will get the code and seed scripts, but **not** your live PostgreSQL data.

## What the next person should do

1. Unzip the `dal` folder.
2. Put `.env`, `dal_metadata.backup`, and `dal_operational.backup` in the same folder as the repo.
3. Start the stack:

   ```bash
   docker compose up -d --build
   ```

4. Run migrations:

   ```bash
   docker compose exec app alembic upgrade head
   ```

5. Restore the metadata database:

   ```bash
   docker cp ./dal_metadata.backup dal-metadata-db-1:/tmp/dal_metadata.backup
   docker compose exec metadata-db pg_restore -U dal_meta -d dal_metadata --clean --if-exists /tmp/dal_metadata.backup
   ```

6. Restore the operational database:

   ```bash
   docker cp ./dal_operational.backup dal-operational-db-1:/tmp/dal_operational.backup
   docker compose exec operational-db pg_restore -U dal_ops -d dal_operational --clean --if-exists /tmp/dal_operational.backup
   ```

7. Open the API docs:
   - `http://localhost:8000/docs`

## Can local store the full data?

Yes, if the machine has enough disk space.

Rule of thumb:

- If the backup is about 5 GB, keep at least 10 GB to 15 GB free locally before restoring.
- The restored PostgreSQL data can use a bit more space than the backup file itself.
- If the data is split across the two databases, check both backup sizes together.

To check backup file size on Windows PowerShell:

```powershell
Get-Item .\dal_metadata.backup, .\dal_operational.backup | Select-Object Name, Length
```

If you want the exact source size before backup, run this on the database server:

```sql
SELECT pg_size_pretty(pg_database_size('dal_metadata'));
SELECT pg_size_pretty(pg_database_size('dal_operational'));
```

## If they do not have the backup files

They can still run the app with sample data only:

```bash
docker compose exec app python -m scripts.seed_metadata
docker compose exec app python -m scripts.seed_operational
```

## Short version

To recreate your current setup exactly, send:

- repo zip
- `.env`
- `dal_metadata.backup`
- `dal_operational.backup`

Then the next person can unzip the repo, start Docker, restore both backups, and get the same data you have now.
