# Database protection

## The three accounts

| Account | Setting | Can | Cannot |
| --- | --- | --- | --- |
| app | `DATABASE_URL` | read and write rows | create, change or drop tables; create accounts or databases |
| migrator | `MIGRATION_DATABASE_URL` | own the tables and change the structure | used only by `migrate` while deploying |
| backup | `BACKUP_DATABASE_URL` | read everything | write anything |

The running website and the workers hold only the app password. The step that runs `migrate`
holds only the migrator password. `manage.py` switches by itself for `migrate`,
`reset_dev_db` and `provision_database_roles`. A bug in the app (or a stolen app password)
can change rows but not the database structure, and cannot reach other accounts.

Nobody else may connect or create anything: the rights of every other role are removed.
Tables the migrator creates later give the app and backup accounts their rights
automatically.

## Setting up staging or production

1. Install PostgreSQL on the server and make it reachable from this computer or the private
   network only. It is never open to the internet (the firewall itself is a launch ticket).
2. Switch encryption on: `ssl = on` with a certificate in `postgresql.conf`, and only
   `hostssl` lines in `pg_hba.conf` (no plain `host` lines), so a plain connection is refused.
3. Create the empty database. Create an administrator account for this step only. It is kept
   out of the app's environment.
4. Put three different, real passwords in the three addresses, each ending with
   `?sslmode=verify-full` (put the server's certificate authority file where PostgreSQL
   clients look, or use `sslrootcert=`).
5. With `ADMIN_DATABASE_URL` set for this one command, run
   `python manage.py provision_database_roles`. It creates the accounts and sets their
   rights, and can be repeated. Passwords are hashed before they are sent to the server, so
   the server log never holds them.
6. Deploy in this order: provision, `migrate`, start the app, then run
   `python manage.py check_database_protection`. It fails if the app's account has too many
   rights or the connection is not encrypted.

Locally, `python scripts/dev.py` does steps 3 to 5 with fake passwords.

## Storing personal data

```python
from core.field_protection import normalize_email
from core.protected_fields import EncryptedTextField, LookupHashField

class Candidate(CompanyOwnedModel):
    email = EncryptedTextField(purpose="candidate.email")
    email_lookup = LookupHashField(of="email", purpose="candidate.email", normalize=normalize_email)
```

- `email` is encrypted (AES-256-GCM) before it is saved and decrypted when it is read. The
  database only ever holds unreadable text, different every time.
- `email_lookup` is filled in on every save with a keyed hash of the normalised value, so
  `Candidate.objects.filter(email_lookup="Jo@Example.com")` finds `jo@example.com` for
  duplicate detection without storing the address readably. It supports only exact matches.
- Searching the encrypted column itself raises an error on purpose.
- `purpose` is sealed into each value so it cannot be copied into another column. Do not
  change a purpose, a normaliser or a key once data exists.
- `bulk_update` and `QuerySet.update()` do not fill the hash column. Use `save()`.

## Not built yet

- Candidate tables and the fields on them (BERA-076 and the candidate tickets).
- Hashing of user passwords (the login tickets). Refresh tokens are already stored hashed.
- Changing the field keys: values carry a version byte for it, but re-encrypting all rows is
  not built.
- Backup jobs, backup encryption and restore tests: the account exists, nothing uses it yet.
- The server firewall and keeping the database off the internet (launch tickets).
