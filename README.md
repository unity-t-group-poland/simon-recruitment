# Zadanie rekrutacyjne — systemy SIMON

Repozytorium startowe do [zadania dotyczącego protokołu SP/1](TASK.md): odbiór zdarzeń z centrali, trwały zapis, potwierdzenia i REST API odczytu. Specyfikacja w TASK.md określa jeden wspólny zakres oraz wymagane testy. Ścieżkę API, metodę i statusy projektujesz samodzielnie.

Symulator SP/1 wymaga Python 3.9+ i działa poleceniem `python tools/panel_simulator.py --scenario normal`. Szczegóły oraz scenariusze objęte zadaniem są w [TASK.md](TASK.md#symulator-i-testy).

Po zaimplementowaniu klienta uruchamiaj symulator w osobnym terminalu przed aplikacją. [Tabela scenariuszy](TASK.md#uruchamianie-scenariuszy) opisuje wymagany stan początkowy, ACK i wynik w bazie. Wyniki `PASS`/`FAIL` symulatora dotyczą komunikacji TCP, nie zapisu ani API.

Zadanie wykonujesz w domu. Pytania o rozwiązanie, odpowiedzi i poprawki odbywają się wyłącznie asynchronicznie w PR na GitHubie; nie będzie prezentacji, spotkania z omówieniem zadania ani live codingu. **AI jest niedozwolone**, również podczas pisania dokumentacji, odpowiedzi i poprawek w PR. Dozwolone są dokumentacja, wyszukiwanie źródeł i zwykłe funkcje IDE. Szczegółowe zasady: [TASK.md](TASK.md#zakres-i-organizacja).

Szablon zawiera uruchamialną aplikację, konfigurację PostgreSQL/jOOQ, Maven Wrapper, test połączenia i GitHub Actions. Klient TCP, parser, model, schemat danych, API odczytu i testy reguł zadania są do przygotowania. Poprawny wynik testu startowego nie oznacza rozwiązania zadania.

## Fork i pull request

Pull request na GitHubie jest wymaganym sposobem przekazania rozwiązania i miejscem informacji zwrotnej. Komentarze do kodu, odpowiedzi kandydata, poprawki i podsumowanie review pozostają w tym samym PR. Archiwum nie zastępuje tego procesu.

1. Otwórz **prywatne repozytorium startowe wskazane przez rekrutera** i zaakceptuj zaproszenie, jeśli jest wymagane. Centralny szablon organizacji to [unity-t-group-poland/simon-recruitment](https://github.com/unity-t-group-poland/simon-recruitment); rekruter może przekazać osobną kopię tylko dla Twojej rekrutacji.
2. W GitHub wybierz **Fork**, jako właściciela wskaż swoje konto osobiste. Fork prywatnego repozytorium pozostaje prywatny. Jeśli przycisk jest niedostępny, zgłoś to rekruterowi — wymaga to sprawdzenia polityki forkowania.
3. Sklonuj swój fork i utwórz `solution` z istniejącego `main`:

   ```bash
   git switch main
   git switch -c solution
   ```

4. Pracuj na `solution`. `main` pozostaw jako punkt startowy do porównania.
5. Wypchnij `solution` do swojego forka. Utwórz **pull request do repozytorium startowego przypisanego Tobie**: `base repository` = przypisane repozytorium rekrutera, `base` = `main`, `head repository` = Twój fork, `compare` = `solution`. Sprawdź docelowe repozytorium przed wysłaniem; nie kieruj PR do centralnego szablonu, jeżeli dostałeś osobne repozytorium.
6. Uzupełnij formularz PR i sekcję "Notatki do rozwiązania" poniżej. Review odbędzie się w GitHub, a kolejne poprawki dodawaj na tej samej gałęzi. PR pozostaw otwarty do przeglądu.

Nie publikuj rozwiązania jako publiczne repozytorium. Nie trzeba nadawać dostępu do innych prywatnych projektów ani zapraszać pozostałych kandydatów.

## Wymagania

- **JDK 8**, wskazany przez `JAVA_HOME`. Maven Enforcer sprawdza rzeczywisty JDK, nie tylko poziom składni. `./mvnw -v` pokazuje używaną Javę.
- **Docker z Compose v2** albo własny PostgreSQL 16. Docker jest wygodnym sposobem uruchomienia baz, nie wymaganiem implementacji aplikacji.
- Internet przy pierwszym pobraniu Maven i zależności. Projekt korzysta z publicznego Maven Central.
- **Python 3.9+** do uruchomienia dostarczonego symulatora centrali.

Wersje startowe: Spring Boot 2.7.18, jOOQ 3.12.3, PostgreSQL JDBC 42.7.4, Maven 3.9.9, Maven Wrapper 3.3.2. Są dobrane do ćwiczenia zgodności z Java 8. `pom.xml` jest źródłem wersji bibliotek.

## Szybki start

Uruchom bazę aplikacji:

```bash
docker compose up -d --wait postgres
```

Linux/macOS:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Stan infrastruktury: [http://127.0.0.1:8080/actuator/health](http://127.0.0.1:8080/actuator/health). Początkowo powinien zwrócić `{"status":"UP"}`. API zadania nie jest jeszcze zaimplementowane. W [requests/events.http](requests/events.http) znajdziesz kontrolę infrastruktury; dodaj własne przykłady dla zaprojektowanego API odczytu, w tym brak rekordu i błędne wejście.

Lokalne dane połączenia:

| Baza | Port hosta | Nazwa | Użytkownik | Hasło tylko do lokalnego ćwiczenia |
| --- | ---: | --- | --- | --- |
| Aplikacja | 54329 | simon_recruitment | recruitment | local-recruitment-only |
| Testy | 54330 | simon_recruitment_test | recruitment_test | local-test-only |

Bazy i HTTP aplikacji domyślnie nasłuchują na `127.0.0.1`. Dane aplikacji mają osobny wolumen. Baza testowa korzysta z pamięci tymczasowej i traci dane po zatrzymaniu kontenera; testy powinny dodatkowo izolować dane między scenariuszami.

## Testowanie

Uruchom oddzielną bazę testową, a następnie pełną weryfikację:

```bash
docker compose --profile test up -d --wait postgres-test
./mvnw clean verify
```

W PowerShell drugie polecenie ma postać `./mvnw.cmd clean verify`.

- `*Test` / `*Tests`: testy uruchamiane przez Surefire w fazie `test`.
- `*IT`: testy integracyjne uruchamiane przez Failsafe w `verify`; dołącz `@ActiveProfiles("test")` do testów korzystających z konfiguracji testowej.
- Samo `./mvnw test` nie wykonuje `*IT`. W początkowym szablonie jest jeden test integracyjny połączenia, bez testów jednostkowych.
- Raporty: `target/surefire-reports` i `target/failsafe-reports`.

Szablon nie tworzy tabel domenowych. Przygotuj schemat oraz jego inicjalizację dla aplikacji i testów zgodnie z [db/README.md](db/README.md). GitHub Actions uruchamia pusty PostgreSQL i `./mvnw clean verify`; nie wykonuje za Ciebie skryptów SQL, dopóki nie podłączysz ich do procesu testowego.

GitHub Actions jest skonfigurowane dla PR do `main`, push do `main` i uruchomienia ręcznego. W prywatnych forkach dostępność uruchomienia zależy także od ustawień repozytorium/organizacji; rekruter może musieć je włączyć lub zatwierdzić. Brak uruchomienia workflow nie zastępuje wyniku testów lokalnych.

Testy samego symulatora uruchomisz osobno, bez bazy i aplikacji:

```bash
python -m unittest discover -s tools -p test_panel_simulator.py -v
```

GitHub Actions wykonuje również te testy. Nie zastępują one wymaganych testów Twojego rozwiązania uruchamianych przez Maven.

## Własna konfiguracja

| Zmienna | Zastosowanie |
| --- | --- |
| `DB_URL`, `DB_USER`, `DB_PASSWORD` | Połączenie aplikacji |
| `TEST_DB_URL`, `TEST_DB_USER`, `TEST_DB_PASSWORD` | Połączenie testów z profilem `test` |
| `SERVER_PORT`, `SERVER_ADDRESS` | Port/adres HTTP aplikacji |
| `DB_PORT`, `TEST_DB_PORT` | Opcjonalna zmiana portów hosta w Compose |

Przy zmianie `DB_PORT` ustaw też `DB_URL`; analogicznie dla bazy testowej. Przykład zmiany portu testowego w PowerShell:

```powershell
$env:TEST_DB_PORT = '54331'
$env:TEST_DB_URL = 'jdbc:postgresql://127.0.0.1:54331/simon_recruitment_test'
docker compose --profile test up -d --wait postgres-test
.\mvnw.cmd clean verify
```

## Pakowanie i zakończenie pracy

Po `clean verify` uruchamialny JAR znajduje się w `target`:

```bash
java -jar target/simon-recruitment-0.1.0-SNAPSHOT.jar
```

Do działania wymaga uruchomionej bazy aplikacji. Zatrzymanie kontenerów:

```bash
docker compose --profile test down
```

To zachowuje wolumen danych aplikacji; baza testowa jest tymczasowa. W razie potrzeby zmiany konfiguracji wystarczą lokalne zmienne środowiskowe.

## Notatki do rozwiązania — uzupełnij

- Zaimplementowane zachowanie:
- Schemat, jego inicjalizacja i migracje:
- Reguły tożsamości, indeksy i uzasadnienie:
- Granice transakcji i obsługa konkurujących żądań:
- Konfiguracja połączenia z centralą i sposób wznowienia odbioru po rozłączeniu:
- Uruchomione testy i wynik:
- Ograniczenia lub niedokończone elementy:
- Czas pierwszej implementacji:
- Czas poprawek po review:
- Wykorzystane źródła i narzędzia:

Odpowiedzi projektowe (łącznie maksymalnie jedna strona):

1. Uzasadnienie ścieżki, metody, statusów oraz błędów API odczytu:
2. Granica transakcji, równoległe duplikaty i utrata ACK po zapisie:
3. Diagnostyka błędów ramki, połączenia i zapisu oraz zarządzanie zasobami:
