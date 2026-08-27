"""create deterministic synthetic HRIS reference schema"""

from alembic import op
import sqlalchemy as sa

revision = "0001_synthetic_hris"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("cost_center", sa.String(32), nullable=False),
    )
    op.create_table(
        "position",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id"), nullable=False),
    )
    op.create_table(
        "employee",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_code", sa.String(32), nullable=False, unique=True),
        sa.Column("first_name", sa.String(80), nullable=False),
        sa.Column("last_name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("department.id"), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("position.id"), nullable=False),
    )
    op.create_table(
        "contract",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("contract_type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_contract_dates"),
    )
    op.create_table(
        "attendance_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scheduled_minutes", sa.Integer(), nullable=False),
        sa.Column("worked_minutes", sa.Integer(), nullable=False),
        sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("absence_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("scheduled_minutes >= 0 AND worked_minutes >= 0", name="ck_attendance_minutes"),
        sa.CheckConstraint("late_minutes >= 0 AND absence_minutes >= 0", name="ck_attendance_incidents"),
    )
    op.create_table(
        "attendance_incident",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("incident_date", sa.Date(), nullable=False),
        sa.Column("incident_type", sa.String(32), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint("minutes > 0", name="ck_incident_minutes"),
    )
    op.create_table(
        "overtime_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("approved_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint("approved_minutes > 0", name="ck_overtime_minutes"),
    )
    op.create_table(
        "vacation_balance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("earned_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("used_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("scheduled_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("available_days", sa.Numeric(6, 2), nullable=False),
        sa.UniqueConstraint("employee_id", "period_year", name="uq_vacation_balance_period"),
        sa.CheckConstraint("earned_days >= 0 AND used_days >= 0 AND scheduled_days >= 0", name="ck_vacation_days"),
        sa.CheckConstraint("available_days = earned_days - used_days - scheduled_days", name="ck_vacation_available"),
    )
    op.create_table(
        "vacation_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("requested_days", sa.Numeric(6, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_vacation_request_dates"),
    )
    op.create_table(
        "leave_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("leave_type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_leave_dates"),
    )
    op.create_table(
        "payroll_period",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_payroll_period_dates"),
    )
    op.create_table(
        "employee_payroll",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("payroll_period_id", sa.Integer(), sa.ForeignKey("payroll_period.id"), nullable=False),
        sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("deduction_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("employer_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("cost_center", sa.String(32), nullable=False),
        sa.UniqueConstraint("employee_id", "payroll_period_id", name="uq_employee_payroll_period"),
        sa.CheckConstraint("gross_amount >= 0 AND deduction_amount >= 0 AND employer_cost >= 0", name="ck_payroll_amounts"),
        sa.CheckConstraint("net_amount = gross_amount - deduction_amount", name="ck_payroll_net"),
    )
    op.create_table(
        "payroll_concept",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("concept_type", sa.String(32), nullable=False),
        sa.Column("taxable", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "payroll_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_payroll_id", sa.Integer(), sa.ForeignKey("employee_payroll.id"), nullable=False),
        sa.Column("payroll_concept_id", sa.Integer(), sa.ForeignKey("payroll_concept.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("source_reference", sa.String(64)),
        sa.CheckConstraint("quantity >= 0 AND rate >= 0", name="ck_payroll_item_values"),
    )


def downgrade() -> None:
    for table in (
        "payroll_item", "payroll_concept", "employee_payroll", "payroll_period",
        "leave_request", "vacation_request", "vacation_balance", "overtime_record",
        "attendance_incident", "attendance_record", "contract", "employee", "position", "department",
    ):
        op.drop_table(table)
