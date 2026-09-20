from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

LIMITS = {
    "learners": ("max_learners", "apprenants"),
    "instructors": ("max_instructors", "moniteurs"),
    "agencies": ("max_agencies", "agences"),
    "cohorts": ("max_cohorts", "cohortes"),
}


def active_subscription(school):
    from .models import Subscription
    today = timezone.localdate()
    return (Subscription.objects.filter(school=school, status="active", start_date__lte=today, end_date__gte=today)
            .select_related("plan").order_by("-end_date").first())


def count_for(school, key):
    from apps.learners.models import Learner
    from apps.organizations.models import Cohort
    from apps.practice.models import Instructor
    from .models import Agency
    return {"learners": lambda: Learner.objects.filter(school=school).count(),
            "instructors": lambda: Instructor.objects.filter(school=school).count(),
            "agencies": lambda: Agency.objects.filter(school=school).count(),
            "cohorts": lambda: Cohort.objects.filter(school=school).count()}[key]()


def check_limit(school, key):
    """Lève une erreur si le forfait de l'auto-école interdit une création de plus.

    Une auto-école sans aucun abonnement n'est pas limitée (mode démo / gratuit).
    """
    if school is None:
        return
    from .models import Subscription
    if not Subscription.objects.filter(school=school).exists():
        return
    sub = active_subscription(school)
    if sub is None:
        raise PermissionDenied("Abonnement expiré ou suspendu : création impossible.")
    attr, label = LIMITS[key]
    limit = getattr(sub.plan, attr)
    if count_for(school, key) >= limit:
        raise ValidationError({"detail": f"Limite du forfait {sub.plan.name} atteinte ({limit} {label})."})


def usage(school):
    sub = active_subscription(school)
    data = {k: {"used": count_for(school, k), "limit": getattr(sub.plan, LIMITS[k][0]) if sub else None}
            for k in LIMITS}
    return {"plan": sub.plan.name if sub else None, "expires": sub.end_date if sub else None, "usage": data}
