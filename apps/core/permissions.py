"""RBAC : matrice rôle -> ressource -> verbes."""
from rest_framework.permissions import BasePermission

# Rôles
AKWABA_ADMIN = "akwaba_admin"
DIRECTOR = "director"
SECRETARY = "secretary"
ACCOUNTANT = "accountant"
ORG_ADMIN = "org_admin"
HR = "hr"
TRAINING_MANAGER = "training_manager"
ORG_ACCOUNTANT = "org_accountant"
ORG_DIRECTION = "org_direction"
INSTRUCTOR = "instructor"
LEARNER = "learner"

ROLE_CHOICES = [
    (AKWABA_ADMIN, "Administrateur Akwaba"),
    (DIRECTOR, "Directeur d'auto-école"),
    (SECRETARY, "Secrétaire"),
    (ACCOUNTANT, "Comptable"),
    (ORG_ADMIN, "Administrateur d'entreprise"),
    (HR, "RH"),
    (TRAINING_MANAGER, "Responsable formation"),
    (ORG_ACCOUNTANT, "Comptable entreprise"),
    (ORG_DIRECTION, "Direction"),
    (INSTRUCTOR, "Moniteur"),
    (LEARNER, "Apprenant"),
]

SCHOOL_ROLES = {DIRECTOR, SECRETARY, ACCOUNTANT}
ORG_ROLES = {ORG_ADMIN, HR, TRAINING_MANAGER, ORG_ACCOUNTANT, ORG_DIRECTION}

VERBS = ("view", "create", "change", "delete", "validate", "export", "print", "administer")
ALL = set(VERBS)
RO = {"view"}
RW = {"view", "create", "change"}
RWD = {"view", "create", "change", "delete"}
VE = {"view", "export", "print"}

RESOURCES = [
    "users", "schools", "agencies", "trainings", "learners", "documents", "courses", "questions",
    "quizzes", "attempts", "instructors", "vehicles", "maintenance", "fuel", "rooms", "lessons",
    "evaluations", "organizations", "contracts", "cohorts", "groups", "invoices", "payments",
    "installments", "expenses", "exams", "certificates", "reports", "plans", "subscriptions",
    "audit", "notifications", "imports", "quotes", "subscription_orders", "member_subscriptions",
    "individual_quotes", "recycling_items", "recycling_reminder_settings", "alert_settings",
]

MATRIX = {
    AKWABA_ADMIN: {"*": ALL},
    DIRECTOR: {
        "*": ALL,
        "plans": ALL, "subscriptions": RO, "schools": {"view", "change"}, "quotes": set(),
    },
    SECRETARY: {
        "learners": RWD | {"validate"}, "documents": RWD, "lessons": RWD, "cohorts": RWD, "groups": RWD,
        "organizations": RW, "contracts": RO, "invoices": RW | {"print"}, "payments": RW | {"print"},
        "installments": RW, "agencies": RO, "trainings": RO, "courses": RW, "questions": RO,
        "quizzes": RO, "instructors": RO, "vehicles": RO, "rooms": RO, "exams": RW, "certificates": RO | {"print"},
        "attempts": RO, "evaluations": RO, "schools": RO, "reports": RO, "users": RO, "notifications": RO,
        "plans": RO, "subscription_orders": {"view", "create"}, "member_subscriptions": RO,
        "individual_quotes": RWD | {"validate", "print"}, "recycling_items": RO,
        "recycling_reminder_settings": RO,
    },
    ACCOUNTANT: {
        "invoices": ALL, "payments": ALL, "installments": ALL, "expenses": ALL, "reports": ALL,
        "learners": RO, "organizations": RO, "contracts": RO, "cohorts": RO, "agencies": RO,
        "trainings": RO, "vehicles": RO, "instructors": RO, "maintenance": RO, "fuel": RO,
        "schools": RO, "notifications": RO, "plans": RO, "subscription_orders": RO, "member_subscriptions": {"view", "administer"},
    },
    ORG_ADMIN: {
        "learners": RW | {"export"}, "cohorts": RO, "groups": RO, "contracts": RO, "invoices": VE,
        "payments": VE, "installments": RO, "reports": VE, "certificates": VE, "attempts": RO, "exams": RO,
        "organizations": RO, "trainings": RO, "lessons": RO, "notifications": RO, "users": RW, "evaluations": RO,
        "imports": {"create", "view"}, "plans": RO, "subscription_orders": {"view", "create"},
        "member_subscriptions": {"view", "change"},
    },
    HR: {
        "learners": RW | {"export"}, "cohorts": RO, "groups": RO, "contracts": RO, "reports": VE,
        "certificates": VE, "attempts": RO, "exams": RO, "organizations": RO, "trainings": RO, "lessons": RO,
        "notifications": RO, "evaluations": RO, "imports": {"create", "view"}, "plans": RO,
        "member_subscriptions": RO,
    },
    TRAINING_MANAGER: {
        "learners": RO | {"export"}, "cohorts": RO, "groups": RO, "contracts": RO, "reports": VE,
        "certificates": VE, "attempts": RO, "exams": RO, "organizations": RO, "trainings": RO,
        "lessons": RO, "evaluations": RW, "notifications": RO, "plans": RO, "member_subscriptions": RO,
    },
    ORG_ACCOUNTANT: {
        "invoices": VE, "payments": VE, "installments": RO, "contracts": RO, "reports": VE,
        "organizations": RO, "cohorts": RO, "learners": RO, "notifications": RO, "plans": RO,
        "subscription_orders": RO, "member_subscriptions": RO,
    },
    ORG_DIRECTION: {
        "learners": VE, "cohorts": RO, "groups": RO, "contracts": RO, "invoices": VE, "payments": VE,
        "installments": RO, "reports": VE, "certificates": VE, "attempts": RO, "exams": RO,
        "organizations": RO, "trainings": RO, "notifications": RO, "plans": RO, "member_subscriptions": RO,
    },
    INSTRUCTOR: {
        "learners": RO, "lessons": {"view", "change", "create"}, "evaluations": RW, "vehicles": RO,
        "instructors": RO, "cohorts": RO, "groups": RO, "trainings": RO, "attempts": RO, "courses": RO,
        "notifications": RO, "rooms": RO,
    },
    LEARNER: {
        "learners": RO, "documents": RO, "courses": RO, "quizzes": RO, "attempts": {"view", "create", "change"},
        "exams": RO, "certificates": RO | {"print"}, "invoices": RO | {"print"}, "payments": {"view", "create", "print"},
        "installments": RO, "lessons": RO, "evaluations": RO, "trainings": RO, "notifications": RO,
        "instructors": RO, "cohorts": RO, "schools": RO, "agencies": RO, "plans": RO,
        "subscription_orders": {"view", "create"}, "member_subscriptions": RO,
    },
}


def allowed(user, resource, verb):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    perms = MATRIX.get(user.role, {})
    if user.role in (AKWABA_ADMIN,):
        return True
    grant = perms.get(resource)
    if grant is None:
        grant = perms.get("*", set())
    return verb in grant


def permissions_for(user):
    return {r: sorted(v for v in VERBS if allowed(user, r, v)) for r in RESOURCES}


ACTION_VERBS = {
    "list": "view", "retrieve": "view", "create": "create", "update": "change",
    "partial_update": "change", "destroy": "delete",
}


class RBACPermission(BasePermission):
    """Utilise `view.resource` et, pour les actions custom, `view.action_verbs`."""

    def has_permission(self, request, view):
        resource = getattr(view, "resource", None)
        if not resource:
            return bool(request.user and request.user.is_authenticated)
        action = getattr(view, "action", None)
        custom = getattr(view, "action_verbs", {}) or {}
        if action in custom:
            verb = custom[action]
        elif action in ACTION_VERBS:
            verb = ACTION_VERBS[action]
        else:
            verb = "view" if request.method in ("GET", "HEAD", "OPTIONS") else "change"
        return allowed(request.user, resource, verb)
