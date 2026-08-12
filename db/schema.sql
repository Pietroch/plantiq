-- db/schema.sql

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;


-- ============================================================
-- ENUM types
-- ============================================================


-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE site (
    id              bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name            text NOT NULL,
    address         text,
    city            text,
    country_code    char(2),
    latitude        numeric(9,6) NOT NULL,
    longitude       numeric(9,6) NOT NULL,
    created_at      timestamptz   NOT NULL DEFAULT now(),
    -- Nothing is deleted in this model: a row is closed, never removed
    closed_at       timestamptz
);

CREATE TABLE species (
    id                      bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    scientific_name         text NOT NULL UNIQUE,
    watering_interval_days  integer NOT NULL
);

CREATE TABLE plant (
    id          bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    species_id  bigint NOT NULL REFERENCES species (id)
);

-- ============================================================
-- Grants
-- ============================================================

GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, anon, authenticated, service_role;