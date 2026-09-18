"""
Granular RBAC for the Django Admin site.

Super Admin and (for simplicity) Admin get full access everywhere. Every
other operational role gets a declared level of access per app, falling
back to read-only for anything not explicitly listed -- so an Accountant
can still *see* orders/bottles for context but can only actually edit
payment-related records, and a View-Only user can't edit anything at all.

To add a new role's access rules, just add an entry to ROLE_APP_ACCESS.
"""

from accounts.models import Role

FULL = "full"
VIEW = "view"
NONE = "none"

# role -> {app_label: level}. "*" is the fallback for apps not listed.
ROLE_APP_ACCESS = {
    Role.SUPER_ADMIN: {"*": FULL},
    Role.ADMIN: {"*": FULL},
    Role.OPERATIONS_MANAGER: {
        "*": VIEW,
        "orders": FULL, "catalog": FULL, "bottles": FULL, "delivery": FULL,
    },
    Role.DELIVERY_MANAGER: {
        "*": VIEW,
        "orders": FULL, "delivery": FULL,
    },
    Role.WAREHOUSE_STAFF: {
        "*": VIEW,
        "bottles": FULL,
    },
    Role.ACCOUNTANT: {
        "*": VIEW,
        "payments": FULL,
    },
    Role.VIEW_ONLY: {
        "*": VIEW,
    },
    # Customers / delivery staff never get Django Admin access at all --
    # they use the customer/staff panels instead (enforced by is_staff too).
    Role.CUSTOMER: {"*": NONE},
    Role.DELIVERY_STAFF: {"*": NONE},
}


def _access_level(user, app_label):
    if not getattr(user, "is_authenticated", False):
        return NONE
    if user.is_superuser:
        return FULL
    rules = ROLE_APP_ACCESS.get(getattr(user, "role", None), {"*": NONE})
    return rules.get(app_label, rules.get("*", NONE))


class RoleBasedAdminMixin:
    """Mix this into a ModelAdmin to enforce ROLE_APP_ACCESS. View-only roles
    can browse and open change forms (read-only) but can't save/add/delete."""

    def _level(self, request):
        return _access_level(request.user, self.model._meta.app_label)

    def has_module_permission(self, request):
        return self._level(request) in (FULL, VIEW)

    def has_view_permission(self, request, obj=None):
        return self._level(request) in (FULL, VIEW)

    def has_add_permission(self, request):
        return self._level(request) == FULL

    def has_change_permission(self, request, obj=None):
        return self._level(request) == FULL

    def has_delete_permission(self, request, obj=None):
        return self._level(request) == FULL
