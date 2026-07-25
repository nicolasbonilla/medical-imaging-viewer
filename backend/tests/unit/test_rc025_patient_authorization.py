"""RC-025 — role-level authorization on patient records (CAPA-004 CA-4.5).

Risk control for HAZ-010 (unauthorized access to patient data).

CAPA-004 §4 found that of 124 route decorators, 7 enforced a permission and 0
enforced a role — all confined to user administration. This module covers the
patient routes, where the gap was compounded by something worse:

    Ten route docstrings stated "Required permissions: PATIENT_CREATE"
    (and VIEW/UPDATE/DELETE) for permissions that DID NOT EXIST in the
    Permission enum and were enforced nowhere.

In a Class C device a docstring naming a required permission is a claim a
reviewer will believe. Reading patients.py, an auditor would conclude the
routes were access-controlled. Every one of them gated on authentication alone.

SCOPE — read before citing this as closing CAPA-002
These controls answer "may this ROLE operate on patient records at all". They
do NOT answer "may this user access THIS patient" — object-level authorization,
which requires an entitlement model and remains open as CAPA-002 CA-2.1. An
authenticated VIEWER still reaches every patient in the system.

Negative control (CAPA-001 §5): revert any route to
`Depends(get_current_active_user)`, or drop a PATIENT_* permission from the
enum, and these tests MUST fail.
"""
import re
from pathlib import Path

import pytest

from app.security.models import Permission, UserRole
from app.security.rbac import RBACManager

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PATIENT_ROUTES = BACKEND_ROOT / "app" / "api" / "routes" / "patients.py"
ROUTES_DIR = BACKEND_ROOT / "app" / "api" / "routes"

PATIENT_PERMISSIONS = {
    "PATIENT_VIEW",
    "PATIENT_CREATE",
    "PATIENT_UPDATE",
    "PATIENT_DELETE",
}


class TestRC025PermissionsExist:
    """The permissions the docstrings promised must be real."""

    @pytest.mark.parametrize("name", sorted(PATIENT_PERMISSIONS))
    def test_rc025_patient_permission_is_defined(self, name):
        assert hasattr(Permission, name), (
            f"Permission.{name} is referenced by patient route documentation "
            "but is not defined. A promised permission that does not exist "
            "cannot be enforced and misleads every reviewer of that route."
        )

    def test_rc025_no_docstring_promises_a_permission_that_does_not_exist(self):
        """The root cause, generalised across every route module.

        This is the assertion that would have caught the original defect, and it
        guards every future route — not just patients.py.
        """
        defined = {member.name for member in Permission}
        promised: dict[str, set[str]] = {}

        for path in ROUTES_DIR.glob("*.py"):
            for match in re.finditer(r"Required permissions?: ([A-Z_, ]+)", path.read_text(encoding="utf-8")):
                names = {n.strip() for n in match.group(1).split(",") if n.strip()}
                promised.setdefault(path.name, set()).update(names)

        phantom = {
            module: sorted(names - defined)
            for module, names in promised.items()
            if names - defined
        }
        assert not phantom, (
            f"route documentation promises permissions that do not exist: {phantom}"
        )


class TestRC025RolesAreGraded:
    """The permission model must actually distinguish roles, or it is decoration."""

    def test_rc025_every_role_may_view_patients(self):
        for role in UserRole:
            assert RBACManager.has_permission(role, Permission.PATIENT_VIEW), (
                f"{role} cannot view patients; clinical work is impossible"
            )

    def test_rc025_viewer_cannot_create_or_modify_patients(self):
        for permission in (
            Permission.PATIENT_CREATE,
            Permission.PATIENT_UPDATE,
            Permission.PATIENT_DELETE,
        ):
            assert not RBACManager.has_permission(UserRole.VIEWER, permission), (
                f"VIEWER holds {permission.value} — the role grants write access"
            )

    def test_rc025_technician_cannot_update_or_delete(self):
        assert RBACManager.has_permission(UserRole.TECHNICIAN, Permission.PATIENT_CREATE)
        assert not RBACManager.has_permission(UserRole.TECHNICIAN, Permission.PATIENT_UPDATE)
        assert not RBACManager.has_permission(UserRole.TECHNICIAN, Permission.PATIENT_DELETE)

    def test_rc025_only_admin_may_delete_a_patient(self):
        """Deleting a patient record is destructive and subject to regulatory
        retention requirements."""
        for role in UserRole:
            expected = role == UserRole.ADMIN
            assert RBACManager.has_permission(role, Permission.PATIENT_DELETE) is expected, (
                f"{role} delete permission should be {expected}"
            )

    def test_rc025_radiologist_may_update_but_not_delete(self):
        assert RBACManager.has_permission(UserRole.RADIOLOGIST, Permission.PATIENT_UPDATE)
        assert not RBACManager.has_permission(UserRole.RADIOLOGIST, Permission.PATIENT_DELETE)


class TestRC025RoutesEnforceThePermissions:
    """Enforcement sites, not definition sites — CAPA-004 §5's second blind spot.

    RC-018 was recorded VERIFIED because the enum and the role map looked
    complete. Seven of 124 routes applied them. Counting the definition proves
    nothing; only counting the enforcement does.
    """

    SOURCE = PATIENT_ROUTES.read_text(encoding="utf-8")

    def test_rc025_no_patient_route_gates_on_authentication_alone(self):
        assert "Depends(get_current_active_user)" not in self.SOURCE, (
            "a patient route has been reverted to authentication-only access"
        )

    def test_rc025_every_patient_route_enforces_role_or_permission(self):
        """Every route must gate on a permission OR a role. require_role counts:
        the quarantine-triage route is ADMIN-only via require_role, which is a
        stronger gate than any single permission, not a weaker one."""
        route_count = len(re.findall(r"@router\.(get|post|put|patch|delete)", self.SOURCE))
        by_permission = self.SOURCE.count("Depends(require_permission(")
        by_role = self.SOURCE.count("Depends(require_role(")

        assert by_permission + by_role == route_count, (
            f"{by_permission} permission + {by_role} role = "
            f"{by_permission + by_role} of {route_count} patient routes enforce access"
        )

    def test_rc025_destructive_route_requires_the_delete_permission(self):
        assert "Depends(require_permission(Permission.PATIENT_DELETE))" in self.SOURCE

    def test_rc025_write_routes_do_not_settle_for_view_permission(self):
        """A route enforcing PATIENT_VIEW on an update is enforcement theatre."""
        for fn in ("update_patient", "add_medical_history", "update_medical_history"):
            start = self.SOURCE.find(f"async def {fn}(")
            assert start > 0, f"{fn} not found"
            signature = self.SOURCE[start:self.SOURCE.find(")", self.SOURCE.find("current_user", start))]
            assert "PATIENT_UPDATE" in signature, f"{fn} does not require PATIENT_UPDATE"


class TestRC025CreationRecordsProvenance:
    """CAPA-002: there was no data to authorize against."""

    def test_rc025_patient_creation_records_the_creating_user(self):
        source = PATIENT_ROUTES.read_text(encoding="utf-8")
        assert "created_by=current_user.id" in source, (
            "patient creation no longer records who created the record. The "
            "service has always accepted created_by and no caller supplied it, "
            "so every earlier record has created_by = None. Provenance cannot "
            "be reconstructed retroactively."
        )


def test_rc025_does_not_claim_to_close_capa_002():
    """Documents the boundary in an executable place.

    Role-level authorization answers "may this role touch patient records".
    Object-level authorization answers "may this user touch THIS patient".
    Only the first is implemented. An authenticated VIEWER still reaches every
    patient in the system, and CAPA-002 CA-2.1 remains open.
    """
    import json

    manifest = json.loads(
        (BACKEND_ROOT.parent / "docs" / "iec62304" / "records" / "risk_verification"
         / "rc_test_manifest.json").read_text(encoding="utf-8")
    )
    note = manifest["controls"]["RC-025"].get("note", "")
    assert "CAPA-002" in note, (
        "RC-025's manifest entry must record that object-level authorization "
        "remains absent, so no reader mistakes this control for that one."
    )
