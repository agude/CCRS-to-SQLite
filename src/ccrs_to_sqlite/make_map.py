"""Normalization of vehicle make strings.

The published CCRS years hold 31,144 distinct make strings over 8.5 million
non-empty values, mixing two abbreviation conventions with full names. The
later years use NCIC codes (`TOYT`, `LEXS`, `PTRB`); the earlier years use a
plain first-four-letters truncation (`TOYO`, `LEXU`, `PETE`). A map built
against one year covers one convention: seeded from the 2025 file alone it
reached 93.6% of that year and only 83.9% of all eleven, with `TOYO` alone --
498,501 rows, the single most common string in the dataset -- falling through
as NULL.

So the map is seeded from switrs-to-sqlite, which accumulated both conventions
plus a long tail of real-world typos (`BWM`, `BMW/`) over years of NCIC data,
and corrected against CCRS frequencies where the two disagree. That reaches
96.7% of vehicle rows across all eleven years. What is left is a genuine long
tail: 444,000 rows over 30,151 distinct strings, none above 6,000 rows.

The map is deliberately *not* the switrs-to-sqlite design, where the mapped
value replaced the raw string and every correction to the map changed the
output for previously convertible input. Here:

* `vehicles.make_raw` keeps the source string verbatim.
* `vehicles.make` holds the normalized name, and is NULL when unmapped.

A miss degrades to NULL instead of corrupting data, and every normalization
stays auditable against the raw column. Adding entries is additive: rows that
were NULL become populated, and nothing already populated changes.

Ambiguous strings are left out on purpose. `UNKNOWN` is the obvious one --- it
is not a manufacturer, so it stays NULL rather than becoming a make named
"unknown" that aggregates alongside real ones. switrs' placeholder entries
(`N/A`, `NOT STATED`, `--`) are dropped for the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum, unique


@unique
class Make(StrEnum):
    """The normalized maker names. The map may only produce one of these.

    `@unique` is load-bearing rather than decoration. Two members declared with
    the same value do not raise on their own --- the second silently becomes an
    alias of the first, disappears from iteration, and takes its raw strings
    with it into the other maker. With 83 makers merged from two source maps
    that is a live hazard, and it fails at import here instead.
    """

    ACADIAN = "ACADIAN"
    ACURA = "ACURA"
    ALFA_ROMEO = "ALFA ROMEO"
    AMERICAN_LAFRANCE = "AMERICAN LAFRANCE"
    AMERICAN_MOTORS = "AMERICAN MOTORS"
    AUDI = "AUDI"
    AUTOCAR = "AUTOCAR"
    BEALL = "BEALL"
    BENTLEY = "BENTLEY"
    BLUEBIRD = "BLUEBIRD"
    BMW = "BMW"
    BUICK = "BUICK"
    CADILLAC = "CADILLAC"
    CHEVROLET = "CHEVROLET"
    CHRYSLER = "CHRYSLER"
    CIMC = "CIMC"
    CROWN = "CROWN"
    DAEWOO = "DAEWOO"
    DATSUN = "DATSUN"
    DELOREAN = "DELOREAN"
    DODGE = "DODGE"
    DUCATI = "DUCATI"
    FERRARI = "FERRARI"
    FIAT = "FIAT"
    FORD = "FORD"
    FREIGHTLINER = "FREIGHTLINER"
    GEO = "GEO"
    GILLIG = "GILLIG"
    GMC = "GMC"
    GREAT_DANE = "GREAT DANE"
    GRUMMAN = "GRUMMAN"
    HARLEY_DAVIDSON = "HARLEY-DAVIDSON"
    HINO = "HINO"
    HONDA = "HONDA"
    HUMMER = "HUMMER"
    HYUNDAI = "HYUNDAI"
    HYUNDAI_TRANSLEAD = "HYUNDAI TRANSLEAD"
    INFINITI = "INFINITI"
    INTERNATIONAL = "INTERNATIONAL"
    ISUZU = "ISUZU"
    JAGUAR = "JAGUAR"
    JEEP = "JEEP"
    JOHN_DEERE = "JOHN DEERE"
    KAWASAKI = "KAWASAKI"
    KENWORTH = "KENWORTH"
    KIA = "KIA"
    LAND_ROVER = "LAND ROVER"
    LEXUS = "LEXUS"
    LINCOLN = "LINCOLN"
    MACK = "MACK"
    MASERATI = "MASERATI"
    MAZDA = "MAZDA"
    MERCEDES_BENZ = "MERCEDES-BENZ"
    MERCURY = "MERCURY"
    MINI = "MINI"
    MITSUBISHI = "MITSUBISHI"
    NISSAN = "NISSAN"
    OLDSMOBILE = "OLDSMOBILE"
    PETERBILT = "PETERBILT"
    PLYMOUTH = "PLYMOUTH"
    PONTIAC = "PONTIAC"
    PORSCHE = "PORSCHE"
    RAD_POWER_BIKES = "RAD POWER BIKES"
    RAM = "RAM"
    SAAB = "SAAB"
    SATURN = "SATURN"
    SCHWINN = "SCHWINN"
    SCION = "SCION"
    SMART = "SMART"
    STERLING = "STERLING"
    SUBARU = "SUBARU"
    SUZUKI = "SUZUKI"
    TAOTAO = "TAOTAO"
    TESLA = "TESLA"
    THOMAS = "THOMAS"
    TOYOTA = "TOYOTA"
    TREK = "TREK"
    TRIUMPH = "TRIUMPH"
    UTILITY = "UTILITY"
    VESPA = "VESPA"
    VOLKSWAGEN = "VOLKSWAGEN"
    VOLVO = "VOLVO"
    WABASH = "WABASH"
    WHITE = "WHITE"
    WINNEBAGO = "WINNEBAGO"
    YAMAHA = "YAMAHA"


RAW_STRINGS_BY_MAKE: Mapping[Make, tuple[str, ...]] = {
    Make.ACADIAN: ("ACAD", "ACADIAN"),
    Make.ACURA: ("ACU", "ACRU", "ACUA", "ACUR", "ACRUA", "ACURA", "ACCURA", "ACUR /", "ACURA/"),
    Make.ALFA_ROMEO: ("ALFA", "ALFR", "ALFA ROMEO", "ALFA ROMERO"),
    Make.AMERICAN_LAFRANCE: ("AMERICAN LAFRANCE", "AMERICAN LA FRANCE"),
    Make.AMERICAN_MOTORS: (
        "AMER",
        "AMERI",
        "AMERICAN",
        "AMERICAN MOTORS",
        "AMERICAN MOTORS (AMC)",
    ),
    Make.AUDI: ("AUD", "AUDI", "AUDU", "AUID", "AUDI/", "AUIDI", "AUDI /"),
    Make.AUTOCAR: ("AUTOCAR",),
    Make.BEALL: ("BEALL",),
    Make.BENTLEY: ("BENT", "BENTL", "BENTLEY"),
    Make.BLUEBIRD: (
        "BLU",
        "BLUB",
        "BLUE",
        "BLUBD",
        "BLUBI",
        "BLUBR",
        "BLUEB",
        "BLUBRD",
        "BLUBIRD",
        "BLUEBIR",
        "BLU BIRD",
        "BLUE BIR",
        "BLUEBIRD",
        "BLUE BIRD",
        "BLUEBIRD (BUS)",
    ),
    Make.BMW: ("BMW", "BWM", "BWW", "BMW/", "BMW1", "BMWX", "BMW`", "BMW /"),
    Make.BUICK: ("BUI", "BUCK", "BUIC", "BUIK", "BUCIK", "BUICK", "BUICK/"),
    Make.CADILLAC: (
        "CADI",
        "CADI/",
        "CADIL",
        "CADILA",
        "CADILL",
        "CADILAC",
        "CADILLA",
        "CADILLAC",
    ),
    Make.CHEVROLET: (
        "CHV",
        "CEHV",
        "CHEV",
        "CHVY",
        "CEHVY",
        "CHEV/",
        "CHEVE",
        "CHEVR",
        "CHEVT",
        "CHEVY",
        "CHEV`",
        "TAHOE",
        "CHEV /",
        "CHEVER",
        "CHEVEY",
        "CHEVRO",
        "CHEVY/",
        "CHEVRLT",
        "CHEVROL",
        "CHEROLET",
        "CHEVEROL",
        "CHEVOLET",
        "CHEVRLET",
        "CHEVROEL",
        "CHEVROET",
        "CHEVROLE",
        "CHEVROLT",
        "CHVROLET",
        "CHEVROLET",
    ),
    Make.CHRYSLER: (
        "CHY",
        "CRY",
        "CHRS",
        "CHRY",
        "CRYS",
        "CHRSY",
        "CHRY/",
        "CHRYL",
        "CHRYS",
        "CHRYS/",
        "CHRYSL",
        "CHRYST",
        "CHRSLER",
        "CHRYLER",
        "CHRYSER",
        "CHRYSLE",
        "CHRYSLR",
        "CHYSLER",
        "CRYSLER",
        "CHRYLSER",
        "CHRYSLER",
        "CHRYSTLE",
        "CHYRSLER",
    ),
    Make.CIMC: ("CIMC",),
    Make.CROWN: ("CROW", "CROWN", "CROWN (BUS)"),
    Make.DAEWOO: ("DAEW", "DAEWO", "DAEWOO"),
    Make.DATSUN: ("DATS", "DATSU", "DATSUN"),
    Make.DELOREAN: ("DELOREAN",),
    Make.DODGE: (
        "DOD",
        "DOG",
        "DDGE",
        "DODE",
        "DODG",
        "DOGE",
        "D0DGE",
        "DDOGE",
        "DODEG",
        "DODG/",
        "DODGE",
        "DODGW",
        "DOGDE",
        "DOGGE",
        "DODDGE",
        "DODG /",
        "DODGE/",
        "DODGER",
        "DODGE`",
        "DODGE /",
    ),
    Make.DUCATI: ("DUCA", "DUCAT", "DUCTI", "DUCATI", "DUCATI (MOTORCYCLE)"),
    Make.FERRARI: ("FERRARA", "FERRARI"),
    Make.FIAT: ("FIAT", "FIAT-ABARTH"),
    Make.FORD: (
        "FOR",
        "FRD",
        "FORC",
        "FORD",
        "FORE",
        "FORF",
        "FORR",
        "FORS",
        "FROD",
        "RORD",
        "FORD/",
        "FORDE",
        "FORD`",
        "FORED",
        "FORRD",
        "FORD /",
        "RANGER",
    ),
    Make.FREIGHTLINER: (
        "FRH",
        "FRI",
        "FRT",
        "FTL",
        "FREI",
        "FRGH",
        "FRGT",
        "FRHI",
        "FRHK",
        "FRHT",
        "FRIE",
        "FRTH",
        "FRTL",
        "FTLR",
        "FREHT",
        "FREIG",
        "FREIT",
        "FRGHT",
        "FRGTH",
        "FRHGT",
        "FRHT.",
        "FRHT/",
        "FRHTL",
        "FRIET",
        "FRIGH",
        "FRTLN",
        "FREI /",
        "FREIGH",
        "FREIGT",
        "FREIHT",
        "FRGHT.",
        "FRHT /",
        "FRHTLN",
        "FRIEGH",
        "FRIGHT",
        "FRTLNR",
        "FREIGHT",
        "FRGTLNR",
        "FRHTLNR",
        "FRIEGHT",
        "FREIGHTL",
        "FREITLIN",
        "FREITLNR",
        "FRGHTLNR",
        "FRHTLINE",
        "FRHTLINR",
        "FRIEGHTL",
        "FRTLINER",
        "FREIGHTLINER",
        "FREIGHT LINER",
        "FREIGHTLINER CORP",
    ),
    Make.GEO: ("GEO",),
    Make.GILLIG: (
        "GILG",
        "GILL",
        "GILIG",
        "GILLI",
        "GILLIC",
        "GILLIG",
        "GILLIG BUS",
        "GILLIG (BUS)",
    ),
    Make.GMC: (
        "GM",
        "GMA",
        "GMC",
        "GMG",
        "GMS",
        "GMV",
        "GMX",
        "GMZ",
        "GNC",
        "GMC/",
        "GMCX",
        "GMC /",
        "GENERAL",
        "WHITEGMC",
        "WHITE GMC",
        "GENERAL MOTORS CORP",
        "GMC (GENERAL MOTORS)",
    ),
    Make.GREAT_DANE: ("GDAN", "GREAT DANE"),
    Make.GRUMMAN: (
        "GRUM",
        "GRUMM",
        "GRUMAN",
        "GRUMIN",
        "GRUMANN",
        "GRUMMAN",
        "GRUMMAN MOTOR HOME",
    ),
    Make.HARLEY_DAVIDSON: (
        "HD",
        "HD/",
        "HARL",
        "HARLE",
        "HARLY",
        "HARL /",
        "HARLEY",
        "HARLEYD",
        "HARL DAV",
        "HARLEY D",
        "HARLEY-D",
        "HARLEY DAVIDSON",
        "HARLEY-DAVIDSON",
    ),
    Make.HINO: ("HINO", "HINO/"),
    Make.HONDA: (
        "HON",
        "HONA",
        "HOND",
        "HONE",
        "HONF",
        "HONG",
        "HONS",
        "H0NDA",
        "HANDA",
        "HIOND",
        "HODNA",
        "HONAD",
        "HOND/",
        "HONDA",
        "HONDS",
        "HONSA",
        "HIONDA",
        "HOINDA",
        "HOND /",
        "HONDA/",
        "HONDAS",
        "HONDAY",
        "HONDA`",
        "HONDA /",
        "ODYSSEY",
        "HONDA MC",
    ),
    Make.HUMMER: ("HUMM", "HUMME", "HUMMER", "HUMVEE"),
    Make.HYUNDAI: (
        "HUN",
        "HYN",
        "HYU",
        "HUYN",
        "HYND",
        "HYNU",
        "HYUD",
        "HYUM",
        "HYUN",
        "HYUU",
        "HYU N",
        "HYUAN",
        "HYUIN",
        "HYUN/",
        "HYUNA",
        "HYUND",
        "HYUUN",
        "HUNDAI",
        "HYNDAI",
        "HYUDAI",
        "HYUN /",
        "HYUNAI",
        "HYUNDA",
        "HYUNDI",
        "HUYNDAI",
        "HYNUDAI",
        "HYUNDAI",
        "HYUNDAU",
        "HYUNDAY",
        "HYUNDIA",
        "HYUANDAI",
        "HYUNDAI/",
    ),
    Make.HYUNDAI_TRANSLEAD: ("HYTR", "HYUNDAI TRANSLEAD"),
    Make.INFINITI: (
        "INF",
        "INFI",
        "INIF",
        "INFIN",
        "INFIT",
        "INIFI",
        "INFI /",
        "INFIN/",
        "INFINI",
        "INFINT",
        "INFINIT",
        "INFINTI",
        "INFINTY",
        "INFINITE",
        "INFINITI",
        "INFINITY",
        "INIFINIT",
        "INIFNITI",
    ),
    # INTL and INTE are International, the truck maker. switrs called this
    # 'international harvester', its pre-1986 name; one maker, one spelling.
    Make.INTERNATIONAL: (
        "INTE",
        "INTL",
        "INTER",
        "INTERNAT",
        "INTERNATIONAL",
        "INTERNATIONAL HARVESTER",
    ),
    Make.ISUZU: ("ISU", "ISUZ", "ISUZU"),
    Make.JAGUAR: ("JAG", "JAGA", "JAGU", "JAGUA", "JAGUAR"),
    Make.JEEP: ("JEE", "JEEF", "JEEO", "JEEP", "JEPP", "JEEEP", "JEEP/", "JEEP /"),
    Make.JOHN_DEERE: ("JOHN", "JDEER", "JOHND", "JOHN DEE", "JOHNDEER", "JOHN DEER", "JOHN DEERE"),
    Make.KAWASAKI: (
        "KAWA",
        "KAWI",
        "KAWK",
        "KAWAI",
        "KAWAK",
        "KAWAS",
        "KAWASA",
        "KAWASAK",
        "KAWASKI",
        "KAWASAKI",
    ),
    Make.KENWORTH: ("KW", "KENW", "KENWO", "KENWOR", "KENWORT", "KENWRTH", "KENWORTH"),
    Make.KIA: ("KIA", "KIO", "KIS", "KIA/", "KIAX", "KIA /"),
    Make.LAND_ROVER: (
        "LAND",
        "LNDR",
        "RANG",
        "LANDR",
        "RANGE",
        "RNGRV",
        "ROVER",
        "LANDRO",
        "LNDRVR",
        "RNGRVR",
        "LANDRVR",
        "LND RVR",
        "RNG RVR",
        "LAND RVR",
        "LANDROVE",
        "RANGE RO",
        "RANGE RV",
        "RANGEROV",
        "RNG ROVR",
        "LANDROVER",
        "LAND ROVER",
        "RANGE ROVER",
    ),
    Make.LEXUS: (
        "LES",
        "LEX",
        "LEZ",
        "LXS",
        "LESU",
        "LEXI",
        "LEXS",
        "LEXU",
        "LEXAS",
        "LEXIS",
        "LEXSS",
        "LEXUS",
        "LEXUX",
        "LEZUS",
        "LUXUS",
        "LEXS /",
        "LEXSUS",
        "LEXU /",
        "LEXUS/",
    ),
    Make.LINCOLN: (
        "LIN",
        "LINC",
        "LINCL",
        "LINCO",
        "LICOLN",
        "LINC /",
        "LINCOL",
        "LINCON",
        "LINCOLN",
        "LINCOLN/",
        "LINCOLN CONTINENTAL",
    ),
    Make.MACK: ("MACK",),
    Make.MASERATI: ("MASE", "MASI", "MASER", "MASERATI", "MASERATT", "MAZERATI"),
    Make.MAZDA: (
        "MAZ",
        "MZD",
        "MADA",
        "MAZA",
        "MAZD",
        "MZDA",
        "MADZA",
        "MAXDA",
        "MAZAD",
        "MAZDA",
        "MAZDZ",
        "MAZADA",
        "MAZD /",
        "MAZDA/",
        "MAZDA /",
        "MAZDA 3",
        "MAZDA 6",
    ),
    # MERZ (9,376) is Mercedes-Benz and MERC (366) is Mercury. The CCRS
    # frequencies settle a judgment call switrs-to-sqlite guessed at.
    Make.MERCEDES_BENZ: (
        "BENZ",
        "MERB",
        "MERD",
        "MERZ",
        "MERB.",
        "MERB/",
        "MERCE",
        "MERZ/",
        "MERZB",
        "MERB /",
        "MERBNZ",
        "MERCED",
        "MERZ /",
        "MERBENZ",
        "MERCEDE",
        "MERCEDS",
        "MERCEDES",
        "MERCEDEZ",
        "MERZ BNZ",
        "MERCEDES BENZ",
        "MERCEDES-BENZ",
    ),
    Make.MERCURY: ("MERC", "MERCU", "MERCUR", "MERCURY"),
    Make.MINI: ("MNI", "MINI", "MINN", "MNNI", "MINNI", "MNICP", "MINI COOPER"),
    Make.MITSUBISHI: (
        "MIT",
        "MIFU",
        "MIST",
        "MITI",
        "MITS",
        "MITT",
        "MITU",
        "MITZ",
        "MISTU",
        "MITS.",
        "MITS/",
        "MITSH",
        "MITSU",
        "MITTS",
        "MITS /",
        "MITSUB",
        "MITSUBI",
        "MITSUBIS",
        "MITSUBISHI",
    ),
    Make.NISSAN: (
        "NII",
        "NIS",
        "NIIS",
        "NISA",
        "NISS",
        "NIISS",
        "NISAA",
        "NISAN",
        "NISAS",
        "NISS/",
        "NISSA",
        "NISSI",
        "NISSN",
        "NISSS",
        "MISSAN",
        "NIISAN",
        "NISAAN",
        "NISS /",
        "NISSAM",
        "NISSAN",
        "NISSAS",
        "NISSNA",
        "NIISSAN",
        "NISSA N",
        "NISSAN/",
        "NISSANA",
        "NISSAN`",
        "NISSASN",
        "NISSIAN",
        "NISSSAN",
        "NISSAN /",
        "DATSUN/NISSAN",
    ),
    Make.OLDSMOBILE: ("OLS", "OLDS", "OLDSM", "OLDSMO", "OLDSMOBI", "OLDSMOBILE"),
    Make.PETERBILT: (
        "PTB",
        "PTE",
        "PTR",
        "PETE",
        "PETR",
        "PRTB",
        "PTBL",
        "PTBR",
        "PTBT",
        "PTER",
        "PTRB",
        "PETER",
        "PETKT",
        "PETRB",
        "PTBLT",
        "PTRB/",
        "PTRBL",
        "PTRBT",
        "PETERB",
        "PTRB /",
        "PTRBLT",
        "PETERBI",
        "PETERBL",
        "PETERBU",
        "PETRBLT",
        "PTRBILT",
        "PETEBILT",
        "PETERBIL",
        "PETERBLT",
        "PETERBUI",
        "PETERBUL",
        "PETRBILT",
        "PTRBUILT",
        "PETERBILT",
        "PETERBUILT",
    ),
    Make.PLYMOUTH: ("PLY", "PLYM", "PLYMO", "PLYMOU", "PLYMOTH", "VOYAGER", "PLYMOUTH"),
    Make.PONTIAC: (
        "PONI",
        "PONT",
        "PONIT",
        "PONTI",
        "PONTIA",
        "PONTIC",
        "PONITAC",
        "PONTAIC",
        "PONTIAC",
        "PONTIAC/",
    ),
    Make.PORSCHE: (
        "POR",
        "PORC",
        "PORS",
        "PORCH",
        "PORSC",
        "PORSE",
        "PORSH",
        "PORCHE",
        "PORSCE",
        "PORSCH",
        "PORSHE",
        "PORSCHE",
        "PORSCHE/",
    ),
    Make.RAD_POWER_BIKES: (
        "RAD",
        "RAD CITY",
        "RAD POWE",
        "RADPOWER",
        "RADROVER",
        "RAD POWER BIKES",
    ),
    Make.RAM: ("RAM", "RAN", "RAM/", "RAM 2500"),
    Make.SAAB: ("SAAB",),
    Make.SATURN: (
        "SATN",
        "SATR",
        "SATU",
        "SATY",
        "STRN",
        "SATRN",
        "SATRU",
        "SATUN",
        "SATUR",
        "STURN",
        "SATRUN",
        "SATURN",
        "STRN /",
        "SATURN/",
    ),
    Make.SCHWINN: ("SCHW", "SHWIN", "SCHWIN", "SCWINN", "SHWINN", "SCHWINN", "SCHWYNN", "SCWHINN"),
    Make.SCION: ("SCIO", "SCION", "SCOIN", "SCIOIN"),
    Make.SMART: ("SMAR", "SMART"),
    Make.STERLING: ("STERLI", "STERLIN", "STERLING"),
    Make.SUBARU: (
        "SUB",
        "SUBA",
        "SUBI",
        "SUBN",
        "SUBR",
        "SUBU",
        "SUBAR",
        "SUBRA",
        "SUBRU",
        "SUBUR",
        "SUBA /",
        "SUBARA",
        "SUBARI",
        "SUBARU",
        "SUBARY",
        "SUBRAU",
        "SUBURA",
        "SUBURU",
        "SUBARAU",
        "SUBARU/",
        "SUBRARU",
        "SUBUARU",
    ),
    Make.SUZUKI: (
        "SUS",
        "SUZ",
        "SUZI",
        "SUZK",
        "SUZU",
        "SUZKI",
        "SUZUK",
        "SUSUKI",
        "SUZIKI",
        "SUZU /",
        "SUZUKI",
        "SUZUKI/",
        "SUZUKI MC",
    ),
    Make.TAOTAO: ("TAOTA", "TAOTAO"),
    # TSMR is the NCIC code for Tesla Motors.
    Make.TESLA: ("TESL", "TSLA", "TSMR", "TESLA", "TESLA/", "TESLA MOTORS"),
    Make.THOMAS: ("THOB", "THOM", "THOMA", "THOMAS", "THOMAS B", "THOMAS (BUS)"),
    # TOYO (498,501) is the single largest string in the dataset. The
    # earlier years spell it that way; 2025 uses the NCIC code TOYT.
    Make.TOYOTA: (
        "T0Y",
        "TOT",
        "TOY",
        "TOTA",
        "TOTO",
        "TOTY",
        "TOY0",
        "TOYA",
        "TOYI",
        "TOYO",
        "TOYR",
        "TOYT",
        "TOYY",
        "TYOT",
        "PRIUS",
        "TOYAT",
        "TOYO/",
        "TOYOA",
        "TOYOT",
        "TOYOY",
        "TOYO`",
        "TOYT.",
        "TOYT/",
        "TOYTA",
        "TOYTO",
        "TOYTT",
        "TYOTA",
        "T0YOTA",
        "TOTOTA",
        "TOTOYA",
        "TOTYOA",
        "TOY0TA",
        "TOYATA",
        "TOYO /",
        "TOYOAT",
        "TOYORA",
        "TOYOTA",
        "TOYOTO",
        "TOYOTR",
        "TOYOTS",
        "TOYOYA",
        "TOYT /",
        "TOYTOA",
        "TUNDRA",
        "TOTOYTA",
        "TOTYOTA",
        "TOYOTA/",
        "TOYOTAS",
        "TOYOTA`",
        "TOYOTOA",
        "TOYOTRA",
        "TOYOTYA",
        "TOYOYTA",
        "TOYTOTA",
        "TOY/SCIO",
        "TOYO/SCI",
        "TOYT/SCI",
    ),
    Make.TREK: ("TREC", "TREK", "TRECK", "TREK, INC."),
    Make.TRIUMPH: ("TRIU", "TRUM", "TRIPH", "TRIUM", "TRIUMP", "TRIUPH", "TRIUMPH", "TRUIMPH"),
    # Utility Trailer Manufacturing, which is why it outranks most cars.
    Make.UTILITY: ("UTIL", "UTILITY"),
    Make.VESPA: ("VESP", "VESPA"),
    Make.VOLKSWAGEN: (
        "VW",
        "V W",
        "V/W",
        "VOK",
        "V.W.",
        "VOKS",
        "VOLK",
        "VOLS",
        "VOLW",
        "VOLX",
        "V & W",
        "VOLK/",
        "VOLKD",
        "VOLKL",
        "VOLKS",
        "VOLKW",
        "VOLLK",
        "VOLK /",
        "VOLKS/",
        "VOLKSW",
        "VOLKS`",
        "VOLKWA",
        "VOLLKS",
        "VOLKSWA",
        "VOLKWGN",
        "VOLSWGN",
        "VOLKSWAG",
        "VOLKSWGN",
        "VOLKWAGE",
        "VOLSWAGE",
        "VOLKSWAGEN",
        "VOLKSWAGON",
    ),
    Make.VOLVO: (
        "VOLO",
        "VOLV",
        "VOVL",
        "VOVO",
        "VOLCO",
        "VOLOV",
        "VOLV0",
        "VOLVA",
        "VOLVE",
        "VOLVL",
        "VOLVO",
        "VOVLO",
        "VOLOVO",
        "VOLV /",
        "VOLVO/",
        "VOVLVO",
        "WHITE VOLVO",
    ),
    Make.WABASH: ("WABA", "WABASH"),
    Make.WHITE: ("WHITE",),
    Make.WINNEBAGO: ("WINN", "WNBG", "WINNE", "WINNI", "WNBGO", "WINNEBAG", "WINNEBAGO"),
    Make.YAMAHA: (
        "YAH",
        "YAM",
        "YAHA",
        "YAMA",
        "YAMH",
        "YAHMA",
        "YAMAH",
        "YAHAMA",
        "YAMAHA",
        "YAMAMA",
    ),
}

MAKE_MAP: Mapping[str, Make] = {
    raw_string: make
    for make, raw_strings in RAW_STRINGS_BY_MAKE.items()
    for raw_string in raw_strings
}


def normalize_make(raw_string: str | None) -> str | None:
    """Return the normalized maker name for a source make string.

    None for an empty cell, and None for anything the map does not cover.
    """
    if raw_string is None:
        return None

    return MAKE_MAP.get(raw_string.strip().upper())
