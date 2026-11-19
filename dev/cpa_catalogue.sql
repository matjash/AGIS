-- AGIS: layer catalogue table in the CPA database (run once, as the owner of schema public).
-- Same columns as the SQLite catalogues (official / own); one QLR per row.
--
-- Change the curator role below before running. The curator can add, edit,
-- replace and hide entries, but cannot delete them (hidden entries stay as history).

CREATE TABLE IF NOT EXISTS public.agis_viri (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    naziv         text NOT NULL,
    opis          text,
    izvor         text,
    vidnost       text NOT NULL DEFAULT 'cpa',      -- 'javno' | 'cpa'
    kategorija    text,
    oznake        text,                             -- keywords for search, comma separated
    vrstni_red    integer DEFAULT 0,
    omogocen      boolean NOT NULL DEFAULT true,
    qlr           text NOT NULL,
    qlr_prejsnji  text,
    posodobljeno  timestamptz NOT NULL DEFAULT now()
);

-- Columns added later (safe to run again on an existing table)
ALTER TABLE public.agis_viri ADD COLUMN IF NOT EXISTS oznake text;

COMMENT ON TABLE public.agis_viri IS
    'Katalog slojev za vtičnik AGIS (en vir = en QLR). Urejanje prek AGIS: + / desni klik.';

-- Everyone who uses AGIS reads it through the shared read-only account
REVOKE ALL ON public.agis_viri FROM PUBLIC;
GRANT SELECT ON public.agis_viri TO cpa;

-- The curator(s): replace "CPA_admin" with the role or user that maintains the list
GRANT SELECT, INSERT, UPDATE ON public.agis_viri TO "CPA_admin";
