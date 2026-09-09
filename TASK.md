# Zadanie rekrutacyjne - systemy SIMON: protokół centrali

## Zakres i organizacja

Zaimplementuj integrację z fikcyjną centralą alarmową przy użyciu protokołu SP/1 opisanego poniżej. Aplikacja jest klientem TCP, centrala serwerem. Zadanie jest inspirowane integracjami urządzeń w systemach wewnętrznych.

Zadanie obejmuje odbiór zdarzeń TCP, trwały zapis, potwierdzenia i API odczytu. Wszystkie poniższe wymagania tworzą jeden zakres. Nie rozbudowuj rozwiązania o funkcje spoza specyfikacji.

Zapisz faktyczny czas pracy i ograniczenia w README. Nie wymagamy UI, logowania użytkowników, historii operatorów, listy z filtrowaniem, obsługi wielu central, wysyłania poleceń ani wdrożenia produkcyjnego.

Użyj startera: Java 8, Spring Boot 2.7.x, Maven Wrapper, PostgreSQL 16 i jOOQ 3.12.x. Bibliotekę TCP wybierz samodzielnie; Netty nie jest wymagane. Serwisy wystawiaj przez interfejsy, implementacje nazywaj z sufiksem Impl i wstrzykuj przez konstruktor. Dostarcz schemat i testy uruchamiane przez Maven.

Praca odbywa się w domu. Oddanie, pytania, odpowiedzi i poprawki wyłącznie w prywatnym PR na GitHubie według README startera. Nie organizujemy prezentacji ani live codingu. **AI jest niedozwolone** w projektowaniu, kodzie, testach, dokumentacji i odpowiedziach/poprawkach w PR. Dozwolone są dokumentacja, wyszukiwanie źródeł i zwykłe funkcje IDE. Wymień źródła i narzędzia.

## SP/1 - format ramki

Każda ramka ma postać bajtową:

```text
53 50 | LENGTH (2 bajty) | BODY (LENGTH bajtów) | CHECKSUM (1 bajt)
```

- Pierwsze dwa bajty to ASCII SP, stały znacznik początku.
- LENGTH to nieoznaczona liczba big-endian, od 1 do 256. Obejmuje wyłącznie BODY.
- BODY jest tekstem ASCII, bez końca linii i bez spacji. Pola oddziela znak |.
- CHECKSUM = suma wszystkich bajtów BODY modulo 256. Jest surowym bajtem, nie tekstem hex. Nie obejmuje nagłówka ani długości. To suma kontrolna ćwiczenia, nie zabezpieczenie kryptograficzne.
- Cała ramka ma LENGTH + 5 bajtów. Nie ma escapingu; BODY odczytuje się według długości.
- Jeden odczyt TCP może zawierać fragment ramki, kilka ramek lub pełną ramkę i początek następnej. Granice odczytów nie są granicami komunikatów.
- Zły znacznik, długość poza zakresem, suma, ASCII, liczba pól albo typ/pola BODY: zamknij połączenie, niczego nie zapisuj z błędnej ramki i nie wysyłaj odpowiedzi na nią. Nie wymagamy resynchronizacji.
- Poprawne wcześniejsze ramki z tego samego odczytu pozostają przetworzone. Niepełną ramkę buforuj; EOF oznacza odrzucenie jej niepełnej końcówki.
- Limit czasu na odebranie całej ramki od jej pierwszego bajtu: 3 sekundy. Kolejne bajty nie odnawiają tego limitu. Po przekroczeniu zamknij połączenie. Limit nie dotyczy oczekiwania na pierwszy bajt następnej ramki; bez danych połączenie może pozostawać otwarte.

Przykład pełnej ramki dla BODY A|1|OK:
```text
53 50 00 06 41 7C 31 7C 4F 4B 04
```
Suma BODY wynosi 516, więc CHECKSUM = 4.

## Odbiór zdarzeń

Centrala wysyła:
```text
E|eventId|deviceId|code|epochSeconds
```

- eventId: dziesiętna liczba 1..2147483647, bez znaku i zer wiodących.
- deviceId: 1..32 znaków ASCII z [A-Za-z0-9_-], wielkość liter ma znaczenie.
- code: dokładnie ALARM, RESTORE lub TEST.
- epochSeconds: liczba sekund UTC od epoki Unix, zakres 0..4102444800; bez znaku i zer wiodących poza samym 0.
- Przykład: E|1|device-17|ALARM|1789380900.
- sourceId pochodzi z konfiguracji klienta (1..32 znaków jak deviceId), nie z ramki. Jedna konfiguracja odpowiada jednej centrali.

Zapisz w PostgreSQL:
- `id`: unikalny liczbowy identyfikator rekordu nadany przez aplikację lub bazę;
- `sourceId`: identyfikator centrali z konfiguracji klienta;
- `eventId`, `deviceId`, `code`: wartości z ramki;
- `occurredAt`: czas zdarzenia wynikający z `epochSeconds`;
- `receivedAt`: czas odebrania ramki użytej do pierwszego skutecznego zapisu zdarzenia.

Para (`sourceId`, `eventId`) identyfikuje zdarzenie. Identyczne ponowienie ma ten sam klucz i te same wartości `deviceId`, `code` oraz `epochSeconds`. Zmiana któregokolwiek z tych trzech pól przy tym samym kluczu oznacza konflikt. `id` i `receivedAt` nie uczestniczą w porównaniu treści; pozostają niezmienione przy ponowieniu i konflikcie. Zapis i porównanie duplikatu mają działać po restarcie i przy równoległym dostępie do jednej bazy.

Po zatwierdzonym zapisie odeślij ramkę:
```text
A|eventId|OK
```
Identyczne ponowienie zwraca to samo OK i nie zmienia danych/czasu odbioru. Ten sam klucz z inną treścią zwraca A|eventId|CONFLICT, bez zmian w bazie; połączenie pozostaje otwarte. Przy awarii bazy zamknij połączenie bez OK. OK potwierdza trwały odbiór zdarzenia, nie reakcję operatora.

Zaprojektuj REST do pobrania zdarzenia po sourceId i eventId. Sam dobierz ścieżkę, metody i statusy. Oczekiwany JSON:
```json
{
  "id": 101,
  "sourceId": "panel-01",
  "eventId": 1,
  "deviceId": "device-17",
  "code": "ALARM",
  "occurredAt": "2026-09-14T10:15:00Z",
  "receivedAt": "2026-09-14T10:15:02Z"
}
```
Daty zwracaj w UTC z `Z`; dopuszczalne są ułamki sekund. Zapewnij spójne błędy dla braku rekordu i niepoprawnego wejścia, bez szczegółów technicznych.

## Konfiguracja i zasoby

Konfiguruj host, port i sourceId przez właściwości Springa. Utrata połączenia może wymagać restartu aplikacji; opisz to ograniczenie i sposób ponownego uruchomienia odbioru w README. Automatyczny reconnect i heartbeat nie są wymagane. Zamykanie aplikacji oraz obsługa błędu połączenia muszą zwalniać nieużywane zasoby. Zakończenie aplikacji musi zatrzymać socket i wykonawców.

W README krótko uzasadnij projekt API, granice transakcji, sposób rozstrzygania duplikatów przy równoległym zapisie oraz zachowanie po utracie ACK. Opisz logi lub inne informacje diagnostyczne pozwalające rozróżnić błąd ramki, problem połączenia i błąd zapisu. Nie implementuj dodatkowych endpointów diagnostycznych.

## Symulator i testy

Dostarczamy konsolowy symulator centrali `tools/panel_simulator.py`, wymagający Python 3.9+ i wyłącznie biblioteki standardowej. Start w osobnym terminalu, przed uruchomieniem klienta:
```text
python tools/panel_simulator.py --scenario normal
```
Domyślnie nasłuchuje na `127.0.0.1:19090`. Parametry `--host` i `--port` zmieniają adres. Ustaw taki sam adres w konfiguracji swojego klienta. Symulator wysyła zdarzenia po nawiązaniu połączenia; nie oczekuje logowania ani powitania.

### Uruchamianie scenariuszy

Każdy scenariusz sprawdzaj dla `sourceId`, dla którego nie ma jeszcze zdarzeń w bazie, np. osobnego `panel-normal` i `panel-conflict`. Symulator używa ponownie tych samych `eventId`; zmiana scenariusza nie czyści bazy ani nie zmienia `sourceId` w kliencie.

W tabeli `E1` oznacza `E|1|device-17|ALARM|1789380900`, a `E2` oznacza `E|2|device-17|RESTORE|1789380901`. Każde ACK jest pełną ramką SP/1 z BODY `A|eventId|OK` albo `A|eventId|CONFLICT`.

| Scenariusz | Co wysyła symulator | Oczekiwane ACK | Baza i połączenie |
| --- | --- | --- | --- |
| `normal` | E1 | OK dla 1 | Jeden rekord; połączenie otwarte |
| `fragmented` | E1, po jednym bajcie na zapis do socketu | OK dla 1 | Jak `normal` |
| `coalesced` | E1 i E2 jednym zapisem do socketu | OK dla 1 i OK dla 2, w dowolnej kolejności | Dwa rekordy; połączenie otwarte |
| `duplicate` | Dwie identyczne E1 jednym zapisem | Dwa OK dla 1 | Jeden rekord, bez zmiany `id` i `receivedAt`; połączenie otwarte |
| `conflict` | E1; po OK jej wersję z `code=TEST`; po CONFLICT ponownie pierwotną E1 | Kolejno OK, CONFLICT, OK dla 1 | Jeden niezmieniony rekord ALARM; połączenie otwarte |
| `bad-checksum` | E1 z błędną sumą kontrolną | Brak | Brak rekordu; klient zamyka połączenie |
| `bad-length` | Nagłówek z LENGTH=257 | Brak | Brak rekordu; klient zamyka połączenie |
| `truncated` | Niepełną E1, następnie EOF w kierunku do klienta | Brak | Brak rekordu; klient odrzuca końcówkę i zamyka połączenie |
| `frame-timeout` | E1 bez ostatniego bajtu, bez EOF i bez dalszych danych | Brak | Brak rekordu; klient zamyka połączenie po 3 sekundach od pierwszego bajtu |
| `disconnect` | E1; po odebraniu OK zamyka połączenie | OK dla 1 | Jeden rekord; klient zwalnia zasoby połączenia |
| `ack-loss` | E1; ignoruje pierwsze OK i rozłącza; przy następnym połączeniu ponawia E1 | OK dla 1 w obu połączeniach | Jeden rekord z niezmienionymi `id` i `receivedAt`; drugie połączenie otwarte |

Symulator wypisuje `TX`, `RX` oraz wynik `PASS` lub `FAIL` dla komunikacji TCP. Sprawdza pełne ramki ACK, ich treść i liczbę oraz wymagane zamknięcie połączenia. **Nie sprawdza bazy ani REST API.** Wynik `PASS` nie potwierdza trwałego zapisu, poprawnego momentu commit ani ukończenia zadania; sprawdź te warunki osobnymi testami.

Po poprawnych ACK symulator nie rozłącza z powodu bezczynności i czeka na zamknięcie klienta. Zatrzymasz go przez `Ctrl+C`. Brak ACK lub zamknięcia po błędnej ramce jest zgłaszany po 10 sekundach; `--response-timeout 30` wydłuża ten limit narzędzia, np. podczas debugowania. Nie jest to dodatkowy wymóg czasu odpowiedzi aplikacji. Scenariusz `frame-timeout` sprawdza osobno protokołowe 3 sekundy, z tolerancją pomiaru zamknięcia po stronie symulatora.

### Ponowienie po utracie ACK

W scenariuszu `ack-loss` symulator technicznie odbiera pierwsze poprawne ACK, ale celowo go nie uznaje. Pozwala to w kontrolowany sposób odtworzyć ponowienie zdarzenia, którego odbiór centrala uważa za niepotwierdzony; nie jest to rzeczywiste zgubienie pakietu TCP.

1. Uruchom `ack-loss`, następnie klienta dla nowego `sourceId`.
2. Po komunikacie o zignorowaniu ACK sprawdź zapisany rekord przez swoje API i zapamiętaj `id` oraz `receivedAt`.
3. Pozostaw symulator i bazę uruchomione. Wznów połączenie klienta; restart aplikacji jest wystarczający. Zachowaj ten sam `sourceId` i tę samą bazę.
4. Po drugim OK sprawdź, że nadal istnieje jeden rekord, z tym samym `id`, `receivedAt` i treścią. Sam odczyt jednego rekordu przez REST nie dowodzi braku duplikatów w bazie.

Zignorowanie ACK następuje raz na uruchomienie symulatora. Scenariusz `disconnect` rozłącza dopiero po uznaniu ACK i nie zastępuje tego sprawdzenia.

### Wymagane testy rozwiązania

Własne testy muszą sprawdzić:
- składanie ramki przy każdym możliwym miejscu podziału i kilka ramek w jednym buforze;
- walidację długości, sumy, pól oraz EOF/timeout w środku ramki;
- zapis, ponowienie, konflikt i pobranie REST;
- brak pozytywnego ACK przy błędzie zapisu; duplikat po utracie ACK;
- dwa równoległe zapisy identycznego zdarzenia: jeden rekord;
- zwolnienie zasobów po błędzie połączenia i zatrzymaniu aplikacji.

Testy SQL wykonaj na PostgreSQL. Testy transportu mogą korzystać z własnego serwera testowego. Symulator nie wymusza konkretnego podziału odczytów TCP; deterministyczne testy fragmentacji napisz dla dekodera.

## Co oceniamy

Poprawność protokołu, spójność danych, projekt REST, obsługę awarii i zasobów, testy, czytelność, odtwarzalne uruchomienie oraz uzasadnienie decyzji. Oceniamy rozwiązanie w podanym zakresie, nie liczbę dodatkowych funkcji czy użytych bibliotek. Opisz ograniczenia i czas pracy oraz odpowiadaj na uwagi w tym samym PR.
