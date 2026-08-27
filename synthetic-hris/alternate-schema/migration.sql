BEGIN;
DROP TABLE IF EXISTS PAY_MOVEMENT, TIME_EVENT, HR_CONTRACT, PAY_RUN, HR_PERSON CASCADE;
CREATE TABLE HR_PERSON (
    person_id INTEGER PRIMARY KEY, person_no VARCHAR(32) UNIQUE NOT NULL,
    given_name VARCHAR(80) NOT NULL, family_name VARCHAR(80) NOT NULL,
    employment_state VARCHAR(32) NOT NULL, joined_on DATE NOT NULL
);
CREATE TABLE HR_CONTRACT (
    contract_id INTEGER PRIMARY KEY, person_ref INTEGER NOT NULL REFERENCES HR_PERSON(person_id),
    kind VARCHAR(32) NOT NULL, valid_from DATE NOT NULL, valid_to DATE,
    contract_state VARCHAR(32) NOT NULL,
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE TABLE TIME_EVENT (
    event_id INTEGER PRIMARY KEY, person_ref INTEGER NOT NULL REFERENCES HR_PERSON(person_id),
    event_day DATE NOT NULL, overtime_minutes INTEGER NOT NULL, event_status VARCHAR(32) NOT NULL,
    CHECK (overtime_minutes > 0)
);
CREATE TABLE PAY_RUN (
    run_id INTEGER PRIMARY KEY, period_code VARCHAR(32) UNIQUE NOT NULL,
    period_start DATE NOT NULL, period_end DATE NOT NULL, paid_on DATE NOT NULL,
    run_status VARCHAR(32) NOT NULL, CHECK (period_end >= period_start)
);
CREATE TABLE PAY_MOVEMENT (
    movement_id INTEGER PRIMARY KEY, person_ref INTEGER NOT NULL REFERENCES HR_PERSON(person_id),
    run_id INTEGER NOT NULL REFERENCES PAY_RUN(run_id), gross_pay NUMERIC(12,2) NOT NULL,
    withheld_pay NUMERIC(12,2) NOT NULL, net_pay NUMERIC(12,2) NOT NULL,
    employer_total NUMERIC(12,2) NOT NULL, cost_unit VARCHAR(32) NOT NULL,
    UNIQUE (person_ref, run_id), CHECK (net_pay = gross_pay - withheld_pay)
);
COMMIT;
