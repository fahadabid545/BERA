# If a key or password leaks

Treat any secret that was pasted in chat or email, committed, shown in a screenshot, printed
in a log or sent to the wrong person as leaked. Do not wait to be sure.

## 1. Replace

1. Create a new value (a long random one; never reuse an old value or one from another
   environment). Staging and production always have different values.
2. Put it in the environment's secret store or `.env` on the server, never in code or chat.
3. Restart the app. It refuses to start if the value is missing or still a placeholder.

## 2. Revoke the old one

Replacing is not enough: the old value must stop working.

| Secret | What to do |
| --- | --- |
| `JWT_COMPANY_SECRET`, `JWT_ADMIN_SECRET` | Replace and restart. Every token signed with the old key stops working, so everyone is signed in again. |
| `DJANGO_SECRET_KEY` | Replace and restart. |
| Database passwords (`DATABASE_URL`, `MIGRATION_DATABASE_URL`, `BACKUP_DATABASE_URL`) | Set a new password in the address of the leaked account, run `python manage.py provision_database_roles` (it sets the password and the rights again), restart. Only the leaked environment's account changes. A leaked migrator password is the most serious: it can change the structure. |
| `FIELD_ENCRYPTION_KEY` | Whoever holds the key and a copy of the database can read personal data. Treat as a data breach. Changing the key makes every stored value unreadable until the values are re-encrypted, which is not built yet: ask before replacing it. |
| `FIELD_HASH_KEY` | Whoever holds the key can test guesses of known emails and phone numbers against the stored hashes. Replacing it means rebuilding every hash column (the hashes are filled from the encrypted values). |
| AI provider key | Delete the key in the provider's dashboard, create a new one. |
| Payment keys and webhook secret | Roll the keys in the payment dashboard (the old key stops working), update the webhook secret. |
| Email provider key | Delete it in the provider's dashboard, create a new one. |
| Storage keys | Delete the access key in the storage dashboard, create a new one. |

## 3. Check what happened

- Look at the provider's usage and sign-in history for the time between the leak and the
  revoke (unknown IP addresses, unusual volume, new resources).
- Search the application log for the same period: failed and unusual sign-ins, token reuse,
  refused requests, unusually large downloads. Logs never contain secrets, so search by time.
- If candidate data may have been reached, tell the owner of the platform at once; this
  can be a personal data breach with a legal deadline.

## 4. Clean up and record

- Remove the secret from the file, message or page where it appeared. Rewriting git history
  does not make a leaked value safe again; the replacement above does.
- Write down what leaked, when, how it was found, what was replaced and what the checks showed.
- Find out how it happened and fix that (the automatic secret scan should have stopped a commit).

Never log, paste or screenshot the old or the new value while doing this.
