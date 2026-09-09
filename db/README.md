# Schemat bazy — do przygotowania

Szablon uruchamia pustą bazę PostgreSQL. Nie zawiera tabel zdarzeń; schemat przygotuj zgodnie z [TASK.md](../TASK.md).

Tutaj możesz umieścić skrypty SQL albo wskazać w głównym README narzędzie migracji i jego lokalizację. Opisz utworzenie schematu zarówno bazy lokalnej, jak i testowej/CI. Automatyczna inicjalizacja SQL Spring Boot jest początkowo wyłączona przez `spring.sql.init.mode=never`.

Nie zmieniaj ręcznie tabel tylko na swojej bazie bez zapisania sposobu odtworzenia schematu. Zapewnienie migracji lub inicjalizacji w testach jest częścią zadania.
