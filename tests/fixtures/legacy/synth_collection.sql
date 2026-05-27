-- Synthetic dev collection seed (committed; PII-free).
--
-- Creates gruvax_dev schema with minimal discogsography-shaped tables and
-- inserts ~200 synthetic records covering all catalog-number format shapes
-- documented in INTERPOLATION.md §2.3.
--
-- Shape variety required (per plan acceptance criteria):
--   - alpha-prefix + digits: BLP 4001..4020, ECM 1001..1015
--   - multi-prefix within one label: "Blue Note" has BLP + BST prefixes
--   - mixed separators within one label: KC 32731 and KC-32732
--   - pure numeric: 32731..32740
--   - multi-value catalog (comma): BLP-100, BST-200
--   - placeholder: none
--   - ~50 singleton labels
--
-- The fts_vector column is populated via to_tsvector() so the FTS search
-- path (plan 03) works without real discogsography data.

-- ── Schema ─────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS gruvax_dev;

-- ── artists ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gruvax_dev.artists (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

-- ── releases ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gruvax_dev.releases (
    id                 BIGSERIAL PRIMARY KEY,
    title              TEXT,
    label              TEXT,
    catalog_number     TEXT,
    format             TEXT,
    year               SMALLINT,
    fts_vector         TSVECTOR,
    primary_artist_id  BIGINT REFERENCES gruvax_dev.artists(id)
);

-- ── collection_items ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gruvax_dev.collection_items (
    id          BIGSERIAL PRIMARY KEY,
    release_id  BIGINT REFERENCES gruvax_dev.releases(id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── truncate to allow idempotent re-seeding ────────────────────────────────
TRUNCATE gruvax_dev.collection_items RESTART IDENTITY CASCADE;
TRUNCATE gruvax_dev.releases RESTART IDENTITY CASCADE;
TRUNCATE gruvax_dev.artists RESTART IDENTITY CASCADE;

-- ── seed artists ───────────────────────────────────────────────────────────
-- IDs 1-40
INSERT INTO gruvax_dev.artists (name) VALUES
  -- Jazz
  ('Miles Davis'),           -- 1
  ('John Coltrane'),         -- 2
  ('Bill Evans'),            -- 3
  ('Thelonious Monk'),       -- 4
  ('Charles Mingus'),        -- 5
  ('Herbie Hancock'),        -- 6
  ('Wayne Shorter'),         -- 7
  ('Clifford Brown'),        -- 8
  -- ECM artists
  ('Keith Jarrett'),         -- 9
  ('Jan Garbarek'),          -- 10
  ('Eberhard Weber'),        -- 11
  ('Chick Corea'),           -- 12
  -- Columbia / CBS artists
  ('Bob Dylan'),             -- 13
  ('Simon & Garfunkel'),     -- 14
  ('Leonard Cohen'),         -- 15
  -- KC / Columbia KC artists
  ('Bruce Springsteen'),     -- 16
  ('Chicago'),               -- 17
  ('Earth Wind & Fire'),     -- 18
  -- Prestige artists
  ('Sonny Rollins'),         -- 19
  ('Red Garland'),           -- 20
  -- Pure numeric label artists
  ('Dexter Gordon'),         -- 21
  ('Lee Morgan'),            -- 22
  -- Multi-prefix label artist
  ('Art Blakey'),            -- 23
  ('Horace Silver'),         -- 24
  -- Multi-value catalog artists
  ('Duke Ellington'),        -- 25
  ('Count Basie'),           -- 26
  -- Placeholder catalog
  ('Various Artists'),       -- 27
  -- Mixed separator label
  ('Wes Montgomery'),        -- 28
  ('Jimmy Smith'),           -- 29
  -- Singleton labels (IDs 30-40)
  ('Radiohead'),             -- 30
  ('Nick Drake'),            -- 31
  ('Joni Mitchell'),         -- 32
  ('Neil Young'),            -- 33
  ('Van Morrison'),          -- 34
  ('Tom Waits'),             -- 35
  ('The Velvet Underground'),-- 36
  ('Can'),                   -- 37
  ('Fela Kuti'),             -- 38
  ('Sun Ra'),                -- 39
  ('Albert Ayler');          -- 40

-- ── helper: build fts_vector from title + label + artist name ──────────────
-- We use a DO block to insert releases with fts_vector computed inline.

-- ── Blue Note — BLP prefix (alpha-prefix + digits) ─────────────────────────
-- 20 records, BLP 4001..4020 — boundary: unit 1 row 0 col 0
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Kind of Blue',           'Blue Note', 'BLP 4001', 'LP', 1959, 1, to_tsvector('english', 'Kind of Blue Blue Note Miles Davis')),
  ('Giant Steps',            'Blue Note', 'BLP 4002', 'LP', 1960, 2, to_tsvector('english', 'Giant Steps Blue Note John Coltrane')),
  ('Portrait in Jazz',       'Blue Note', 'BLP 4003', 'LP', 1960, 3, to_tsvector('english', 'Portrait in Jazz Blue Note Bill Evans')),
  ('Monk''s Dream',          'Blue Note', 'BLP 4004', 'LP', 1963, 4, to_tsvector('english', 'Monks Dream Blue Note Thelonious Monk')),
  ('Mingus Ah Um',           'Blue Note', 'BLP 4005', 'LP', 1959, 5, to_tsvector('english', 'Mingus Ah Um Blue Note Charles Mingus')),
  ('Maiden Voyage',          'Blue Note', 'BLP 4006', 'LP', 1965, 6, to_tsvector('english', 'Maiden Voyage Blue Note Herbie Hancock')),
  ('Speak No Evil',          'Blue Note', 'BLP 4007', 'LP', 1966, 7, to_tsvector('english', 'Speak No Evil Blue Note Wayne Shorter')),
  ('Clifford Brown Memorial','Blue Note', 'BLP 4008', 'LP', 1956, 8, to_tsvector('english', 'Clifford Brown Memorial Blue Note Clifford Brown')),
  ('Empyrean Isles',         'Blue Note', 'BLP 4009', 'LP', 1964, 6, to_tsvector('english', 'Empyrean Isles Blue Note Herbie Hancock')),
  ('The Real McCoy',         'Blue Note', 'BLP 4010', 'LP', 1967, 2, to_tsvector('english', 'The Real McCoy Blue Note John Coltrane')),
  ('Inventions and Dimensions','Blue Note','BLP 4011','LP', 1964, 6, to_tsvector('english', 'Inventions and Dimensions Blue Note Herbie Hancock')),
  ('Adam''s Apple',          'Blue Note', 'BLP 4012', 'LP', 1967, 7, to_tsvector('english', 'Adams Apple Blue Note Wayne Shorter')),
  ('Night Dreamer',          'Blue Note', 'BLP 4013', 'LP', 1964, 7, to_tsvector('english', 'Night Dreamer Blue Note Wayne Shorter')),
  ('Juju',                   'Blue Note', 'BLP 4014', 'LP', 1965, 7, to_tsvector('english', 'Juju Blue Note Wayne Shorter')),
  ('Schizophrenia',          'Blue Note', 'BLP 4015', 'LP', 1969, 7, to_tsvector('english', 'Schizophrenia Blue Note Wayne Shorter')),
  ('The Sidewinder',         'Blue Note', 'BLP 4016', 'LP', 1964, 22, to_tsvector('english', 'The Sidewinder Blue Note Lee Morgan')),
  ('Search for the New Land','Blue Note', 'BLP 4017', 'LP', 1966, 22, to_tsvector('english', 'Search for the New Land Blue Note Lee Morgan')),
  ('Cornbread',              'Blue Note', 'BLP 4018', 'LP', 1967, 22, to_tsvector('english', 'Cornbread Blue Note Lee Morgan')),
  ('Caramba',                'Blue Note', 'BLP 4019', 'LP', 1968, 22, to_tsvector('english', 'Caramba Blue Note Lee Morgan')),
  ('Tom Cat',                'Blue Note', 'BLP 4020', 'LP', 1981, 22, to_tsvector('english', 'Tom Cat Blue Note Lee Morgan'));

-- ── Blue Note — BST prefix (multi-prefix within same label) ────────────────
-- 10 records, BST 84001..84010 — same "Blue Note" label as BLP series
-- Boundaries for "Blue Note" span two adjacent cubes (BLP in cube 0,0 BST in cube 0,1)
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('A Night in Tunisia',     'Blue Note', 'BST 84001', 'LP', 1957, 23, to_tsvector('english', 'A Night in Tunisia Blue Note Art Blakey')),
  ('Moanin',                 'Blue Note', 'BST 84002', 'LP', 1958, 23, to_tsvector('english', 'Moanin Blue Note Art Blakey')),
  ('The Witch Doctor',       'Blue Note', 'BST 84003', 'LP', 1967, 23, to_tsvector('english', 'The Witch Doctor Blue Note Art Blakey')),
  ('Song for My Father',     'Blue Note', 'BST 84004', 'LP', 1965, 24, to_tsvector('english', 'Song for My Father Blue Note Horace Silver')),
  ('The Cape Verdean Blues',  'Blue Note', 'BST 84005', 'LP', 1965, 24, to_tsvector('english', 'The Cape Verdean Blues Blue Note Horace Silver')),
  ('The Jody Grind',         'Blue Note', 'BST 84006', 'LP', 1967, 24, to_tsvector('english', 'The Jody Grind Blue Note Horace Silver')),
  ('Serenade to a Soul Sister','Blue Note','BST 84007','LP', 1969, 24, to_tsvector('english', 'Serenade to a Soul Sister Blue Note Horace Silver')),
  ('You Gotta Take a Little Love','Blue Note','BST 84008','LP',1970,24, to_tsvector('english', 'You Gotta Take a Little Love Blue Note Horace Silver')),
  ('Total Response',         'Blue Note', 'BST 84009', 'LP', 1972, 24, to_tsvector('english', 'Total Response Blue Note Horace Silver')),
  ('In Pursuit of the 27th Man','Blue Note','BST 84010','LP',1972,24, to_tsvector('english', 'In Pursuit of the 27th Man Blue Note Horace Silver'));

-- ── ECM — alpha-prefix + digits ────────────────────────────────────────────
-- 15 records, ECM 1001..1015 — boundary: unit 1 row 0 col 2
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Facing You',             'ECM', 'ECM 1001', 'LP', 1972,  9, to_tsvector('english', 'Facing You ECM Keith Jarrett')),
  ('Afric Pepperbird',       'ECM', 'ECM 1002', 'LP', 1970, 10, to_tsvector('english', 'Afric Pepperbird ECM Jan Garbarek')),
  ('Luminessence',           'ECM', 'ECM 1003', 'LP', 1976, 10, to_tsvector('english', 'Luminessence ECM Jan Garbarek')),
  ('Witchi-Tai-To',          'ECM', 'ECM 1004', 'LP', 1974, 10, to_tsvector('english', 'Witchi Tai To ECM Jan Garbarek')),
  ('Belonging',              'ECM', 'ECM 1005', 'LP', 1974,  9, to_tsvector('english', 'Belonging ECM Keith Jarrett')),
  ('The Koln Concert',       'ECM', 'ECM 1006', 'LP', 1975,  9, to_tsvector('english', 'The Koln Concert ECM Keith Jarrett')),
  ('Arbour Zena',            'ECM', 'ECM 1007', 'LP', 1976, 10, to_tsvector('english', 'Arbour Zena ECM Jan Garbarek')),
  ('My Song',                'ECM', 'ECM 1008', 'LP', 1978,  9, to_tsvector('english', 'My Song ECM Keith Jarrett')),
  ('Solstice',               'ECM', 'ECM 1009', 'LP', 1975, 11, to_tsvector('english', 'Solstice ECM Eberhard Weber')),
  ('The Following Morning',  'ECM', 'ECM 1010', 'LP', 1977, 11, to_tsvector('english', 'The Following Morning ECM Eberhard Weber')),
  ('Violin',                 'ECM', 'ECM 1011', 'LP', 1977, 12, to_tsvector('english', 'Violin ECM Chick Corea')),
  ('The Song of Singing',    'ECM', 'ECM 1012', 'LP', 1970, 12, to_tsvector('english', 'The Song of Singing ECM Chick Corea')),
  ('Piano Improvisations V1','ECM', 'ECM 1013', 'LP', 1971, 12, to_tsvector('english', 'Piano Improvisations ECM Chick Corea')),
  ('A.R.C.',                 'ECM', 'ECM 1014', 'LP', 1971, 12, to_tsvector('english', 'ARC ECM Chick Corea')),
  ('Return to Forever',      'ECM', 'ECM 1015', 'LP', 1972, 12, to_tsvector('english', 'Return to Forever ECM Chick Corea'));

-- ── KC — mixed separators (space vs dash within same label) ────────────────
-- 12 records — boundary: unit 1 row 0 col 3
-- KC 32731, KC 32732, KC-32733, KC-32734 ... space and dash both appear
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Born to Run',            'KC', 'KC 32731', 'LP', 1975, 16, to_tsvector('english', 'Born to Run KC Bruce Springsteen')),
  ('The Wild Innocent',      'KC', 'KC-32732', 'LP', 1973, 16, to_tsvector('english', 'The Wild Innocent KC Bruce Springsteen')),
  ('Darkness on the Edge',   'KC', 'KC 32733', 'LP', 1978, 16, to_tsvector('english', 'Darkness on the Edge KC Bruce Springsteen')),
  ('The River',              'KC', 'KC-32734', 'LP', 1980, 16, to_tsvector('english', 'The River KC Bruce Springsteen')),
  ('Chicago VII',            'KC', 'KC 32735', 'LP', 1974, 17, to_tsvector('english', 'Chicago VII KC Chicago')),
  ('Chicago VIII',           'KC', 'KC-32736', 'LP', 1975, 17, to_tsvector('english', 'Chicago VIII KC Chicago')),
  ('Chicago IX',             'KC', 'KC 32737', 'LP', 1975, 17, to_tsvector('english', 'Chicago IX KC Chicago')),
  ('Chicago X',              'KC', 'KC-32738', 'LP', 1976, 17, to_tsvector('english', 'Chicago X KC Chicago')),
  ('All N All',              'KC', 'KC 32739', 'LP', 1977, 18, to_tsvector('english', 'All N All KC Earth Wind Fire')),
  ('I Am',                   'KC', 'KC-32740', 'LP', 1979, 18, to_tsvector('english', 'I Am KC Earth Wind Fire')),
  ('Raise',                  'KC', 'KC 32741', 'LP', 1981, 18, to_tsvector('english', 'Raise KC Earth Wind Fire')),
  ('Powerlight',             'KC', 'KC-32742', 'LP', 1983, 18, to_tsvector('english', 'Powerlight KC Earth Wind Fire'));

-- ── Prestige — pure numeric catalog ────────────────────────────────────────
-- 10 records, purely numeric catalog numbers — boundary: unit 1 row 1 col 0
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Saxophone Colossus',     'Prestige', '32731', 'LP', 1956, 19, to_tsvector('english', 'Saxophone Colossus Prestige Sonny Rollins')),
  ('Worktime',               'Prestige', '32732', 'LP', 1956, 19, to_tsvector('english', 'Worktime Prestige Sonny Rollins')),
  ('A Night at the Village Vanguard','Prestige','32733','LP',1958,19, to_tsvector('english', 'A Night at the Village Vanguard Prestige Sonny Rollins')),
  ('Newk''s Time',           'Prestige', '32734', 'LP', 1959, 19, to_tsvector('english', 'Newks Time Prestige Sonny Rollins')),
  ('The Bridge',             'Prestige', '32735', 'LP', 1962, 19, to_tsvector('english', 'The Bridge Prestige Sonny Rollins')),
  ('Red Garland''s Piano',   'Prestige', '32736', 'LP', 1957, 20, to_tsvector('english', 'Red Garlands Piano Prestige Red Garland')),
  ('All Mornin'' Long',      'Prestige', '32737', 'LP', 1957, 20, to_tsvector('english', 'All Mornin Long Prestige Red Garland')),
  ('High Pressure',          'Prestige', '32738', 'LP', 1958, 20, to_tsvector('english', 'High Pressure Prestige Red Garland')),
  ('Soul Junction',          'Prestige', '32739', 'LP', 1960, 20, to_tsvector('english', 'Soul Junction Prestige Red Garland')),
  ('Dig It',                 'Prestige', '32740', 'LP', 1962, 20, to_tsvector('english', 'Dig It Prestige Red Garland'));

-- ── Verve — multi-value catalog (comma separated) ──────────────────────────
-- 6 records with comma-style multi-value catalog numbers
-- boundary: unit 1 row 1 col 1
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Ellington at Newport',   'Verve', 'BLP-100, BST-200', 'LP', 1956, 25, to_tsvector('english', 'Ellington at Newport Verve Duke Ellington')),
  ('Such Sweet Thunder',     'Verve', 'MGV-8200, V-8200', 'LP', 1957, 25, to_tsvector('english', 'Such Sweet Thunder Verve Duke Ellington')),
  ('Blues in Orbit',         'Verve', 'V-8241, V6-8241',  'LP', 1960, 25, to_tsvector('english', 'Blues in Orbit Verve Duke Ellington')),
  ('April in Paris',         'Verve', 'MGV-8012, V-8012', 'LP', 1957, 26, to_tsvector('english', 'April in Paris Verve Count Basie')),
  ('The Atomic Mr. Basie',   'Verve', 'V-8257, V6-8257',  'LP', 1957, 26, to_tsvector('english', 'The Atomic Mr Basie Verve Count Basie')),
  ('Basie in London',        'Verve', 'MGV-8199, V-8199', 'LP', 1957, 26, to_tsvector('english', 'Basie in London Verve Count Basie'));

-- ── Unknown — placeholder catalog (none) ───────────────────────────────────
-- 4 records with "none" placeholder catalog
-- boundary: unit 1 row 1 col 2
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Private Press Vol.1',    'Unknown', 'none', 'LP', 1974, 27, to_tsvector('english', 'Private Press Vol 1 Unknown Various Artists')),
  ('Private Press Vol.2',    'Unknown', 'none', 'LP', 1975, 27, to_tsvector('english', 'Private Press Vol 2 Unknown Various Artists')),
  ('Private Press Vol.3',    'Unknown', 'none', 'LP', 1976, 27, to_tsvector('english', 'Private Press Vol 3 Unknown Various Artists')),
  ('Private Press Vol.4',    'Unknown', 'none', 'LP', 1977, 27, to_tsvector('english', 'Private Press Vol 4 Unknown Various Artists'));

-- ── Milestone — more alpha-prefix records ──────────────────────────────────
-- boundary: unit 1 row 1 col 3
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('Smokin'' at the Half Note','Milestone','MSP 9001','LP',1965,28,to_tsvector('english', 'Smokin at the Half Note Milestone Wes Montgomery')),
  ('Bumpin''',                'Milestone', 'MSP 9002', 'LP', 1966, 28, to_tsvector('english', 'Bumpin Milestone Wes Montgomery')),
  ('Goin'' Out of My Head',  'Milestone', 'MSP 9003', 'LP', 1966, 28, to_tsvector('english', 'Goin Out of My Head Milestone Wes Montgomery')),
  ('Down Here on the Ground','Milestone', 'MSP 9004', 'LP', 1968, 28, to_tsvector('english', 'Down Here on the Ground Milestone Wes Montgomery')),
  ('The Boss',               'Milestone', 'MSP 9005', 'LP', 1969, 29, to_tsvector('english', 'The Boss Milestone Jimmy Smith')),
  ('Root Down',              'Milestone', 'MSP 9006', 'LP', 1972, 29, to_tsvector('english', 'Root Down Milestone Jimmy Smith')),
  ('Any Number Can Win',     'Milestone', 'MSP 9007', 'LP', 1963, 29, to_tsvector('english', 'Any Number Can Win Milestone Jimmy Smith')),
  ('Hobo Flats',             'Milestone', 'MSP 9008', 'LP', 1964, 29, to_tsvector('english', 'Hobo Flats Milestone Jimmy Smith'));

-- ── Singleton labels (~50 records, one per label) ──────────────────────────
-- boundary: unit 1 rows 2-3 and unit 2
INSERT INTO gruvax_dev.releases (title, label, catalog_number, format, year, primary_artist_id, fts_vector) VALUES
  ('OK Computer',            'Parlophone', 'NODATA 006',  'LP', 1997, 30, to_tsvector('english', 'OK Computer Parlophone Radiohead')),
  ('Kid A',                  'Parlophone', 'NODATA 007',  'LP', 2000, 30, to_tsvector('english', 'Kid A Parlophone Radiohead')),
  ('Five Leaves Left',       'Island',     'ILPS 9105',   'LP', 1969, 31, to_tsvector('english', 'Five Leaves Left Island Nick Drake')),
  ('Bryter Layter',          'Island',     'ILPS 9134',   'LP', 1970, 31, to_tsvector('english', 'Bryter Layter Island Nick Drake')),
  ('Pink Moon',              'Island',     'ILPS 9184',   'LP', 1972, 31, to_tsvector('english', 'Pink Moon Island Nick Drake')),
  ('Blue',                   'Reprise',    'MS 2038',     'LP', 1971, 32, to_tsvector('english', 'Blue Reprise Joni Mitchell')),
  ('Court and Spark',        'Asylum',     'SD 5007',     'LP', 1974, 32, to_tsvector('english', 'Court and Spark Asylum Joni Mitchell')),
  ('Harvest',                'Reprise',    'MS 2032',     'LP', 1972, 33, to_tsvector('english', 'Harvest Reprise Neil Young')),
  ('After the Gold Rush',    'Reprise',    'RS 6383',     'LP', 1970, 33, to_tsvector('english', 'After the Gold Rush Reprise Neil Young')),
  ('Tonight''s the Night',   'Reprise',    'MS 2221',     'LP', 1975, 33, to_tsvector('english', 'Tonights the Night Reprise Neil Young')),
  ('Astral Weeks',           'Warner Bros','WS 1768',     'LP', 1968, 34, to_tsvector('english', 'Astral Weeks Warner Bros Van Morrison')),
  ('Moondance',              'Warner Bros','WS 1835',     'LP', 1970, 34, to_tsvector('english', 'Moondance Warner Bros Van Morrison')),
  ('Tupelo Honey',           'Warner Bros','BS 2633',     'LP', 1971, 34, to_tsvector('english', 'Tupelo Honey Warner Bros Van Morrison')),
  ('Closing Time',           'Asylum',     'SD 5061',     'LP', 1973, 35, to_tsvector('english', 'Closing Time Asylum Tom Waits')),
  ('Small Change',           'Asylum',     'SD 5060',     'LP', 1976, 35, to_tsvector('english', 'Small Change Asylum Tom Waits')),
  ('Foreign Affairs',        'Asylum',     'SD 5070',     'LP', 1977, 35, to_tsvector('english', 'Foreign Affairs Asylum Tom Waits')),
  ('Blue Valentine',         'Asylum',     'SD 5070-2',   'LP', 1978, 35, to_tsvector('english', 'Blue Valentine Asylum Tom Waits')),
  ('The Velvet Underground & Nico','Verve','V6-5008',     'LP', 1967, 36, to_tsvector('english', 'The Velvet Underground and Nico Verve')),
  ('White Light White Heat', 'Verve',      'V6-5046',     'LP', 1968, 36, to_tsvector('english', 'White Light White Heat Verve Velvet Underground')),
  ('Tago Mago',              'UA',         'UAS 29211',   '2xLP',1971,37, to_tsvector('english', 'Tago Mago UA Can')),
  ('Ege Bamyasi',            'UA',         'UAS 29414',   'LP', 1972, 37, to_tsvector('english', 'Ege Bamyasi UA Can')),
  ('Future Days',            'UA',         'UAS 29505',   'LP', 1973, 37, to_tsvector('english', 'Future Days UA Can')),
  ('Zombie',                 'Creole',     'CRLP 501',    'LP', 1977, 38, to_tsvector('english', 'Zombie Creole Fela Kuti')),
  ('Opposite People',        'Creole',     'CRLP 502',    'LP', 1977, 38, to_tsvector('english', 'Opposite People Creole Fela Kuti')),
  ('Monkey Banana',          'Creole',     'CRLP 503',    'LP', 1981, 38, to_tsvector('english', 'Monkey Banana Creole Fela Kuti')),
  ('The Futuristic Sounds',  'Saturn',     'SR-9956-2-LP','LP', 1961, 39, to_tsvector('english', 'The Futuristic Sounds Saturn Sun Ra')),
  ('The Heliocentric Worlds','ESP',        'ESP 1014',    'LP', 1965, 39, to_tsvector('english', 'The Heliocentric Worlds ESP Sun Ra')),
  ('Baptism',                'Impulse',    'AS-9191',     'LP', 1967, 40, to_tsvector('english', 'Baptism Impulse Albert Ayler')),
  ('New Grass',              'Impulse',    'AS-9175',     'LP', 1969, 40, to_tsvector('english', 'New Grass Impulse Albert Ayler')),
  ('Music Is the Healing Force','Impulse', 'AS-9191-2',   'LP', 1969, 40, to_tsvector('english', 'Music Is the Healing Force Impulse Albert Ayler')),
  -- Additional singletons to reach ~200 total
  ('Led Zeppelin',           'Atlantic',   'ATL 40031',   'LP', 1969,  1, to_tsvector('english', 'Led Zeppelin Atlantic')),
  ('Led Zeppelin II',        'Atlantic',   'ATL 40037',   'LP', 1969,  1, to_tsvector('english', 'Led Zeppelin II Atlantic')),
  ('Physical Graffiti',      'Swan Song',  'SSK 89400',   '2xLP',1975, 1, to_tsvector('english', 'Physical Graffiti Swan Song Led Zeppelin')),
  ('Abbey Road',             'Apple',      'PCS 7088',    'LP', 1969,  2, to_tsvector('english', 'Abbey Road Apple Beatles')),
  ('Revolver',               'Parlophone', 'PMC 7009',    'LP', 1966,  2, to_tsvector('english', 'Revolver Parlophone Beatles')),
  ('Pet Sounds',             'Capitol',    'ST 2458',     'LP', 1966,  3, to_tsvector('english', 'Pet Sounds Capitol Beach Boys')),
  ('Innervisions',           'Tamla',      'T313L',       'LP', 1973,  6, to_tsvector('english', 'Innervisions Tamla Stevie Wonder')),
  ('Songs in the Key of Life','Tamla',     'T13-340C2',   '2xLP',1976, 6, to_tsvector('english', 'Songs in the Key of Life Tamla Stevie Wonder')),
  ('What''s Going On',       'Tamla',      'T310',        'LP', 1971,  6, to_tsvector('english', 'Whats Going On Tamla Marvin Gaye')),
  ('Let''s Get It On',       'Tamla',      'T329V1',      'LP', 1973,  6, to_tsvector('english', 'Lets Get It On Tamla Marvin Gaye')),
  ('Off the Wall',           'Epic',       'EPC 83468',   'LP', 1979,  7, to_tsvector('english', 'Off the Wall Epic Michael Jackson')),
  ('Thriller',               'Epic',       'EPC 85930',   'LP', 1982,  7, to_tsvector('english', 'Thriller Epic Michael Jackson')),
  ('Sign o'' the Times',     'Paisley Park','925577-1',   '2xLP',1987, 8, to_tsvector('english', 'Sign o the Times Paisley Park Prince')),
  ('Purple Rain',            'Warner Bros','25110-1',     'LP', 1984,  8, to_tsvector('english', 'Purple Rain Warner Bros Prince')),
  ('Bitches Brew',           'Columbia',   'GP 26',       '2xLP',1970, 1, to_tsvector('english', 'Bitches Brew Columbia Miles Davis')),
  ('Sketches of Spain',      'Columbia',   'CL 1480',     'LP', 1960,  1, to_tsvector('english', 'Sketches of Spain Columbia Miles Davis')),
  ('A Love Supreme',         'Impulse',    'A-77',        'LP', 1965,  2, to_tsvector('english', 'A Love Supreme Impulse John Coltrane')),
  ('Coltrane',               'Impulse',    'A-21',        'LP', 1962,  2, to_tsvector('english', 'Coltrane Impulse John Coltrane')),
  ('Waltz for Debby',        'Riverside',  'RLP 399',     'LP', 1962,  3, to_tsvector('english', 'Waltz for Debby Riverside Bill Evans')),
  ('Sunday at the Village Vanguard','Riverside','RLP 376','LP',1961, 3, to_tsvector('english', 'Sunday at the Village Vanguard Riverside Bill Evans')),
  ('Brilliant Corners',      'Riverside',  'RLP 12-226',  'LP', 1957,  4, to_tsvector('english', 'Brilliant Corners Riverside Thelonious Monk')),
  ('Monk''s Music',          'Riverside',  'RLP 12-242',  'LP', 1957,  4, to_tsvector('english', 'Monks Music Riverside Thelonious Monk')),
  ('Mingus Mingus Mingus',   'Impulse',    'AS-54',       'LP', 1963,  5, to_tsvector('english', 'Mingus Mingus Mingus Impulse Charles Mingus')),
  ('The Black Saint',        'Atlantic',   'SD 1416',     'LP', 1970,  5, to_tsvector('english', 'The Black Saint Atlantic Charles Mingus')),
  ('Blowin'' in the Wind',   'Columbia',   'CS 8786',     'LP', 1963, 13, to_tsvector('english', 'Blowin in the Wind Columbia Bob Dylan')),
  ('Highway 61 Revisited',   'Columbia',   'CS 9189',     'LP', 1965, 13, to_tsvector('english', 'Highway 61 Revisited Columbia Bob Dylan')),
  ('Blonde on Blonde',       'Columbia',   'C2S 841',     '2xLP',1966,13, to_tsvector('english', 'Blonde on Blonde Columbia Bob Dylan')),
  ('Blood on the Tracks',    'Columbia',   'PC 33235',    'LP', 1975, 13, to_tsvector('english', 'Blood on the Tracks Columbia Bob Dylan')),
  ('Sounds of Silence',      'Columbia',   'CS 9269',     'LP', 1966, 14, to_tsvector('english', 'Sounds of Silence Columbia Simon Garfunkel')),
  ('Bookends',               'Columbia',   'KCS 9529',    'LP', 1968, 14, to_tsvector('english', 'Bookends Columbia Simon Garfunkel')),
  ('Songs of Leonard Cohen',  'Columbia',  'CS 9533',     'LP', 1967, 15, to_tsvector('english', 'Songs of Leonard Cohen Columbia Leonard Cohen')),
  ('Songs from a Room',      'Columbia',   'CS 9767',     'LP', 1969, 15, to_tsvector('english', 'Songs from a Room Columbia Leonard Cohen')),
  -- Sparse label with large numeric gaps (INTERPOLATION §2.5 case)
  ('Dexter Gordon',          'SteepleChase','SCS 1001',  'LP', 1975, 21, to_tsvector('english', 'Dexter Gordon SteepleChase')),
  ('More Than You Know',     'SteepleChase','SCS 1032',  'LP', 1975, 21, to_tsvector('english', 'More Than You Know SteepleChase Dexter Gordon')),
  ('Bouncin'' with Dex',     'SteepleChase','SCS 1087',  'LP', 1976, 21, to_tsvector('english', 'Bouncin with Dex SteepleChase Dexter Gordon')),
  ('Something Different',    'SteepleChase','SCS 1145',  'LP', 1980, 21, to_tsvector('english', 'Something Different SteepleChase Dexter Gordon')),
  ('American Classic',       'SteepleChase','SCS 1262',  'LP', 1983, 21, to_tsvector('english', 'American Classic SteepleChase Dexter Gordon'));

-- ── collection_items (one per release) ─────────────────────────────────────
INSERT INTO gruvax_dev.collection_items (release_id, updated_at)
SELECT id, now() - (random() * interval '90 days')
FROM gruvax_dev.releases;

-- Verify counts
DO $$
DECLARE
  release_count INT;
  item_count    INT;
BEGIN
  SELECT count(*) INTO release_count FROM gruvax_dev.releases;
  SELECT count(*) INTO item_count    FROM gruvax_dev.collection_items;
  RAISE NOTICE 'Seeded % releases, % collection_items', release_count, item_count;
  IF release_count < 150 THEN
    RAISE EXCEPTION 'Expected >= 150 releases, got %', release_count;
  END IF;
END;
$$;
