"""Application tests for incident, kill-switch, and exception orchestration."""

from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.application.incidents import IncidentService
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import (
    AgentKillSwitchState,
    ExceptionState,
    ExceptionStatus,
    IncidentRecord,
    IncidentStatus,
    IncidentSystemContext,
    PolicyExceptionRecord,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
OWNER = Principal(user_id="system-owner")
ADMIN = Principal(user_id="admin-1", is_admin=True)
STRANGER = Principal(user_id="stranger")


def system_context() -> IncidentSystemContext:
    return IncidentSystemContext(ai_system_id="system-1", ai_system_owner_id="system-owner")


def incident(**overrides: object) -> IncidentRecord:
    values: dict[str, object] = {
        "id": "incident-1",
        "ai_system_id": "system-1",
        "title": "Agent produced unverified financial figures",
        "severity": RiskTier.HIGH,
        "status": IncidentStatus.OPEN,
        "description": "Agent output referenced an unapproved data source.",
        "detected_at": NOW,
        "owner_id": "system-owner",
        "containment": None,
        "remediation_owner_id": None,
        "remediation_description": None,
        "remediation_due_at": None,
        "resolved_at": None,
        "version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return IncidentRecord(**values)  # type: ignore[arg-type]


def agent_state(**overrides: object) -> AgentKillSwitchState:
    values: dict[str, object] = {
        "id": "agent-1",
        "ai_system_id": "system-1",
        "kill_switch_enabled": True,
        "kill_switch_engaged": False,
        "version": 1,
    }
    values.update(overrides)
    return AgentKillSwitchState(**values)  # type: ignore[arg-type]


def exception_record(**overrides: object) -> PolicyExceptionRecord:
    values: dict[str, object] = {
        "id": "exception-1",
        "incident_id": "incident-1",
        "ai_system_id": "system-1",
        "requested_by": "system-owner",
        "requested_at": NOW,
        "purpose": "Keep serving cached results while remediation is in progress.",
        "scope_description": "Bypass real-time verification for read-only queries.",
        "compensating_controls": "Manual spot-check every hour by Security.",
        "expires_at": NOW + timedelta(days=2),
        "status": ExceptionStatus.PENDING,
        "decided_by": None,
        "decided_at": None,
        "decision_reason": None,
        "version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return PolicyExceptionRecord(**values)  # type: ignore[arg-type]


class FakeRepository:
    """In-memory double replicating the SQLAlchemy adapter's join semantics."""

    def __init__(self) -> None:
        self.systems: dict[str, IncidentSystemContext] = {}
        self.incidents: dict[str, IncidentRecord] = {}
        self.agents: dict[str, AgentKillSwitchState] = {}
        self.exceptions: dict[str, PolicyExceptionRecord] = {}

    async def get_system_context(self, ai_system_id: str) -> IncidentSystemContext | None:
        return self.systems.get(ai_system_id)

    async def get_system_context_for_update(
        self, ai_system_id: str
    ) -> IncidentSystemContext | None:
        return self.systems.get(ai_system_id)

    async def get_incident(self, incident_id: str) -> IncidentRecord | None:
        return self.incidents.get(incident_id)

    async def get_incident_for_update(
        self, incident_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord] | None:
        record = self.incidents.get(incident_id)
        if record is None:
            return None
        context = self.systems.get(record.ai_system_id)
        if context is None:
            return None
        return context, record

    async def save_incident(self, record: IncidentRecord) -> IncidentRecord:
        self.incidents[record.id] = record
        return record

    async def list_incidents_for_system(self, ai_system_id: str) -> list[IncidentRecord]:
        return [item for item in self.incidents.values() if item.ai_system_id == ai_system_id]

    async def get_agent_for_kill_switch(
        self, incident_id: str, agent_id: str
    ) -> tuple[IncidentSystemContext, IncidentRecord, AgentKillSwitchState] | None:
        record = self.incidents.get(incident_id)
        agent = self.agents.get(agent_id)
        if record is None or agent is None or agent.ai_system_id != record.ai_system_id:
            return None
        context = self.systems.get(record.ai_system_id)
        if context is None:
            return None
        return context, record, agent

    async def save_agent_kill_switch(
        self, state: AgentKillSwitchState
    ) -> AgentKillSwitchState:
        self.agents[state.id] = state
        return state

    async def get_exception_for_update(
        self, exception_id: str
    ) -> tuple[IncidentSystemContext, PolicyExceptionRecord] | None:
        record = self.exceptions.get(exception_id)
        if record is None:
            return None
        incident_record = self.incidents.get(record.incident_id)
        if incident_record is None:
            return None
        context = self.systems.get(incident_record.ai_system_id)
        if context is None:
            return None
        return context, record

    async def save_exception(self, record: PolicyExceptionRecord) -> PolicyExceptionRecord:
        self.exceptions[record.id] = record
        return record

    async def list_exceptions_for_incident(
        self, incident_id: str
    ) -> list[PolicyExceptionRecord]:
        return [item for item in self.exceptions.values() if item.incident_id == incident_id]


class FakeAudit:
    """Capture incident lifecycle events."""

    def __init__(self) -> None:
        self.actions: list[str] = []

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        entity_version: int,
        payload: dict[str, object],
    ) -> None:
        self.actions.append(action)


class FakeTransaction:
    """Count application transaction boundaries."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def service(repository: FakeRepository) -> tuple[IncidentService, FakeAudit, FakeTransaction]:
    audit = FakeAudit()
    transaction = FakeTransaction()
    return (
        IncidentService(
            repository, audit, transaction, clock=lambda: NOW, id_factory=lambda: "new-id"
        ),
        audit,
        transaction,
    )


async def test_report_incident_requires_owner_or_admin_and_sets_system_owner() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    case, audit, transaction = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.report_incident(
            ai_system_id="system-1",
            title="Unauthorized model call",
            severity=RiskTier.HIGH,
            description="Agent invoked a model outside its approved scope.",
            detected_at=NOW,
            principal=STRANGER,
        )
    assert excinfo.value.kind is ErrorKind.FORBIDDEN

    result = await case.report_incident(
        ai_system_id="system-1",
        title="Unauthorized model call",
        severity=RiskTier.HIGH,
        description="Agent invoked a model outside its approved scope.",
        detected_at=NOW,
        principal=OWNER,
    )
    assert result.status is IncidentStatus.OPEN
    assert result.owner_id == "system-owner"
    assert audit.actions == ["incident.reported"]
    assert transaction.commits == 1


async def test_report_incident_unknown_system_is_not_found() -> None:
    repository = FakeRepository()
    case, _, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.report_incident(
            ai_system_id="missing",
            title="x",
            severity=RiskTier.LOW,
            description="x",
            detected_at=NOW,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.NOT_FOUND


async def test_contain_incident_checks_version_and_transitions() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    case, audit, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.contain_incident(
            incident_id="incident-1",
            containment="Disabled the offending tool.",
            expected_version=99,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.CONFLICT

    result = await case.contain_incident(
        incident_id="incident-1",
        containment="Disabled the offending tool.",
        expected_version=1,
        principal=OWNER,
    )
    assert result.status is IncidentStatus.CONTAINED
    assert result.containment == "Disabled the offending tool."
    assert result.version == 2
    assert audit.actions == ["incident.contained"]


async def test_remediation_plan_then_close_full_lifecycle() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    case, audit, _ = service(repository)

    with_plan = await case.set_remediation_plan(
        incident_id="incident-1",
        remediation_owner_id="system-owner",
        remediation_description="Rotate the affected credentials and retrain the agent.",
        remediation_due_at=NOW + timedelta(days=7),
        expected_version=1,
        principal=OWNER,
    )
    assert with_plan.status is IncidentStatus.REMEDIATING
    assert with_plan.version == 2

    closed = await case.close_incident(
        incident_id="incident-1",
        expected_version=2,
        principal=OWNER,
    )
    assert closed.status is IncidentStatus.CLOSED
    assert closed.resolved_at == NOW
    assert audit.actions == ["incident.remediation_plan_set", "incident.closed"]


async def test_close_incident_without_remediation_plan_is_a_conflict() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident(status=IncidentStatus.REMEDIATING, version=2)
    case, _, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.close_incident(
            incident_id="incident-1",
            expected_version=2,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.CONFLICT


async def test_kill_switch_engage_and_restore_round_trip() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    repository.agents["agent-1"] = agent_state()
    case, audit, _ = service(repository)

    engaged = await case.engage_kill_switch(
        incident_id="incident-1",
        agent_id="agent-1",
        expected_version=1,
        principal=OWNER,
    )
    assert engaged.kill_switch_engaged is True
    assert engaged.version == 2

    with pytest.raises(ApplicationError) as excinfo:
        await case.engage_kill_switch(
            incident_id="incident-1",
            agent_id="agent-1",
            expected_version=2,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.CONFLICT

    restored = await case.restore_kill_switch(
        incident_id="incident-1",
        agent_id="agent-1",
        expected_version=2,
        principal=OWNER,
    )
    assert restored.kill_switch_engaged is False
    assert audit.actions == [
        "incident.kill_switch_engaged",
        "incident.kill_switch_restored",
    ]


async def test_kill_switch_engage_refuses_agent_without_declared_switch() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    repository.agents["agent-1"] = agent_state(kill_switch_enabled=False)
    case, _, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.engage_kill_switch(
            incident_id="incident-1",
            agent_id="agent-1",
            expected_version=1,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.CONFLICT


async def test_exception_decision_requires_admin_and_different_person() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    repository.exceptions["exception-1"] = exception_record()
    case, audit, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.decide_exception(
            exception_id="exception-1",
            approved=True,
            decision_reason="Looks fine",
            expected_version=1,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.FORBIDDEN

    same_requester_admin = Principal(user_id="system-owner", is_admin=True)
    with pytest.raises(ApplicationError) as excinfo:
        await case.decide_exception(
            exception_id="exception-1",
            approved=True,
            decision_reason="Self-approving",
            expected_version=1,
            principal=same_requester_admin,
        )
    assert excinfo.value.kind is ErrorKind.FORBIDDEN

    decided = await case.decide_exception(
        exception_id="exception-1",
        approved=True,
        decision_reason="Compensating controls are adequate.",
        expected_version=1,
        principal=ADMIN,
    )
    assert decided.status is ExceptionStatus.APPROVED
    assert decided.decided_by == "admin-1"
    assert audit.actions == ["incident.exception_decided"]
    assert case.exception_state(decided) is ExceptionState.ACTIVE


async def test_exception_revoke_requires_admin_and_active_state() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    repository.exceptions["exception-1"] = exception_record(
        status=ExceptionStatus.REJECTED, version=2
    )
    case, _, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.revoke_exception(
            exception_id="exception-1",
            decision_reason=None,
            expected_version=2,
            principal=OWNER,
        )
    assert excinfo.value.kind is ErrorKind.FORBIDDEN

    with pytest.raises(ApplicationError) as excinfo:
        await case.revoke_exception(
            exception_id="exception-1",
            decision_reason=None,
            expected_version=2,
            principal=ADMIN,
        )
    assert excinfo.value.kind is ErrorKind.CONFLICT


async def test_list_incidents_and_exceptions_enforce_ownership() -> None:
    repository = FakeRepository()
    repository.systems["system-1"] = system_context()
    repository.incidents["incident-1"] = incident()
    repository.exceptions["exception-1"] = exception_record()
    case, _, _ = service(repository)

    with pytest.raises(ApplicationError) as excinfo:
        await case.list_incidents(ai_system_id="system-1", principal=STRANGER)
    assert excinfo.value.kind is ErrorKind.FORBIDDEN

    incidents = await case.list_incidents(ai_system_id="system-1", principal=OWNER)
    assert [item.id for item in incidents] == ["incident-1"]

    with pytest.raises(ApplicationError):
        await case.list_exceptions(incident_id="incident-1", principal=STRANGER)

    exceptions = await case.list_exceptions(incident_id="incident-1", principal=ADMIN)
    assert [item.id for item in exceptions] == ["exception-1"]
