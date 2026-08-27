-- Deterministic, fictitious reference data for Slice 02.
BEGIN;
TRUNCATE payroll_item, employee_payroll, payroll_concept, payroll_period,
  leave_request, vacation_request, vacation_balance, overtime_record,
  attendance_incident, attendance_record, contract, employee, position,
  department RESTART IDENTITY CASCADE;

INSERT INTO department (id, code, name, cost_center) VALUES
  (1, 'ENG', 'Engineering', 'CC-100'), (2, 'OPS', 'Operations', 'CC-200'),
  (3, 'FIN', 'Finance', 'CC-300'), (4, 'HR', 'People Operations', 'CC-400');
INSERT INTO position (id, code, name, department_id) VALUES
  (1, 'SWE2', 'Software Engineer II', 1), (2, 'OPS1', 'Operations Specialist', 2),
  (3, 'ACC1', 'Accountant', 3), (4, 'HRA1', 'HR Analyst', 4);
INSERT INTO employee (id, employee_code, first_name, last_name, status, hire_date, department_id, position_id) VALUES
  (1, 'E-100', 'Ana', 'Silva', 'active', '2022-03-14', 1, 1),
  (2, 'E-101', 'Bruno', 'Costa', 'active', '2024-01-08', 2, 2),
  (3, 'E-102', 'Carla', 'Mendes', 'active', '2021-07-19', 3, 3),
  (4, 'E-103', 'Diego', 'Rocha', 'active', '2023-05-02', 1, 1);
INSERT INTO contract (id, employee_id, contract_type, start_date, end_date, status) VALUES
  (1, 1, 'fixed_term', '2022-03-14', '2025-12-31', 'active'),
  (2, 2, 'indefinite', '2024-01-08', NULL, 'active'),
  (3, 3, 'fixed_term', '2021-07-19', '2025-10-31', 'active'),
  (4, 4, 'indefinite', '2023-05-02', NULL, 'active');
INSERT INTO attendance_record (id, employee_id, work_date, status, scheduled_minutes, worked_minutes, late_minutes, absence_minutes) VALUES
  (1, 1, '2025-02-10', 'present', 480, 480, 0, 0),
  (2, 2, '2025-02-10', 'late', 480, 465, 15, 0),
  (3, 3, '2025-02-10', 'absent', 480, 0, 0, 480),
  (4, 4, '2025-02-10', 'present', 480, 480, 0, 0);
INSERT INTO attendance_incident (id, employee_id, incident_date, incident_type, minutes, status) VALUES
  (1, 2, '2025-02-10', 'late', 15, 'approved'), (2, 3, '2025-02-10', 'absence', 480, 'approved');
INSERT INTO overtime_record (id, employee_id, work_date, approved_minutes, status) VALUES
  (1, 1, '2025-02-12', 120, 'approved'), (2, 4, '2025-02-12', 600, 'approved');
INSERT INTO vacation_balance (id, employee_id, period_year, earned_days, used_days, scheduled_days, available_days) VALUES
  (1, 1, 2025, 20, 5, 3, 12), (2, 2, 2025, 14, 8, 4, 2),
  (3, 3, 2025, 18, 3, 0, 15), (4, 4, 2025, 20, 10, 2, 8);
INSERT INTO vacation_request (id, employee_id, start_date, end_date, requested_days, status, created_at) VALUES
  (1, 1, '2025-11-10', '2025-11-21', 10, 'pending', '2025-09-01T10:00:00Z'),
  (2, 2, '2025-11-03', '2025-11-07', 5, 'pending', '2025-09-02T10:00:00Z'),
  (3, 3, '2025-10-20', '2025-10-24', 5, 'approved', '2025-08-15T10:00:00Z');
INSERT INTO leave_request (id, employee_id, leave_type, start_date, end_date, status) VALUES
  (1, 3, 'medical', '2025-02-10', '2025-02-10', 'approved');
INSERT INTO payroll_period (id, code, start_date, end_date, payment_date, status) VALUES
  (1, '2025-01', '2025-01-01', '2025-01-31', '2025-02-05', 'paid'),
  (2, '2025-02', '2025-02-01', '2025-02-28', '2025-03-05', 'paid');
INSERT INTO employee_payroll (id, employee_id, payroll_period_id, gross_amount, deduction_amount, net_amount, employer_cost, cost_center) VALUES
  (1, 4, 1, 4000.00, 600.00, 3400.00, 4800.00, 'CC-100'),
  (2, 4, 2, 4000.00, 1000.00, 3000.00, 4800.00, 'CC-100'),
  (3, 1, 2, 5000.00, 750.00, 4250.00, 6000.00, 'CC-100'),
  (4, 2, 2, 3200.00, 480.00, 2720.00, 3840.00, 'CC-200'),
  (5, 3, 2, 4500.00, 675.00, 3825.00, 5400.00, 'CC-300');
INSERT INTO payroll_concept (id, code, name, concept_type, taxable) VALUES
  (1, 'BASE', 'Base salary', 'earning', TRUE), (2, 'OT', 'Overtime', 'earning', TRUE),
  (3, 'TAX', 'Income tax', 'deduction', FALSE), (4, 'HEALTH', 'Health contribution', 'deduction', FALSE),
  (5, 'ABSENCE', 'Unpaid absence', 'deduction', FALSE);
INSERT INTO payroll_item (id, employee_payroll_id, payroll_concept_id, quantity, rate, amount, source_reference) VALUES
  (1, 1, 1, 1, 4000.00, 4000.00, 'BASE-2025-01'), (2, 1, 3, 1, 400.00, 400.00, 'TAX-2025-01'), (3, 1, 4, 1, 200.00, 200.00, 'HEALTH-2025-01'),
  (4, 2, 1, 1, 4000.00, 4000.00, 'BASE-2025-02'), (5, 2, 3, 1, 700.00, 700.00, 'TAX-2025-02'), (6, 2, 4, 1, 300.00, 300.00, 'HEALTH-2025-02'),
  (7, 3, 1, 1, 5000.00, 5000.00, 'BASE-2025-02'), (8, 3, 2, 2, 1, 2.00, 'OT-2025-02'), (9, 3, 3, 1, 500.00, 500.00, 'TAX-2025-02'), (10, 3, 4, 1, 250.00, 250.00, 'HEALTH-2025-02'),
  (11, 4, 1, 1, 3200.00, 3200.00, 'BASE-2025-02'), (12, 4, 3, 1, 300.00, 300.00, 'TAX-2025-02'), (13, 4, 4, 1, 180.00, 180.00, 'HEALTH-2025-02'),
  (14, 5, 1, 1, 4500.00, 4500.00, 'BASE-2025-02'), (15, 5, 3, 1, 450.00, 450.00, 'TAX-2025-02'), (16, 5, 4, 1, 225.00, 225.00, 'HEALTH-2025-02');
COMMIT;
