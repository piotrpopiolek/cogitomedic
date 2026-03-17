# Runbook: Aktualizacja aplikacji na mydevil

## Cel

Bezpieczne zaktualizowanie wersji aplikacji Cogitomedica na hostingu mydevil.net **bez użycia gita na serwerze**. Kod jest wgrywany z lokalnego katalogu przez **rsync**. Aplikacja już stoi w katalogu `public_python`; nie wykonujemy klonowania z GitHub na serwerze.

## Różnice: lokal (Docker) vs mydevil

| Aspekt | Lokal (Docker) | Mydevil |
|--------|----------------|---------|
| Zależności | `requirements.txt` | **Zawsze** `requirements_mydevil.txt` |
| Static/Media | `staticfiles` | `MYDEVIL_DEPLOY=1` → `public/static`, `public/media` |
| Pliki wrażliwe | `.env` w projekcie / compose | `.env` **tylko na serwerze**, nie nadpisujemy go rsync |

---

## Wymagania wstępne

- Dostęp SSH do konta na mydevil (użytkownik np. `pepepython`).
- Na serwerze: aplikacja już wdrożona w `/usr/home/pepepython/domains/pepepython.usermd.net/public_python/`, skonfigurowany virtualenv (np. `~/.virtualenvs/cogito`), `.env`, `passenger_wsgi.py`, katalogi `public/static`, `public/media`.
- Lokalnie: repozytorium zaktualizowane (commit + push do GitHub dla backupu).

---

## Krok 1: Przygotowanie lokalne (przed rsync)

Wykonaj **na swoim komputerze** w katalogu projektu:

1. Przetestuj zmiany (uruchom aplikację lokalnie, np. Docker).
2. Uruchom migracje – upewnij się, że nie ma błędów:
   ```bash
   python manage.py migrate
   ```
3. Sprawdź, czy nie dodałeś zależności tylko do `requirements.txt`. Jeśli tak:
   - dopisz je do `requirements_mydevil.txt` (jeśli są dostępne na mydevil), albo
   - upewnij się, że kod obsługuje ich brak (np. opcjonalny import).
4. Zrób commit i push do GitHub (żeby mieć backup i wersję do ewentualnego rollbacku):
   ```bash
   git add -A
   git commit -m "Opis zmian"
   git push origin main
   ```

---

## Krok 2: Rsync – wgranie kodu na mydevil

Wykonaj **na swoim komputerze**. Zastąp `LOGIN` i `DOMENA` swoimi (np. `pepepython`, `pepepython.usermd.net`). Jeśli łączysz się po kluczu SSH, możesz pominąć hasło.

```bash
cd /ścieżka/do/cogitomedica

# Upewnij się, że masz aktualny main (jeśli pracowałeś na branchu)
git checkout main
git pull origin main

rsync -avz \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'media/' \
  --exclude 'staticfiles/' \
  --exclude 'public/' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '*.sqlite3' \
  --exclude 'node_modules/' \
  ./ \
  LOGIN@DOMENA:/usr/home/LOGIN/domains/DOMENA/public_python/
```

**Przykład** (dla pepepython.usermd.net):

```bash
cd C:\Users\piotr\Programming\cogitomedica

rsync -avz \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'media/' \
  --exclude 'staticfiles/' \
  --exclude 'public/' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '*.sqlite3' \
  --exclude 'node_modules/' \
  ./ \
  pepepython@pepepython.usermd.net:/usr/home/pepepython/domains/pepepython.usermd.net/public_python/
```

**Znaczenie wykluczeń:**

- `.env` – nie nadpisuj konfiguracji produkcyjnej na serwerze.
- `public/` – na mydevil zawiera zbierane pliki (`public/static`, `public/media`); generuje je `collectstatic` i uploady użytkowników.
- `media/`, `staticfiles/` – katalogi lokalne (Docker/dev); na mydevil odpowiednikiem jest `public/`.
- `.git`, `__pycache__`, `*.pyc`, `.venv`, `venv`, `node_modules/` – nie są potrzebne na serwerze i nie powinny nadpisywać niczego.

**Uwaga:** Na Windows możesz użyć rsync przez WSL, Git Bash (jeśli jest rsync) lub klienta typu WinSCP/Cyberduck z trybem „synchronizacji” z odpowiednimi wykluczeniami. Wtedy kroki 3–6 wykonasz i tak po SSH.

---

## Krok 3: SSH na mydevil i wejście w katalog

```bash
ssh LOGIN@DOMENA
cd /usr/home/LOGIN/domains/DOMENA/public_python
```

Przykład:

```bash
ssh pepepython@pepepython.usermd.net
cd /usr/home/pepepython/domains/pepepython.usermd.net/public_python
```

---

## Krok 4: Virtualenv i zależności Pythona

**Zawsze** używaj `requirements_mydevil.txt` (nie `requirements.txt`):

```bash
source /usr/home/LOGIN/.virtualenvs/cogito/bin/activate
pip install -r requirements_mydevil.txt
```

Przykład:

```bash
source /usr/home/pepepython/.virtualenvs/cogito/bin/activate
pip install -r requirements_mydevil.txt
```

Jeśli pojawią się błędy instalacji (np. brak pakietu na FreeBSD), usuń lub zamień ten pakiet w `requirements_mydevil.txt` i powtórz kroki 1–4 (kod musi obsługiwać brak takiej zależności).

---

## Krok 5: Migracje bazy danych

Opcjonalnie przed migracją: zrób backup bazy (np. przez panel mydevil / `devil pgsql` lub dostęp do PostgreSQL).

```bash
python manage.py migrate --noinput
```

W razie błędu: nie restartuj aplikacji; sprawdź komunikat (np. konflikt migracji, brakująca kolumna). Ewentualnie przywróć backup bazy i wgraj poprzednią wersję kodu (rollback – patrz sekcja na końcu).

---

## Krok 6: Pliki statyczne (collectstatic)

Na mydevil w `.env` musi być ustawione `MYDEVIL_DEPLOY=1`, żeby Django zbierał pliki do `public/static`.

```bash
python manage.py collectstatic --noinput
```

Sprawdź, czy katalog `public/static` został uzupełniony (serwer WWW serwuje stamtąd pliki pod `/static/`).

---

## Krok 7: Restart aplikacji

- **Przez panel DevilWEB:** logowanie do panelu mydevil → WWW → wybrana domena → Restart.
- **Przez SSH (jeśli dostępne):**
  ```bash
  devil www restart DOMENA
  ```
  (np. `devil www restart pepepython.usermd.net` – nazwa zgodna z konfiguracją konta).

---

## Krok 8: Weryfikacja

1. Otwórz w przeglądarce stronę logowania, np. `https://pepepython.usermd.net/doctor/login/`.
2. Sprawdź, czy CSS/JS się ładują (brak „gołego” HTML).
3. Zaloguj się i przetestuj kluczowe ścieżki (np. panel recepcji, admin).
4. Opcjonalnie: endpoint zdrowia, np. `/api/v1/observability/health`, jeśli jest w projekcie.

---

## Rollback (gdy coś pójdzie nie tak)

1. **Kod:** U siebie cofnij zmiany (np. `git checkout <poprzedni_commit>` lub `git revert`), potem powtórz **Krok 2** (rsync) – wgrajesz poprzednią wersję plików na mydevil.
2. **Na serwerze:** ponownie wykonaj kroki 3–7 (pip, migrate, collectstatic, restart). Jeśli migracje już się wykonały i nowa wersja kodu wymaga nowszych migracji, może być konieczne przywrócenie bazy z backupu przed ponownym rsync i `migrate`.
3. **Baza:** Jeśli zrobiłeś backup bazy przed Krokem 5, przywróć go według procedury mydevil (np. `psql` lub panel), a następnie wgraj poprzednią wersję kodu (rsync) i zrestartuj aplikację.

---

## Szybka checklista (do odhaczenia)

- [ ] Lokalnie: test, `migrate`, commit, push do GitHub.
- [ ] Sprawdzenie `requirements_mydevil.txt` przy nowych zależnościach.
- [ ] Rsync z wykluczeniami (bez `.env`, `public/`, `.git`, cache).
- [ ] SSH: `cd public_python`, `source .../cogito/bin/activate`.
- [ ] `pip install -r requirements_mydevil.txt`.
- [ ] (Opcjonalnie) Backup bazy.
- [ ] `python manage.py migrate --noinput`.
- [ ] `python manage.py collectstatic --noinput`.
- [ ] Restart aplikacji (DevilWEB lub `devil www restart`).
- [ ] Test w przeglądarce.

---

## Zobacz też

- [Plan wdrożenia na mydevil](.cursor/plans/wdrożenie_na_mydevil.net.plan.md) – konfiguracja początkowa, Passenger, .env, static/media.
- README projektu – ogólne informacje o aplikacji.
