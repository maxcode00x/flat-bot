"""Тексты бота на 4 языках: ru, pl, en, uk."""

LANGS = ["ru", "pl", "en", "uk"]
LANG_NAMES = {"ru": "🇷🇺 Русский", "pl": "🇵🇱 Polski", "en": "🇬🇧 English", "uk": "🇺🇦 Українська"}
LANG_PROMPT = ("🌐 Выбери язык\n🌐 Wybierz język\n🌐 Choose your language\n🌐 Обери мову")

T = {
    "btn_filters": {"ru": "⚙️ Фильтры", "pl": "⚙️ Filtry", "en": "⚙️ Filters", "uk": "⚙️ Фільтри"},
    "btn_lang": {"ru": "🌐 Язык", "pl": "🌐 Język", "en": "🌐 Language", "uk": "🌐 Мова"},
    "lang_set": {"ru": "✅ Язык: Русский", "pl": "✅ Język: polski", "en": "✅ Language: English",
                 "uk": "✅ Мова: українська"},
    "welcome": {
        "ru": "Привет! Я ищу квартиры и комнаты на <b>OLX</b>, <b>Otodom</b>, <b>Domiporta</b> и "
              "<b>Nieruchomosci-online</b> и присылаю только новые объявления по твоим фильтрам.\n\n"
              "Нажми <b>⚙️ Фильтры</b> внизу, выбери, что ищешь, и сохрани. Пока фильтры не выбраны, я ничего "
              "не присылаю.\n\nНовые объявления проверяю примерно раз в 10 минут. Остановить — переключатель "
              "«Поиск на паузе» в фильтрах.",
        "pl": "Cześć! Szukam mieszkań i pokoi na <b>OLX</b>, <b>Otodom</b>, <b>Domiporta</b> i "
              "<b>Nieruchomosci-online</b> i wysyłam tylko nowe ogłoszenia według Twoich filtrów.\n\n"
              "Kliknij <b>⚙️ Filtry</b> na dole, wybierz, czego szukasz, i zapisz. Dopóki filtry nie są ustawione, "
              "niczego nie wysyłam.\n\nNowe ogłoszenia sprawdzam mniej więcej co 10 minut. Aby zatrzymać — "
              "przełącznik „Wyszukiwanie wstrzymane” w filtrach.",
        "en": "Hi! I search for flats and rooms on <b>OLX</b>, <b>Otodom</b>, <b>Domiporta</b> and "
              "<b>Nieruchomosci-online</b> and send you only new listings that match your filters.\n\n"
              "Tap <b>⚙️ Filters</b> below, choose what you're looking for and save. Until you set filters, "
              "I won't send anything.\n\nI check for new listings about every 10 minutes. To stop, use the "
              "“Search paused” switch in the filters.",
        "uk": "Привіт! Я шукаю квартири й кімнати на <b>OLX</b>, <b>Otodom</b>, <b>Domiporta</b> та "
              "<b>Nieruchomosci-online</b> і надсилаю лише нові оголошення за твоїми фільтрами.\n\n"
              "Натисни <b>⚙️ Фільтри</b> внизу, обери, що шукаєш, і збережи. Поки фільтри не обрані, я нічого "
              "не надсилаю.\n\nНові оголошення перевіряю приблизно раз на 10 хвилин. Зупинити — перемикач "
              "«Пошук на паузі» у фільтрах.",
    },
    "saved": {"ru": "✅ <b>Фильтры сохранены.</b>", "pl": "✅ <b>Filtry zapisane.</b>",
              "en": "✅ <b>Filters saved.</b>", "uk": "✅ <b>Фільтри збережено.</b>"},
    "paused": {"ru": "⏸ <b>Поиск на паузе.</b>", "pl": "⏸ <b>Wyszukiwanie wstrzymane.</b>",
               "en": "⏸ <b>Search paused.</b>", "uk": "⏸ <b>Пошук на паузі.</b>"},
    "paused_tail": {"ru": "Чтобы продолжить — открой фильтры и выключи паузу.",
                    "pl": "Aby wznowić — otwórz filtry i wyłącz pauzę.",
                    "en": "To resume, open the filters and turn the pause off.",
                    "uk": "Щоб продовжити — відкрий фільтри й вимкни паузу."},
    "first_tail": {"ru": "Сейчас пришлю {n} самых свежих подходящих, дальше — только новые.",
                   "pl": "Zaraz wyślę {n} najnowszych pasujących, potem — tylko nowe.",
                   "en": "I'll send the {n} newest matching listings now, then only new ones.",
                   "uk": "Зараз надішлю {n} найсвіжіших відповідних, далі — лише нові."},
    "only_new": {"ru": "Дальше присылаю только новые объявления.", "pl": "Dalej wysyłam tylko nowe ogłoszenia.",
                 "en": "From now on I'll send only new listings.", "uk": "Далі надсилаю лише нові оголошення."},
    "your_filters": {"ru": "Твои фильтры:", "pl": "Twoje filtry:", "en": "Your filters:", "uk": "Твої фільтри:"},
    "change_hint": {"ru": "Изменить — кнопка <b>{btn}</b>.", "pl": "Zmień — przycisk <b>{btn}</b>.",
                    "en": "To change them, tap <b>{btn}</b>.", "uk": "Змінити — кнопка <b>{btn}</b>."},
    "closed": {"ru": "Извини, сейчас бот не принимает новых пользователей.",
               "pl": "Przepraszam, bot obecnie nie przyjmuje nowych użytkowników.",
               "en": "Sorry, the bot isn't accepting new users right now.",
               "uk": "Вибач, зараз бот не приймає нових користувачів."},
    "read_error": {"ru": "Не смог прочитать фильтры: {e}", "pl": "Nie udało się odczytać filtrów: {e}",
                   "en": "Couldn't read the filters: {e}", "uk": "Не вдалося прочитати фільтри: {e}"},
    # сводка фильтров
    "kind_flat": {"ru": "квартира", "pl": "mieszkanie", "en": "flat", "uk": "квартира"},
    "kind_room": {"ru": "комната", "pl": "pokój", "en": "room", "uk": "кімната"},
    "kind_both": {"ru": "квартира или комната", "pl": "mieszkanie lub pokój", "en": "flat or room",
                  "uk": "квартира або кімната"},
    "rent": {"ru": "аренда", "pl": "czynsz najmu", "en": "rent", "uk": "оренда"},
    "total_max": {"ru": "с czynsz до {v} zł", "pl": "z czynszem adm. do {v} zł", "en": "incl. czynsz up to {v} zł",
                  "uk": "з czynsz до {v} zł"},
    "from": {"ru": "от", "pl": "od", "en": "from", "uk": "від"},
    "to": {"ru": "до", "pl": "do", "en": "up to", "uk": "до"},
    "rooms_n": {"ru": "комнат", "pl": "pokoi", "en": "rooms", "uk": "кімнат"},
    "floor": {"ru": "этаж", "pl": "piętro", "en": "floor", "uk": "поверх"},
    "ground": {"ru": "партер", "pl": "parter", "en": "ground floor", "uk": "партер"},
    "built_from": {"ru": "дом от {y} г.", "pl": "budynek od {y} r.", "en": "built from {y}", "uk": "будинок від {y} р."},
    "heating": {"ru": "отопление", "pl": "ogrzewanie", "en": "heating", "uk": "опалення"},
    "room_for": {"ru": "комната на {n} чел.", "pl": "pokój dla {n} os.", "en": "room for {n}", "uk": "кімната на {n} ос."},
    "rented_to": {"ru": "сдают {who}", "pl": "dla: {who}", "en": "for: {who}", "uk": "здають {who}"},
    "private_only": {"ru": "только частники", "pl": "tylko prywatne", "en": "private owners only",
                     "uk": "лише приватні власники"},
    # объявление
    "furn": {"ru": "с мебелью", "pl": "umeblowane", "en": "furnished", "uk": "з меблями"},
    "pets": {"ru": "можно с животными", "pl": "zwierzęta OK", "en": "pets OK", "uk": "можна з тваринами"},
    "people": {"ru": "на {n} чел.", "pl": "dla {n} os.", "en": "for {n}", "uk": "на {n} ос."},
    "for": {"ru": "для", "pl": "dla", "en": "for", "uk": "для"},
    "private": {"ru": "частник", "pl": "prywatne", "en": "private", "uk": "приватний"},
    "agency": {"ru": "агентство", "pl": "biuro", "en": "agency", "uk": "агентство"},
    "via": {"ru": "через", "pl": "przez", "en": "via", "uk": "через"},
}

BUILDING_T = {
    "BLOCK": {"ru": "блок", "pl": "blok", "en": "apartment block", "uk": "блок"},
    "TENEMENT": {"ru": "каменица", "pl": "kamienica", "en": "tenement", "uk": "кам'яниця"},
    "APARTMENT": {"ru": "апартаментовец", "pl": "apartamentowiec", "en": "modern building", "uk": "апартаментовець"},
    "HOUSE": {"ru": "дом", "pl": "dom", "en": "house", "uk": "будинок"},
    "LOFT": {"ru": "лофт", "pl": "loft", "en": "loft", "uk": "лофт"},
    "OTHER": {"ru": "другое", "pl": "inny", "en": "other", "uk": "інше"},
}
EXTRAS_T = {
    "BALCONY": {"ru": "балкон", "pl": "balkon", "en": "balcony", "uk": "балкон"},
    "TERRACE": {"ru": "терраса", "pl": "taras", "en": "terrace", "uk": "тераса"},
    "GARDEN": {"ru": "сад", "pl": "ogródek", "en": "garden", "uk": "сад"},
    "LIFT": {"ru": "лифт", "pl": "winda", "en": "lift", "uk": "ліфт"},
    "GARAGE": {"ru": "гараж/парковка", "pl": "garaż/parking", "en": "garage/parking", "uk": "гараж/паркінг"},
    "AIR_CONDITIONING": {"ru": "кондиционер", "pl": "klimatyzacja", "en": "air conditioning", "uk": "кондиціонер"},
    "SEPARATE_KITCHEN": {"ru": "отдельная кухня", "pl": "oddzielna kuchnia", "en": "separate kitchen",
                         "uk": "окрема кухня"},
    "INTERNET": {"ru": "интернет", "pl": "internet", "en": "internet", "uk": "інтернет"},
}
HEATING_T = {
    "URBAN": {"ru": "городское (miejskie)", "pl": "miejskie", "en": "district heating", "uk": "міське (miejskie)"},
    "GAS": {"ru": "газовое", "pl": "gazowe", "en": "gas", "uk": "газове"},
    "ELECTRICAL": {"ru": "электрическое", "pl": "elektryczne", "en": "electric", "uk": "електричне"},
    "BOILER_ROOM": {"ru": "котельная", "pl": "kotłownia", "en": "boiler room", "uk": "котельня"},
    "TILED_STOVE": {"ru": "кафельная печь", "pl": "piec kaflowy", "en": "tiled stove", "uk": "кахельна піч"},
    "OTHER": {"ru": "другое", "pl": "inne", "en": "other", "uk": "інше"},
}
PREF_T = {
    "man": {"ru": "мужчине", "pl": "mężczyzna", "en": "man", "uk": "чоловіку"},
    "women": {"ru": "женщине", "pl": "kobieta", "en": "woman", "uk": "жінці"},
    "student": {"ru": "студенту", "pl": "student", "en": "student", "uk": "студенту"},
    "working": {"ru": "работающему", "pl": "osoba pracująca", "en": "working person", "uk": "працюючому"},
}


def t(key: str, lang: str, **kw) -> str:
    row = T[key]
    s = row.get(lang) or row["ru"]
    return s.format(**kw) if kw else s


def tr(table: dict, code: str, lang: str) -> str:
    row = table.get(code) or {}
    return row.get(lang) or row.get("ru") or code


def lang_of(user: dict | None) -> str:
    l = (user or {}).get("lang")
    return l if l in LANGS else "ru"

T.update({
    "btn_fav_list": {"ru": "❤️ Избранное", "pl": "❤️ Ulubione", "en": "❤️ Saved", "uk": "❤️ Обране"},
    "b_fav": {"ru": "❤️ В избранное", "pl": "❤️ Do ulubionych", "en": "❤️ Save", "uk": "❤️ В обране"},
    "b_unfav": {"ru": "💔 Убрать", "pl": "💔 Usuń", "en": "💔 Unsave", "uk": "💔 Прибрати"},
    "b_hide": {"ru": "🚫 Скрыть", "pl": "🚫 Ukryj", "en": "🚫 Hide", "uk": "🚫 Сховати"},
    "b_write": {"ru": "✉️ Написать", "pl": "✉️ Napisz", "en": "✉️ Message", "uk": "✉️ Написати"},
    "b_map": {"ru": "📍 Карта", "pl": "📍 Mapa", "en": "📍 Map", "uk": "📍 Мапа"},
    "b_open": {"ru": "🔗 Открыть", "pl": "🔗 Otwórz", "en": "🔗 Open", "uk": "🔗 Відкрити"},
    "faved": {"ru": "❤️ Добавлено в избранное", "pl": "❤️ Dodano do ulubionych", "en": "❤️ Saved",
              "uk": "❤️ Додано в обране"},
    "unfaved": {"ru": "Убрано из избранного", "pl": "Usunięto z ulubionych", "en": "Removed from saved",
                "uk": "Прибрано з обраного"},
    "hidden": {"ru": "🚫 Скрыто, больше не покажу", "pl": "🚫 Ukryte, więcej nie pokażę",
               "en": "🚫 Hidden, won't show it again", "uk": "🚫 Сховано, більше не покажу"},
    "gone": {"ru": "Это объявление уже не найти", "pl": "Tego ogłoszenia już nie ma", "en": "This listing is no longer available",
             "uk": "Це оголошення вже не знайти"},
    "fav_title": {"ru": "❤️ <b>Избранное</b> ({n}):", "pl": "❤️ <b>Ulubione</b> ({n}):", "en": "❤️ <b>Saved</b> ({n}):",
                  "uk": "❤️ <b>Обране</b> ({n}):"},
    "fav_empty": {"ru": "В избранном пока пусто. Нажимай ❤️ под объявлениями.",
                  "pl": "Brak ulubionych. Klikaj ❤️ pod ogłoszeniami.",
                  "en": "Nothing saved yet. Tap ❤️ under listings.", "uk": "В обраному поки порожньо. Натискай ❤️ під оголошеннями."},
    "fav_hint": {"ru": "Убрать — нажми 💔 под объявлением.", "pl": "Aby usunąć — kliknij 💔 pod ogłoszeniem.",
                 "en": "To remove, tap 💔 under the listing.", "uk": "Прибрати — натисни 💔 під оголошенням."},
    "msg_intro": {"ru": "✉️ Нажми на текст — он скопируется. Открой объявление и вставь в сообщение владельцу:",
                  "pl": "✉️ Kliknij tekst, aby go skopiować. Otwórz ogłoszenie i wklej w wiadomości do właściciela:",
                  "en": "✉️ Tap the text to copy it. Open the listing and paste it into a message to the owner:",
                  "uk": "✉️ Натисни на текст — він скопіюється. Відкрий оголошення й встав у повідомлення власнику:"},
    "msg_short": {"ru": "Коротко для SMS / WhatsApp:", "pl": "Krótko na SMS / WhatsApp:", "en": "Short version for SMS / WhatsApp:",
                  "uk": "Коротко для SMS / WhatsApp:"},
    "msg_fill": {"ru": "💡 Заполни «О себе» в ⚙️ Фильтрах — и текст будет с твоими данными.",
                 "pl": "💡 Uzupełnij „O mnie” w ⚙️ Filtrach — tekst będzie z Twoimi danymi.",
                 "en": "💡 Fill in “About me” in ⚙️ Filters and the text will include your details.",
                 "uk": "💡 Заповни «Про себе» у ⚙️ Фільтрах — і текст буде з твоїми даними."},
    "drop": {"ru": "📉 <b>Цена снизилась:</b> было {old}, стало {new}", "pl": "📉 <b>Cena spadła:</b> było {old}, jest {new}",
             "en": "📉 <b>Price dropped:</b> was {old}, now {new}", "uk": "📉 <b>Ціна знизилась:</b> було {old}, стало {new}"},
    "dup": {"ru": "🔁 Похоже, это же объявление на {site}:", "pl": "🔁 Wygląda na to samo ogłoszenie na {site}:",
            "en": "🔁 Looks like the same listing on {site}:", "uk": "🔁 Схоже, це ж оголошення на {site}:"},
    "night": {"ru": "🌅 Пока были тихие часы, нашлось новых объявлений: {n}", "pl": "🌅 W godzinach ciszy znalazłem nowych ogłoszeń: {n}",
              "en": "🌅 New listings found during quiet hours: {n}", "uk": "🌅 Поки були тихі години, знайшлося нових оголошень: {n}"},
    "ev_below": {"ru": "📊 на {d}% дешевле среднего по {w} ({m})", "pl": "📊 {d}% taniej niż średnio: {w} ({m})",
                 "en": "📊 {d}% below the {w} average ({m})", "uk": "📊 на {d}% дешевше за середнє по {w} ({m})"},
    "ev_above": {"ru": "📊 на {d}% дороже среднего по {w} ({m})", "pl": "📊 {d}% drożej niż średnio: {w} ({m})",
                 "en": "📊 {d}% above the {w} average ({m})", "uk": "📊 на {d}% дорожче за середнє по {w} ({m})"},
    "ev_avg": {"ru": "📊 около средней цены по {w} ({m})", "pl": "📊 w okolicach średniej: {w} ({m})",
               "en": "📊 around the {w} average ({m})", "uk": "📊 близько середньої ціни по {w} ({m})"},
    "scam_head": {"ru": "⚠️ <b>Осторожно:</b>", "pl": "⚠️ <b>Uwaga:</b>", "en": "⚠️ <b>Careful:</b>", "uk": "⚠️ <b>Обережно:</b>"},
    "profile": {"ru": "профиль", "pl": "profil", "en": "profile", "uk": "профіль"},
    "quiet_on": {"ru": "🌙 Тихие часы {a}:00–{b}:00", "pl": "🌙 Godziny ciszy {a}:00–{b}:00", "en": "🌙 Quiet hours {a}:00–{b}:00",
                 "uk": "🌙 Тихі години {a}:00–{b}:00"},
})

SCAM_T = {
    "prepay": {"ru": "просят деньги до просмотра", "pl": "prośba o pieniądze przed obejrzeniem",
               "en": "asks for money before a viewing", "uk": "просять гроші до перегляду"},
    "abroad": {"ru": "владелец «за границей»", "pl": "właściciel „za granicą”", "en": "owner says they're abroad",
               "uk": "власник «за кордоном»"},
    "keys_mail": {"ru": "ключи «пришлют курьером»", "pl": "klucze „wyślą kurierem”", "en": "keys “sent by courier”",
                  "uk": "ключі «надішлють кур'єром»"},
    "no_viewing": {"ru": "без просмотра", "pl": "bez oglądania", "en": "no viewing possible", "uk": "без перегляду"},
    "pay_service": {"ru": "оплата через Airbnb/Booking/переводы", "pl": "płatność przez Airbnb/Booking/przekaz",
                    "en": "payment via Airbnb/Booking/money transfer", "uk": "оплата через Airbnb/Booking/перекази"},
    "contact_only": {"ru": "связь только через мессенджер/почту", "pl": "kontakt tylko przez komunikator/e-mail",
                     "en": "contact only via messenger/e-mail", "uk": "зв'язок лише через месенджер/пошту"},
    "cheap": {"ru": "цена намного ниже рынка", "pl": "cena dużo poniżej rynku", "en": "price far below the market",
              "uk": "ціна набагато нижча за ринок"},
}
