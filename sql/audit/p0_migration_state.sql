-- P0.3 — migration state probe. READ ONLY: every statement is a SELECT.
-- Split from p0_db_state.sql deliberately: the ledger query below raises 42P01 when the Supabase
-- CLI ledger was never created, and in the Supabase SQL editor (whole file = one implicit
-- transaction) that error would abort every statement after it. Keeping it in its own file means
-- it cannot take the data audit down with it.
-- SCHEMA IS `logistics`, NOT `public` (002:1). No statement here can raise on a missing relation,
-- so this file is safe in every run mode: psql, whole-file paste, or section-by-section.
-- RUN THIS FILE FIRST. M1 certifies migration 003, and every table p0_db_state.sql touches comes
-- from 003 — so one M1 row tells you whether that file's queries can resolve at all.

-- M1 AUTHORITATIVE PROBE — applied migrations detected by the objects they create. NULL = not
-- applied; the three 009 rows decide whether 009 may be renumbered into a split set.
SELECT '003 building_scores' AS object, to_regclass('logistics.building_scores')::text AS present
UNION ALL SELECT '006 building_validation_notes', to_regclass('logistics.building_validation_notes')::text
UNION ALL SELECT '007 golden_buildings',          to_regclass('logistics.golden_buildings')::text
UNION ALL SELECT '007 building_rubric_scores',    to_regclass('logistics.building_rubric_scores')::text
UNION ALL SELECT '009 ingress_cases',             to_regclass('logistics.ingress_cases')::text
UNION ALL SELECT '009 operator_reviews',          to_regclass('logistics.operator_reviews')::text
UNION ALL SELECT '009 canonical_drop_points',     to_regclass('logistics.canonical_drop_points')::text;

-- M2 Function inventory, corroborating M1. 008 defines get_building_evidence_extended; 009 defines
-- refresh_ingress_cases, get_ingress_{cases,case_detail,stats}, submit_ingress_review.
SELECT p.proname, count(*) AS n_overloads
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'logistics' GROUP BY p.proname ORDER BY p.proname;

-- M3 Did 007 section C land? Decides whether multi-run rows are possible at all. Constraint
-- building_scores_building_run_unique => 007 applied; building_scores_building_id_key => not.
-- to_regclass, not ::regclass: the literal cast raises 42P01 if the table is absent, which is the
-- very state M1 exists to detect. This form returns zero rows instead.
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE conrelid = to_regclass('logistics.building_scores') ORDER BY conname;

-- M4 Supabase CLI ledger presence. README.md:16 documents applying 001-006 BY HAND and there is no
-- supabase/config.toml, so the ledger may never have been created; absence is NOT proof of
-- non-application — M1 is the authoritative answer.
SELECT to_regclass('supabase_migrations.schema_migrations') IS NOT NULL AS ledger_present;

-- M5 Ledger contents, safe in every run mode. A direct SELECT would raise 42P01 at parse time when
-- the ledger is absent, so the read is deferred into query_to_xml() and gated by CASE, which does
-- not evaluate its THEN branch when the condition is false. Returns NULL when absent, never raises.
-- SELECT * rather than a column list: the ledger's columns vary by Supabase CLI version, and naming
-- `name` explicitly raises 42703 against older ones.
SELECT CASE WHEN to_regclass('supabase_migrations.schema_migrations') IS NOT NULL
            THEN query_to_xml('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version',
                              false, true, '')
       END AS ledger_contents;
-- query_to_xml needs a libxml-enabled build (standard on Supabase). If it errors with "unsupported
-- XML feature", fall back to running this by hand ONLY when M4 returned true:
--   SELECT * FROM supabase_migrations.schema_migrations ORDER BY version;
