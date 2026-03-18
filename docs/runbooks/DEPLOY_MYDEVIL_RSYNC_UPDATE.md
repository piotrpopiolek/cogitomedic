# Runbook: Aktualizacja mydevil przez rsync

## Założenia
- Aplikacja już działa na mydevil.
- `manage.py` znajduje się na serwerze w:
  - `/usr/home/pepepython/domains/pepepython.usermd.net/public_python`
- W `.env` na mydevil masz `MYDEVIL_DEPLOY=1`, więc `collectstatic` trafia do `/usr/home/.../public/static`.
- Nie nadpisujemy na serwerze:
  - `.env` (sekrety)
  - `public/` (static + media serwowane przez hosta)
  - `staticfiles/` (jeśli używasz innej logiki)

## Zmienne do komend (Twoje konkretne wartości)
- Lokalny katalog projektu (z `manage.py`):
  - `C:\Users\piotr\Programming\cogitomedica`
- SSH:
  - `pepepython@s62.mydevil.net`
- Serwer: katalog docelowy:
  - `/usr/home/pepepython/domains/pepepython.usermd.net/public_python`

## Krok 0: Sprawdzenie lokalnie (żeby ograniczyć ryzyko)
1. Upewnij się, że masz w repo odpowiednie zmiany:
   - `git status`
2. Uruchom migracje lokalnie:
   - `python manage.py migrate`

## Krok 1: Backup aktualnego kodu na mydevil (rollback)
Na serwerze (SSH) wykonaj:
```bash
cd /usr/home/pepepython/domains/pepepython.usermd.net/public_python

mkdir -p /usr/home/pepepython/domains/pepepython.usermd.net/public_python_backups
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p /usr/home/pepepython/domains/pepepython.usermd.net/public_python_backups/$TS

rsync -a --delete \
  --exclude '.env' \
  --exclude '.git' \
  --exclude 'public/' \
  --exclude 'media/' \
  --exclude 'staticfiles/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  ./ /usr/home/pepepython/domains/pepepython.usermd.net/public_python_backups/$TS/
```

## Krok 2: Rsync nowej wersji kodu (bez `.env` i bez `public/`)
Uruchom na swoim komputerze:
```bash
rsync -avz --progress \
  --exclude '.git' \
  --exclude '.cursor/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'public/' \
  --exclude 'media/' \
  --exclude 'staticfiles/' \
  "C:/Users/piotr/Programming/cogitomedica/" ./ \
  pepepython@s62.mydevil.net:/usr/home/pepepython/domains/pepepython.usermd.net/public_python/
```

## Krok 3: Instalacja zależności na mydevil
```bash
source /usr/home/pepepython/.virtualenvs/cogito/bin/activate
pip install -r /usr/home/pepepython/domains/pepepython.usermd.net/public_python/requirements_mydevil.txt
```

## Krok 4: Migracje
```bash
cd /usr/home/pepepython/domains/pepepython.usermd.net/public_python
python manage.py migrate --noinput
```

## Krok 5: collectstatic
```bash
python manage.py collectstatic --noinput
```

## Krok 6: Restart aplikacji (Passenger)
- W DevilWEB: WWW → wybierz domenę → `Restart` (dla tej domeny).
- Jeśli masz CLI restart (zależy od panelu), użyj polecenia podanego przez mydevil.

## Krok 7: Weryfikacja po wdrożeniu
Sprawdź:
- `/doctor/login/`
- `/admin/`
- ładowanie CSS/JS (brak błędów w konsoli).

## Rollback (gdy coś nie działa)
1. Cofnij kod do backupu (z kroku 1), omijając `.env` i `public/`:
   ```bash
   cd /usr/home/pepepython/domains/pepepython.usermd.net/public_python
   rsync -a --delete \
     --exclude '.env' \
     --exclude 'public/' \
     --exclude 'media/' \
     --exclude 'staticfiles/' \
     /usr/home/pepepython/domains/pepepython.usermd.net/public_python_backups/$TS/ ./
   ```
2. Ponownie:
   - `pip install -r requirements_mydevil.txt`
   - `python manage.py migrate --noinput` (jeśli używałeś migracji; przy rollbacku może wymagać cofnięcia do poprzedniego stanu migracji)
   - `python manage.py collectstatic --noinput`
3. Restart Passenger.

