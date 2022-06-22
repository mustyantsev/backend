-- Attributes used in the Trusted Data Format

-- run externally, then connect to this database
-- CREATE DATABASE tdf_database;

-- performs nocase checks
CREATE COLLATION IF NOT EXISTS NOCASE
    (
    provider = 'icu',
    locale = 'und-u-ks-level2', deterministic = false
);

CREATE SCHEMA IF NOT EXISTS tdf_attribute;
CREATE TABLE IF NOT EXISTS tdf_attribute.attribute_namespace
(
    id   SERIAL PRIMARY KEY,
    name VARCHAR COLLATE NOCASE NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tdf_attribute.attribute
(
    id           SERIAL PRIMARY KEY,
    namespace_id INTEGER NOT NULL REFERENCES tdf_attribute.attribute_namespace,
    state        VARCHAR NOT NULL,
    rule         VARCHAR NOT NULL,
    name         VARCHAR NOT NULL UNIQUE, -- ??? COLLATE NOCASE
    description  VARCHAR,
    values_array       TEXT[],
    group_by_attr     INTEGER REFERENCES tdf_attribute.attribute(id),
    group_by_attrval  VARCHAR,
    CHECK(group_by_attrval is not null or group_by_attr is null)
);

CREATE SCHEMA IF NOT EXISTS tdf_entitlement;
CREATE TABLE IF NOT EXISTS tdf_entitlement.entity_attribute
(
    id        SERIAL PRIMARY KEY,
    entity_id VARCHAR NOT NULL,
    namespace VARCHAR NOT NULL,
    name      VARCHAR NOT NULL,
    value     VARCHAR NOT NULL
);
CREATE INDEX entity_id_index ON tdf_entitlement.entity_attribute (entity_id);

CREATE SCHEMA IF NOT EXISTS tdf_entity;
CREATE TABLE IF NOT EXISTS tdf_entity.entity
(
    id        SERIAL PRIMARY KEY,
    is_person BOOLEAN NOT NULL,
    state     INTEGER,
    entity_id VARCHAR,
    name      VARCHAR,
    email     VARCHAR
);

-- tdf_attribute
CREATE ROLE tdf_attribute_manager WITH LOGIN PASSWORD 'myPostgresPassword';
GRANT USAGE ON SCHEMA tdf_attribute TO tdf_attribute_manager;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA tdf_attribute TO tdf_attribute_manager;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tdf_attribute TO tdf_attribute_manager;
-- tdf_entitlement
CREATE ROLE tdf_entitlement_manager WITH LOGIN PASSWORD 'myPostgresPassword';
GRANT USAGE ON SCHEMA tdf_entitlement TO tdf_entitlement_manager;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA tdf_entitlement TO tdf_entitlement_manager;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tdf_entitlement TO tdf_entitlement_manager;
-- entitlement-store
CREATE ROLE tdf_entitlement_reader WITH LOGIN PASSWORD 'myPostgresPassword';
GRANT USAGE ON SCHEMA tdf_entitlement TO tdf_entitlement_reader;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA tdf_entitlement TO tdf_entitlement_reader;
GRANT SELECT ON tdf_entitlement.entity_attribute TO tdf_entitlement_reader;
-- tdf_entity
CREATE ROLE tdf_entity_manager WITH LOGIN PASSWORD 'myPostgresPassword';
GRANT USAGE ON SCHEMA tdf_entity TO tdf_entity_manager;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA tdf_entity TO tdf_entity_manager;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tdf_entity TO tdf_entity_manager;
