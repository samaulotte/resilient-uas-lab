"""Initial schema.

Revision ID: 0001
Revises: None
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("runner_id", sa.String(length=64), nullable=False),
        sa.Column("adapters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("active_run_id", sa.UUID(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("runner_id"),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("api_version", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("assertion_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "score_profiles",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_table(
        "system_topologies",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("vehicle_class", sa.String(length=64), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scenario_id", sa.UUID(), nullable=True),
        sa.Column("scenario_name", sa.String(length=64), nullable=False),
        sa.Column("scenario_version", sa.String(length=32), nullable=False),
        sa.Column("scenario_hash", sa.String(length=80), nullable=False),
        sa.Column("scenario_document", sa.Text(), nullable=False),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("vehicle", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("runner_id", sa.String(length=64), nullable=True),
        sa.Column("replay_source_run_id", sa.UUID(), nullable=True),
        sa.Column("planned_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("hard_gate_result", sa.String(length=16), nullable=True),
        sa.Column("resilience_score", sa.Float(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("last_simulation_time", sa.Float(), nullable=False),
        sa.Column("mission_complete", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_created_at"), "runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_runs_result"), "runs", ["result"], unique=False)
    op.create_index(op.f("ix_runs_state"), "runs", ["state"], unique=False)
    op.create_table(
        "system_components",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topology_id", sa.String(length=64), nullable=False),
        sa.Column("component_id", sa.String(length=65), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("trust_zone", sa.String(length=32), nullable=False),
        sa.Column("healthy_state", sa.String(length=16), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["topology_id"], ["system_topologies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topology_id", "component_id", name="uq_system_components_topology"),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "name", name="uq_artifacts_run_name"),
    )
    op.create_index(op.f("ix_artifacts_run_id"), "artifacts", ["run_id"], unique=False)
    op.create_table(
        "assertions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("expression", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("metric_path", sa.String(length=120), nullable=False),
        sa.Column("operator", sa.String(length=4), nullable=False),
        sa.Column("measured", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expected", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assertions_run_id"), "assertions", ["run_id"], unique=False)
    op.create_table(
        "metrics",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("simulation_time", sa.Float(), nullable=False),
        sa.Column("wall_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("subsystem", sa.String(length=65), nullable=True),
        sa.Column("state_before", sa.String(length=16), nullable=True),
        sa.Column("state_after", sa.String(length=16), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("scenario_event_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
    )
    op.create_index(op.f("ix_run_events_kind"), "run_events", ["kind"], unique=False)
    op.create_index(
        "ix_run_events_run_time", "run_events", ["run_id", "simulation_time"], unique=False
    )
    op.create_table(
        "run_telemetry_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("t_start", sa.Float(), nullable=False),
        sa.Column("t_end", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("samples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_telemetry_run_sequence"),
    )
    op.create_index(
        "ix_run_telemetry_run_tstart", "run_telemetry_chunks", ["run_id", "t_start"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_run_telemetry_run_tstart", table_name="run_telemetry_chunks")
    op.drop_table("run_telemetry_chunks")
    op.drop_index("ix_run_events_run_time", table_name="run_events")
    op.drop_index(op.f("ix_run_events_kind"), table_name="run_events")
    op.drop_table("run_events")
    op.drop_table("metrics")
    op.drop_index(op.f("ix_assertions_run_id"), table_name="assertions")
    op.drop_table("assertions")
    op.drop_index(op.f("ix_artifacts_run_id"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_table("system_components")
    op.drop_index(op.f("ix_runs_state"), table_name="runs")
    op.drop_index(op.f("ix_runs_result"), table_name="runs")
    op.drop_index(op.f("ix_runs_created_at"), table_name="runs")
    op.drop_table("runs")
    op.drop_table("system_topologies")
    op.drop_table("score_profiles")
    op.drop_table("scenarios")
    op.drop_table("runners")
