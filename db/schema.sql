-- db/schema.sql

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;


-- ============================================================
-- ENUM types
-- ============================================================

CREATE TYPE room_environment  AS ENUM ('indoor', 'outdoor');
CREATE TYPE wall_element_type AS ENUM ('window', 'radiator', 'air_conditioner');
CREATE TYPE season            AS ENUM ('spring', 'summer', 'autumn', 'winter');

-- Declaration order is the comparison order: low < indirect < bright_indirect < direct
CREATE TYPE light_exposure    AS ENUM ('low', 'indirect', 'bright_indirect', 'direct');
CREATE TYPE sun_tolerance     AS ENUM ('none', 'filtered', 'full');

-- One enum for both care_log and reminder. 'repotting' only ever appears in
-- reminder: the act itself lives in plant_container, which already carries the
-- period, the container and the history. A CHECK on care_log enforces it.
CREATE TYPE care_action AS ENUM (
    'watering', 'fertilizing', 'repotting', 'pruning', 'treatment', 'cleaning'
);

CREATE TYPE health_status AS ENUM (
    'healthy', 'dormant', 'stressed', 'sick', 'recovering', 'dying'
);

-- Three tables, three life cycles: a container is kept, a consumable is used
-- up, a tool belongs to no plant in particular. Only a container attaches to a
-- plant, and the composite foreign key on plant_container is what enforces it.
CREATE TYPE container_type  AS ENUM ('pot', 'cachepot');
CREATE TYPE consumable_type AS ENUM ('substrate', 'fertilizer');

-- Carried by the row, not derived from finished_at IS NULL: a run that never
-- reported back and a run someone stopped are not the same thing.
CREATE TYPE batch_status AS ENUM ('running', 'ok', 'failed', 'aborted');


-- ============================================================
-- Tables
-- ============================================================

-- Reference table, seeded at the bottom of this file.
-- is_porous drives watering: a porous wall lets the substrate dry faster.
CREATE TABLE material (
    id        bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    code      text    NOT NULL UNIQUE,
    label     text    NOT NULL,
    is_porous boolean NOT NULL
);

CREATE TABLE site (
    id              bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name            text NOT NULL,
    address         text,
    city            text,
    country_code    char(2),
    latitude        numeric(9,6) NOT NULL,
    longitude       numeric(9,6) NOT NULL,
    -- weather_log.observed_on is computed in this zone, never in UTC:
    -- in summer, a UTC date would roll over two hours early
    timezone        text NOT NULL DEFAULT 'Europe/Brussels',
    created_at      timestamptz   NOT NULL DEFAULT now(),
    -- Nothing is deleted in this model: a row is closed, never removed
    closed_at       timestamptz
);

-- The botanical dictionary is neither closable nor deletable: it only grows.
-- Hence no closed_at here, unlike every other table.
--
-- A month window where start > end wraps around the new year:
-- start = 10, end = 3 means October through March.
CREATE TABLE species (
    id                     bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    scientific_name        text NOT NULL UNIQUE,
    common_name            text,

    -- Watering volume scales with substrate volume, not with the plant.
    -- The litres it multiplies do not exist yet: pot volume comes with the container.
    watering_ml_per_litre  integer NOT NULL,

    exposure_min           light_exposure NOT NULL,
    exposure_max           light_exposure NOT NULL,
    sun_tolerance          sun_tolerance  NOT NULL DEFAULT 'none',

    temp_min_c             integer NOT NULL,
    temp_max_c             integer NOT NULL,

    -- Physiological threshold, not an evaporation parameter. Below it the plant
    -- browns at the leaf margins; that says nothing about how fast the substrate
    -- dries, which is why this drives an alert and never the watering interval.
    -- The species' own sensitivity already lives in species_watering.
    humidity_min_pct       integer,

    fertilizing_interval_days integer,
    fertilizing_month_start   integer,
    fertilizing_month_end     integer,

    repotting_interval_months integer,
    repotting_month_start     integer,
    repotting_month_end       integer,

    created_at             timestamptz NOT NULL DEFAULT now(),

    CHECK (watering_ml_per_litre > 0),
    CHECK (exposure_max >= exposure_min),
    CHECK (temp_max_c > temp_min_c),
    CHECK (humidity_min_pct IS NULL OR humidity_min_pct BETWEEN 0 AND 100),
    CHECK (fertilizing_interval_days IS NULL OR fertilizing_interval_days > 0),
    CHECK (repotting_interval_months IS NULL OR repotting_interval_months > 0),
    CHECK (fertilizing_month_start IS NULL OR fertilizing_month_start BETWEEN 1 AND 12),
    CHECK (fertilizing_month_end   IS NULL OR fertilizing_month_end   BETWEEN 1 AND 12),
    CHECK (repotting_month_start   IS NULL OR repotting_month_start   BETWEEN 1 AND 12),
    CHECK (repotting_month_end     IS NULL OR repotting_month_end     BETWEEN 1 AND 12),
    -- A window is given whole or not at all, same pattern as the room scale
    CHECK ((fertilizing_month_start IS NULL) = (fertilizing_month_end IS NULL)),
    CHECK ((repotting_month_start   IS NULL) = (repotting_month_end   IS NULL))
);

-- One row per season: adding a finer breakdown later needs no migration
CREATE TABLE species_watering (
    id            bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    species_id    bigint NOT NULL REFERENCES species (id),
    season        season NOT NULL,
    interval_days integer NOT NULL,
    UNIQUE (species_id, season),
    CHECK (interval_days > 0)
);

CREATE TABLE plant (
    id           bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    species_id   bigint  NOT NULL REFERENCES species (id),
    name         text    NOT NULL,
    purchased_on date,
    price_eur    numeric(8,2),
    retailer     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    closed_at    timestamptz,
    -- Zero is allowed: a gift or a cutting costs nothing
    CHECK (price_eur IS NULL OR price_eur >= 0)
);

CREATE TABLE room (
    id         bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    site_id    bigint  NOT NULL REFERENCES site (id),
    name       text    NOT NULL,
    floor      integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    closed_at  timestamptz
);

-- Geometry is immutable: any structural change opens a new version.
-- Placements reference a version, never a room.
CREATE TABLE room_version (
    id               bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    room_id          bigint  NOT NULL REFERENCES room (id),
    environment      room_environment NOT NULL DEFAULT 'indoor',
    north_angle      integer NOT NULL,
    scale_wall_index integer,
    scale_cm         numeric(8,2),
    created_at       timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    CHECK (north_angle >= 0 AND north_angle < 360),
    CHECK ((scale_wall_index IS NULL) = (scale_cm IS NULL)),
    CHECK (scale_cm IS NULL OR scale_cm > 0)
);

CREATE TABLE room_vertex (
    id              bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    room_version_id bigint  NOT NULL REFERENCES room_version (id),
    position        integer NOT NULL,
    x               numeric(10,2) NOT NULL,
    y               numeric(10,2) NOT NULL,
    UNIQUE (room_version_id, position),
    CHECK (position >= 0)
);

-- created_at / closed_at are entry dates, not real-world validity.
-- Add valid_from / valid_to the day retroactive history matters.
CREATE TABLE wall_element (
    id              bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    room_version_id bigint  NOT NULL REFERENCES room_version (id),
    wall_index      integer NOT NULL,
    type            wall_element_type NOT NULL,
    t_start         numeric(5,4) NOT NULL,
    t_end           numeric(5,4) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz,
    CHECK (wall_index >= 0),
    CHECK (t_start >= 0 AND t_end <= 1 AND t_start < t_end)
);

-- A plant only exists somewhere: creating one and placing it is a single
-- transaction. The placement points at a version, never at a room, so the
-- geometry under the marker can never change beneath it.
CREATE TABLE plant_placement (
    id              bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    plant_id        bigint NOT NULL REFERENCES plant (id),
    room_version_id bigint NOT NULL REFERENCES room_version (id),
    x               numeric(10,2) NOT NULL,
    y               numeric(10,2) NOT NULL,
    -- How high the support stands, in centimetres — a shelf, a stool, a
    -- windowsill. Not the height of the plant. NULL means it sits on the floor.
    elevation_cm    numeric(6,1),
    created_at      timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz,
    CHECK (elevation_cm IS NULL OR elevation_cm >= 0)
);

-- What holds a plant: its pot, its cachepot. Kept, cleaned, reused — never
-- consumed. volume_l is the substrate volume a pot holds, the litres
-- watering_ml_per_litre multiplies.
CREATE TABLE container (
    id           bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    type         container_type NOT NULL,
    name         text NOT NULL,
    volume_l     numeric(6,2),
    material_id  bigint REFERENCES material (id),

    -- Outer dimensions: what a cachepot must swallow, and what the pot
    -- occupies on a shelf. Volume stays the substrate it holds.
    outer_top_diameter_cm    numeric(5,1),
    outer_bottom_diameter_cm numeric(5,1),
    outer_height_cm          numeric(5,1),

    -- The thin pot the plant arrived in from the garden centre.
    -- Named after what it is, not after when it was acquired.
    is_nursery_pot boolean NOT NULL DEFAULT false,

    -- A cachepot without a hole keeps water at the roots, which lengthens
    -- the interval instead of shortening it.
    has_drainage boolean,

    purchased_on date,
    price_eur    numeric(8,2),
    retailer     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    closed_at    timestamptz,
    CHECK (volume_l IS NULL OR volume_l > 0),
    CHECK (price_eur IS NULL OR price_eur >= 0),
    CONSTRAINT container_dimensions_positive CHECK (
        (outer_top_diameter_cm    IS NULL OR outer_top_diameter_cm    > 0) AND
        (outer_bottom_diameter_cm IS NULL OR outer_bottom_diameter_cm > 0) AND
        (outer_height_cm          IS NULL OR outer_height_cm          > 0)
    ),
    -- A nursery pot came with the plant: its cost is already in the plant's
    -- price, so counting it here would count it twice
    CONSTRAINT nursery_pot_has_no_purchase CHECK (
        NOT is_nursery_pot
        OR (purchased_on IS NULL AND price_eur IS NULL AND retailer IS NULL)
    ),
    CONSTRAINT nursery_pot_is_a_pot CHECK (NOT is_nursery_pot OR type = 'pot'),
    -- Candidate key for the composite foreign key in plant_container,
    -- which is what stops its denormalised type from drifting
    UNIQUE (id, type)
);

-- What gets used up: substrate, fertiliser. A bag is bought once and depletes,
-- so it belongs to no plant — attaching it to one would be meaningless, and
-- the split is what makes that impossible rather than merely discouraged.
CREATE TABLE consumable (
    id           bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    type         consumable_type NOT NULL,
    name         text NOT NULL,
    volume_l     numeric(6,2),

    -- Fertiliser only: the label figures, kept as written on the bottle
    npk               text,
    dilution_ml_per_l numeric(6,2),

    purchased_on date,
    price_eur    numeric(8,2),
    retailer     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    closed_at    timestamptz,
    CHECK (volume_l IS NULL OR volume_l > 0),
    CHECK (price_eur IS NULL OR price_eur >= 0),
    CHECK (dilution_ml_per_l IS NULL OR dilution_ml_per_l > 0),
    CONSTRAINT npk_belongs_to_fertilizer CHECK (
        type = 'fertilizer' OR (npk IS NULL AND dilution_ml_per_l IS NULL)
    )
);

-- Everything else bought for the plants: secateurs, watering can, moisture
-- meter. No type column — a tool is a tool, and nothing reads this table.
CREATE TABLE tool (
    id           bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name         text NOT NULL,
    purchased_on date,
    price_eur    numeric(8,2),
    retailer     text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    closed_at    timestamptz,
    CHECK (price_eur IS NULL OR price_eur >= 0)
);

-- Which container a plant sits in, and for which period. Changing one closes
-- the row and opens a new one, like every other period in this model.
--
-- container_type is denormalised on purpose. It cannot drift from
-- container.type — the composite foreign key forbids it — and it is what
-- makes "one open pot AND one open cachepot per plant" expressible as an
-- index.
CREATE TABLE plant_container (
    id             bigint NOT NULL GENERATED ALWAYS AS IDENTITY,
    plant_id       bigint NOT NULL REFERENCES plant (id),
    container_id   bigint NOT NULL REFERENCES container (id),
    container_type container_type NOT NULL,

    -- Real-world validity. created_at / closed_at say when the row was
    -- entered, which is a different thing: a period lived in 2021 can be
    -- recorded today.
    valid_from     date,
    valid_to       date,

    created_at     timestamptz NOT NULL DEFAULT now(),
    closed_at      timestamptz,

    PRIMARY KEY (id),
    FOREIGN KEY (container_id, container_type) REFERENCES container (id, type),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

-- One row per batch execution. Answers "did it run, and did anything fail",
-- which notification_log.payload does not: that one says why 495 ml, this one
-- says whether the machinery worked.
--
-- Known limit: if the database is unreachable the row cannot be written either,
-- so it records failures inside a run, not failures of the run. The absence of
-- a row for last night is itself the signal.
CREATE TABLE batch_run (
    id            bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    status        batch_status NOT NULL DEFAULT 'running',
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    sites_ok      integer NOT NULL DEFAULT 0,
    sites_failed  integer NOT NULL DEFAULT 0,
    reminders_new integer NOT NULL DEFAULT 0,
    sent          integer NOT NULL DEFAULT 0,
    send_failed   integer NOT NULL DEFAULT 0,
    error         text
);

-- One reading per site and per local day. observed_on is written by Python
-- in the site's timezone, and carries the idempotence: replaying the batch
-- updates the row instead of duplicating it.
CREATE TABLE weather_log (
    id           bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    -- Which run produced this row. NULL when written outside a batch.
    batch_run_id bigint REFERENCES batch_run (id),
    site_id      bigint NOT NULL REFERENCES site (id),
    observed_at  timestamptz NOT NULL,
    observed_on  date NOT NULL,
    temp_c       numeric(4,1),
    humidity_pct numeric(5,2),
    cloud_pct    smallint,
    condition_id smallint,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (site_id, observed_on),
    CHECK (humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100),
    CHECK (cloud_pct    IS NULL OR cloud_pct    BETWEEN 0 AND 100)
);

-- Care actually carried out. Single source of truth.
-- done_at is the day it happened, recorded_at the instant it was entered —
-- the same split as plant_container.valid_from against created_at.
-- Mistakes are corrected in place: one writer, no audit trail needed.
--
-- A date, not a timestamp: nothing in the engine ever reads an hour off this
-- column, and a watering entered at 23:00 would otherwise land on the next
-- day in UTC. The ordering against recorded_at is left to the application —
-- comparing a date to a timestamptz needs a timezone conversion, which is not
-- immutable and therefore not allowed in a CHECK.
CREATE TABLE care_log (
    id          bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    plant_id    bigint NOT NULL REFERENCES plant (id),
    action      care_action NOT NULL,
    done_at     date NOT NULL DEFAULT CURRENT_DATE,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    volume_ml   integer,
    notes       text,
    CHECK (volume_ml IS NULL OR volume_ml > 0),
    -- Repotting is recorded in plant_container, never here
    CONSTRAINT care_log_excludes_repotting CHECK (action <> 'repotting')
);

-- Append-only, on the care_log model: an observation is a fact, corrected in
-- place if mistyped, never closed. There is deliberately no status column on
-- plant — the current state is the most recent row here, so recording a change
-- never overwrites what came before.
--
-- noted_on is when it was observed, recorded_at when it was typed in: the same
-- split as care_log.done_at against recorded_at.
CREATE TABLE plant_health (
    id          bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    plant_id    bigint NOT NULL REFERENCES plant (id),
    status      health_status NOT NULL,
    noted_on    date NOT NULL DEFAULT CURRENT_DATE,
    note        text,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

-- A pending task. Completing it writes into care_log and closes the reminder.
-- dismissed_reason separates "done" from "no longer relevant", which would
-- otherwise be indistinguishable and would skew any adherence figure.
CREATE TABLE reminder (
    id               bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    batch_run_id     bigint REFERENCES batch_run (id),
    plant_id         bigint NOT NULL REFERENCES plant (id),
    action           care_action NOT NULL,
    due_on           date NOT NULL,
    is_generated     boolean NOT NULL DEFAULT true,
    care_log_id      bigint REFERENCES care_log (id),
    completed_at     timestamptz,
    dismissed_reason text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (care_log_id IS NULL OR completed_at IS NOT NULL)
);

-- What was sent. Carries the batch idempotence.
CREATE TABLE notification_log (
    id          bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    -- Which run produced this row. NULL when written outside a batch.
    batch_run_id bigint REFERENCES batch_run (id),
    plant_id    bigint NOT NULL REFERENCES plant (id),
    action      care_action NOT NULL,
    reminder_id bigint REFERENCES reminder (id),
    sent_on     date NOT NULL,
    sent_at     timestamptz NOT NULL DEFAULT now(),
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Enforced by the application, not by the database.
-- A CHECK cannot query another table, so none of this is guaranteed here:
--   at least three vertices per version,
--   wall_index and scale_wall_index below the vertex count,
--   a version referenced by a placement is frozen and never updated again,
--   no room created under a closed site,
--   closing a room closes its open version,
--   no placement in a closed version,
--   closing a version closes its open placements,
--   a plant marker lies inside its room polygon,
--   every species carries all four seasons in species_watering,
--   reminder.care_log_id points at a care_log of the same plant and action,
--   reminder.due_on and notification_log.sent_on are computed in the site's
--     timezone, never in UTC, like weather_log.observed_on,
--   care_log.recorded_at falls on or after care_log.done_at,


-- ============================================================
-- Indexes
-- ============================================================

-- One open version per room at any time
CREATE UNIQUE INDEX ux_room_version_current
    ON room_version (room_id) WHERE closed_at IS NULL;

-- One open placement per plant, whatever the version it sits in
CREATE UNIQUE INDEX ux_plant_placement_current
    ON plant_placement (plant_id) WHERE closed_at IS NULL;

CREATE INDEX ix_species_watering_species ON species_watering (species_id);
CREATE INDEX ix_room_site               ON room (site_id);
CREATE INDEX ix_room_version_room       ON room_version (room_id);
CREATE INDEX ix_wall_element_room       ON wall_element (room_version_id);
CREATE INDEX ix_plant_placement_version ON plant_placement (room_version_id);

-- One open container of each kind per plant — a pot and a cachepot may
-- coexist, two pots may not — and one plant per physical container.
CREATE UNIQUE INDEX ux_plant_container_current
    ON plant_container (plant_id, container_type) WHERE closed_at IS NULL;
CREATE UNIQUE INDEX ux_plant_container_item
    ON plant_container (container_id) WHERE closed_at IS NULL;

CREATE INDEX ix_container_material      ON container (material_id);
CREATE INDEX ix_plant_container_plant   ON plant_container (plant_id);
CREATE INDEX ix_weather_log_site_date   ON weather_log (site_id, observed_on DESC);
CREATE INDEX ix_care_log_plant_action   ON care_log (plant_id, action, done_at DESC);
CREATE INDEX ix_plant_health_plant      ON plant_health (plant_id, noted_on DESC, id DESC);

-- One open reminder per plant and action: an overdue task does not stack
CREATE UNIQUE INDEX ux_reminder_open
    ON reminder (plant_id, action) WHERE completed_at IS NULL;

-- One notification per plant, action and day: replaying the batch sends nothing twice
CREATE UNIQUE INDEX ux_notification
    ON notification_log (plant_id, action, sent_on);

CREATE INDEX ix_batch_run_started ON batch_run (started_at DESC);

-- ============================================================
-- Reference values
-- ============================================================

INSERT INTO material (code, label, is_porous) VALUES
    ('plastic',      'Plastique',      false),
    ('terracotta',   'Terre cuite',    true),
    ('ceramic',      'Céramique',      false),
    ('glazed_earth', 'Terre émaillée', false),
    ('concrete',     'Béton',          true),
    ('metal',        'Métal',          false);


-- ============================================================
-- Grants
-- ============================================================

GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, anon, authenticated, service_role;