from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.notify import notify
from apps.core.permissions import AKWABA_ADMIN, DIRECTOR, LEARNER, ORG_ADMIN, SCHOOL_ROLES
from apps.schools.models import Plan, School, Subscription

from . import providers
from .models import LearnerSubscription, OrganizationSubscription, SubscriptionOrder

FEATURES = {"quizzes": "includes_quizzes", "exams": "includes_exams", "courses": "includes_courses"}


def today():
    return timezone.localdate()


def as_list(data, key):
    """Liste depuis du JSON ou un formulaire multipart (valeurs répétées)."""
    if hasattr(data, "getlist"):
        return [v for v in data.getlist(key) if v not in ("", None)]
    v = data.get(key) or []
    return v if isinstance(v, list) else [v]


# --------------------------------------------------------------------------- tarification
def price_for(plan, extra_seats=0):
    """Prix d'une commande : prix du plan + places supplémentaires (organisations uniquement)."""
    extra = plan.extra_beneficiary_price * extra_seats if plan.audience == "organization" else 0
    return Decimal(plan.price) + Decimal(extra)


def seats_used(sub):
    from apps.learners.models import Learner
    return Learner.objects.filter(cohort__in=sub.cohorts.all()).count()


def check_cohort_seat(cohort, learner=None):
    """Refuse d'ajouter un bénéficiaire à une cohorte couverte dont toutes les places sont prises."""
    if cohort is None:
        return
    from apps.learners.models import Learner
    for sub in OrganizationSubscription.objects.filter(cohorts=cohort, status="active", start_date__lte=today(), end_date__gte=today()):
        qs = Learner.objects.filter(cohort__in=sub.cohorts.all())
        if learner is not None and learner.pk:
            qs = qs.exclude(pk=learner.pk)
        if sub.seats and qs.count() >= sub.seats:
            raise ValidationError({"cohort": f"Toutes les places de l'abonnement « {sub.plan.name} » sont utilisées ({sub.seats}). "
                                             "Augmentez le nombre de places pour ajouter des bénéficiaires."})


# --------------------------------------------------------------------------- droits d'accès
def learner_has_access(learner, feature="quizzes"):
    if not learner.school.subscription_required:
        return True
    flag = FEATURES[feature]
    t = today()
    for sub in LearnerSubscription.objects.filter(learner=learner, status="active", start_date__lte=t, end_date__gte=t).select_related("plan"):
        if getattr(sub.plan, flag) and sub.plan.category in ("", learner.category):
            return True
    if learner.cohort_id:
        for sub in OrganizationSubscription.objects.filter(cohorts=learner.cohort_id, status="active", start_date__lte=t,
                                                           end_date__gte=t).select_related("plan"):
            if getattr(sub.plan, flag) and sub.plan.category in ("", learner.category):
                return True
    return False


def require_access(learner, feature):
    if not learner_has_access(learner, feature):
        if learner.cohort_id and OrganizationSubscription.objects.filter(cohorts=learner.cohort_id, status="suspended", end_date__gte=today()).exists():
            raise PermissionDenied("L'abonnement de votre entreprise est suspendu (défaut de paiement). Contactez votre responsable.",
                                   code="subscription_suspended")
        raise PermissionDenied("Abonnement requis : souscrivez à un plan (menu « Mon abonnement ») pour accéder à ce contenu.",
                               code="subscription_required")


# --------------------------------------------------------------------------- commande
def _resolve_target(user, plan, data):
    """Détermine le bénéficiaire (particulier / organisation / auto-école) selon le rôle de l'acheteur."""
    from apps.learners.models import Learner
    from apps.organizations.models import Organization
    role = user.role
    staff = role in SCHOOL_ROLES or role == AKWABA_ADMIN
    learner = org = school = None
    if plan.audience == "individual":
        if role == LEARNER:
            learner = Learner.objects.filter(user=user).first()
        elif staff:
            learner = Learner.objects.filter(pk=data.get("learner")).first()
        else:
            raise PermissionDenied("Souscription non autorisée pour votre rôle.")
        if not learner:
            raise ValidationError({"learner": "Apprenant introuvable."})
        school = learner.school
    elif plan.audience == "organization":
        if role == ORG_ADMIN:
            org = user.organization
        elif staff:
            org = Organization.objects.filter(pk=data.get("organization")).first()
        else:
            raise PermissionDenied("Souscription non autorisée pour votre rôle.")
        if not org:
            raise ValidationError({"organization": "Organisation introuvable."})
        school = org.school
    else:
        if role == AKWABA_ADMIN:
            school = School.objects.filter(pk=data.get("school")).first()
        elif role == DIRECTOR:
            school = user.school
        else:
            raise PermissionDenied("Seul le directeur peut souscrire l'abonnement de l'auto-école.")
        if not school:
            raise ValidationError({"school": "Auto-école introuvable."})
    if role != AKWABA_ADMIN and school != user.school:
        raise PermissionDenied("Hors de votre auto-école.")
    return school, learner, org


def build_order(user, plan, data):
    """Valide la demande et prépare (sans l'enregistrer) les paramètres de la commande."""
    if not plan.is_on_sale:
        raise ValidationError({"plan": "Ce plan n'est pas en vente actuellement (inactif ou hors de sa période de vente)."})
    school, learner, org = _resolve_target(user, plan, data)
    if plan.organization_id and (org is None or plan.organization_id != org.id):
        raise ValidationError({"plan": "Ce plan est réservé à une autre entreprise."})
    if plan.audience != "school" and plan.school_id not in (None, school.id):
        raise ValidationError({"plan": "Ce plan n'est pas proposé par votre auto-école."})
    if plan.audience == "school" and plan.school_id is not None:
        raise ValidationError({"plan": "Plan invalide."})
    if learner and plan.category and plan.category != learner.category:
        raise ValidationError({"plan": f"Ce plan est réservé au permis {plan.category}."})

    cohort_ids, extra, seats = [], 0, 0
    if plan.audience == "organization":
        from apps.learners.models import Learner
        from apps.organizations.models import Cohort
        ids = [int(i) for i in as_list(data, "cohorts")]
        if plan.cohort_id:                                   # plan réservé à une cohorte : couverture imposée
            ids = [plan.cohort_id]
        if not ids:
            raise ValidationError({"cohorts": "Sélectionnez au moins une cohorte à couvrir (créez-en une d'abord si besoin)."})
        cohorts = list(Cohort.objects.filter(pk__in=ids, organization=org, school=school))
        if len(cohorts) != len(set(ids)):
            raise ValidationError({"cohorts": "Cohorte inconnue ou n'appartenant pas à votre organisation."})
        if plan.max_cohorts and len(cohorts) > plan.max_cohorts:
            raise ValidationError({"cohorts": f"Ce plan couvre au maximum {plan.max_cohorts} cohorte(s)."})
        extra = int(data.get("extra_seats") or 0)
        if extra < 0 or (extra and not plan.extra_beneficiary_price):
            raise ValidationError({"extra_seats": "Places supplémentaires non proposées par ce plan."})
        seats = plan.included_beneficiaries + extra
        needed = Learner.objects.filter(cohort__in=cohorts).count()
        if plan.included_beneficiaries and needed > seats:
            raise ValidationError({"extra_seats": f"Les cohortes choisies comptent {needed} bénéficiaires pour {seats} place(s) : "
                                                  f"ajoutez au moins {needed - seats} place(s) supplémentaire(s)."})
        cohort_ids = [c.id for c in cohorts]
    return dict(school=school, learner=learner, organization=org, cohort_ids=cohort_ids, extra_seats=extra, seats=seats,
                amount=price_for(plan, extra), currency=plan.currency)


@transaction.atomic
def create_order(user, plan, data):
    from apps.billing.models import Invoice, InvoiceLine
    params = build_order(user, plan, data)
    order = SubscriptionOrder.objects.create(plan=plan, audience=plan.audience, created_by=user, method=data.get("method") or "cinetpay",
                                             payer_phone=data.get("phone") or "", **params)
    if plan.audience != "school" and order.amount > 0:
        invoice = Invoice.objects.create(school=order.school, learner=order.learner, organization=order.organization,
                                         title=f"Abonnement {plan.name}", total=order.amount, issue_date=today())
        InvoiceLine.objects.create(invoice=invoice, description=f"Abonnement {plan.name} ({plan.get_billing_cycle_display()})",
                                   quantity=1, unit_price=plan.price)
        if order.extra_seats:
            InvoiceLine.objects.create(invoice=invoice, description="Places supplémentaires", quantity=order.extra_seats,
                                       unit_price=plan.extra_beneficiary_price)
        order.invoice = invoice
        order.save(update_fields=["invoice"])
    return order


def start_payment(order, user, base_url=None):
    """Lance le paiement : CinetPay (redirection) ou encaissement manuel par le personnel. -> redirect_url ou None."""
    from apps.billing.models import Payment
    from apps.billing.services import confirm_payment
    if order.amount <= 0:
        return activate(order) and None
    if order.method in ("cash", "transfer", "other"):
        if user.role in (LEARNER, ORG_ADMIN):
            raise PermissionDenied("Ce mode de paiement est réservé au personnel de l'auto-école.")
        if not order.proof:
            raise ValidationError({"proof": "Preuve de paiement obligatoire (reçu signé, bordereau de versement ou virement)."})
        if order.invoice:
            p = Payment.objects.create(school=order.school, invoice=order.invoice, method=order.method, amount=order.amount,
                                       recorded_by=user, reference=order.proof_reference)
            confirm_payment(p)
        else:
            activate(order)
        return None
    try:
        result = providers.init_payment(order, order.created_by or user, order.payer_phone or getattr(user, "phone", ""),
                                        f"Abonnement {order.plan.name} #{order.pk}", base_url)
    except providers.PaymentError as e:
        invoice = order.invoice
        order.delete()          # rien n'a été encaissé : on ne garde ni commande ni facture orphelines
        if invoice:
            invoice.delete()
        raise ValidationError({"detail": str(e)})
    order.provider_ref = result.reference
    order.method = "cinetpay"
    order.save(update_fields=["provider_ref", "method", "updated_at"])
    if order.invoice:
        Payment.objects.create(school=order.school, invoice=order.invoice, method="cinetpay", amount=order.amount,
                               payer_phone=order.payer_phone, provider_ref=result.reference, recorded_by=user)
    return result.redirect_url


# --------------------------------------------------------------------------- confirmation
def _payment_of(order):
    return order.invoice.payments.filter(provider_ref=order.provider_ref).first() if order.invoice_id else None


def mark_paid(order, raw=None):
    from apps.billing.services import confirm_payment
    order.refresh_from_db()
    if order.status == "paid":
        return order
    payment = _payment_of(order)
    if payment:
        confirm_payment(payment, raw)      # -> on_invoice_paid -> activate()
    else:
        order.raw_payload = raw
        order.save(update_fields=["raw_payload"])
        activate(order)
    order.refresh_from_db()
    return order


def mark_failed(order, raw=None):
    from apps.billing.services import fail_payment
    order.refresh_from_db()
    if order.status != "pending":
        return order
    payment = _payment_of(order)
    if payment:
        fail_payment(payment, raw)
    order.status = "failed"
    order.raw_payload = raw
    order.save(update_fields=["status", "raw_payload", "updated_at"])
    if order.created_by:
        notify(order.created_by, "subscription_failed", "Paiement d'abonnement échoué", f"Le paiement de « {order.plan.name} » n'a pas abouti.")
    return order


def finalize(order):
    """Re-vérifie l'état du paiement auprès de CinetPay (jamais sur la foi du navigateur ou du webhook)."""
    order.refresh_from_db()
    if order.status != "pending" or not order.provider_ref:
        return order
    state, raw = providers.verify_payment(order.provider_ref)
    if state == "succeeded":
        return mark_paid(order, raw)
    if state == "failed":
        return mark_failed(order, raw)
    return order


def mock_confirm(order, success=True):
    if not providers.is_mock():
        raise providers.PaymentError("Simulation indisponible (mode sandbox réel actif).")
    return mark_paid(order, {"mock": True}) if success else mark_failed(order, {"mock": True})


def on_invoice_paid(invoice):
    """Appelé par billing.confirm_payment : active l'abonnement lié à la facture."""
    order = SubscriptionOrder.objects.filter(invoice=invoice, status="pending").first()
    if order and invoice.status == "paid":
        activate(order)


# --------------------------------------------------------------------------- activation
@transaction.atomic
def activate(order):
    plan, t = order.plan, today()
    order = SubscriptionOrder.objects.select_for_update().get(pk=order.pk)
    if order.status == "paid":
        return order
    if order.audience == "individual":
        qs = LearnerSubscription.objects.filter(learner=order.learner, status="active", end_date__gte=t)
    elif order.audience == "organization":
        qs = OrganizationSubscription.objects.filter(organization=order.organization, plan=plan, status="active", end_date__gte=t)
    else:
        qs = Subscription.objects.filter(school=order.school, status="active", end_date__gte=t)
    latest = qs.aggregate(m=Max("end_date"))["m"]
    start = max(t, latest + timedelta(days=1)) if latest else t      # un renouvellement s'ajoute à la suite
    end = start + timedelta(days=plan.duration_days)
    if order.audience == "individual":
        sub = LearnerSubscription.objects.create(school=order.school, learner=order.learner, plan=plan, order=order, start_date=start,
                                                 end_date=end, amount_paid=order.amount)
        who = order.learner.user
    elif order.audience == "organization":
        sub = OrganizationSubscription.objects.create(school=order.school, organization=order.organization, plan=plan, order=order,
                                                      start_date=start, end_date=end, amount_paid=order.amount, seats=order.seats)
        sub.cohorts.set(order.cohort_ids)
        who = None
    else:
        sub = Subscription.objects.create(school=order.school, plan=plan, start_date=start, end_date=end, status="active",
                                          amount_paid=order.amount)
        who = None
    order.status, order.paid_at, order.result_id = "paid", timezone.now(), sub.pk
    order.save(update_fields=["status", "paid_at", "result_id", "updated_at"])
    msg = f"Votre abonnement « {plan.name} » est actif jusqu'au {end:%d/%m/%Y}."
    for u in {x for x in (order.created_by, who) if x}:
        notify(u, "subscription_active", "Abonnement activé", msg, channels=("inapp", "email"))
    return order


# --------------------------------------------------------------------------- vie des abonnements
def expire_subscriptions():
    t = today()
    n = 0
    for model in (LearnerSubscription, OrganizationSubscription, Subscription):
        n += model.objects.filter(status="active", end_date__lt=t).update(status="expired")
    return n


def send_subscription_reminders(days=(7, 3, 1)):
    """Rappels avant expiration (à planifier chaque jour, avec send_reminders)."""
    from apps.accounts.models import User
    t, sent = today(), 0
    for d in days:
        target = t + timedelta(days=d)
        for sub in LearnerSubscription.objects.filter(status="active", end_date=target).select_related("learner__user", "plan"):
            if sub.learner.user:
                notify(sub.learner.user, "subscription_expiring", "Votre abonnement expire bientôt",
                       f"« {sub.plan.name} » expire dans {d} jour(s). Renouvelez-le pour garder l'accès.", channels=("inapp", "sms"))
                sent += 1
        for sub in OrganizationSubscription.objects.filter(status="active", end_date=target).select_related("organization", "plan"):
            for u in User.objects.filter(organization=sub.organization, role=ORG_ADMIN, is_active=True):
                notify(u, "subscription_expiring", "Abonnement de l'organisation bientôt expiré",
                       f"« {sub.plan.name} » expire dans {d} jour(s).", channels=("inapp", "email"))
                sent += 1
    return sent


def set_cohorts(sub, cohort_ids):
    """Change les cohortes couvertes d'un abonnement d'organisation (respect du plafond du plan et des places)."""
    from apps.learners.models import Learner
    from apps.organizations.models import Cohort
    cohorts = list(Cohort.objects.filter(pk__in=cohort_ids, organization=sub.organization))
    if len(cohorts) != len(set(cohort_ids)) or not cohorts:
        raise ValidationError({"cohorts": "Sélection invalide."})
    if sub.plan.max_cohorts and len(cohorts) > sub.plan.max_cohorts:
        raise ValidationError({"cohorts": f"Ce plan couvre au maximum {sub.plan.max_cohorts} cohorte(s)."})
    needed = Learner.objects.filter(cohort__in=cohorts).count()
    if sub.seats and needed > sub.seats:
        raise ValidationError({"cohorts": f"Ces cohortes comptent {needed} bénéficiaires pour {sub.seats} place(s) souscrite(s)."})
    sub.cohorts.set(cohorts)
    return sub


# --------------------------------------------------------------------------- vue « mon abonnement »
def serialize_sub(sub):
    base = {"id": sub.id, "plan": sub.plan_id, "plan_name": sub.plan.name, "start_date": sub.start_date, "end_date": sub.end_date,
            "status": sub.status, "is_current": sub.is_current, "days_left": sub.days_left, "amount_paid": sub.amount_paid}
    if isinstance(sub, OrganizationSubscription):
        base.update(seats=sub.seats, seats_used=seats_used(sub), max_cohorts=sub.plan.max_cohorts,
                    cohorts=[{"id": c.id, "name": c.name, "learners": c.learners.count()} for c in sub.cohorts.all()])
    return base


# --------------------------------------------------------------------------- suspension (défaut de paiement)
def suspend(sub, reason="", actor=None):
    if sub.status != "active":
        raise ValidationError({"detail": "Seul un abonnement actif peut être suspendu."})
    sub.status, sub.suspended_at, sub.suspension_reason = "suspended", timezone.now(), (reason or "Défaut de paiement")[:255]
    sub.save(update_fields=["status", "suspended_at", "suspension_reason", "updated_at"])
    _notify_suspension(sub, True)
    return sub


def reactivate(sub, actor=None):
    if sub.status != "suspended":
        raise ValidationError({"detail": "Cet abonnement n'est pas suspendu."})
    if sub.end_date < today():
        sub.status = "expired"
    else:
        sub.status = "active"
    sub.suspended_at, sub.suspension_reason = None, ""
    sub.save(update_fields=["status", "suspended_at", "suspension_reason", "updated_at"])
    _notify_suspension(sub, False)
    return sub


def suspend_organization(org, reason=""):
    """Suspend TOUS les abonnements actifs d'une entreprise (les bénéficiaires de ses cohortes perdent l'accès)."""
    return [suspend(s, reason) for s in OrganizationSubscription.objects.filter(organization=org, status="active")]


def reactivate_organization(org):
    return [reactivate(s) for s in OrganizationSubscription.objects.filter(organization=org, status="suspended")]


def _notify_suspension(sub, suspended):
    from apps.accounts.models import User
    if isinstance(sub, OrganizationSubscription):
        targets = User.objects.filter(organization=sub.organization, role=ORG_ADMIN, is_active=True)
        who = sub.organization.name
    else:
        targets = [sub.learner.user] if sub.learner.user else []
        who = "votre compte"
    title = "Abonnement suspendu" if suspended else "Abonnement réactivé"
    msg = (f"L'abonnement « {sub.plan.name} » de {who} est suspendu : {sub.suspension_reason}. Régularisez le paiement pour rétablir l'accès."
           if suspended else f"L'abonnement « {sub.plan.name} » de {who} est de nouveau actif.")
    for u in targets:
        notify(u, "subscription_suspended" if suspended else "subscription_reactivated", title, msg, channels=("inapp", "email"))


def next_period(plan, latest_end):
    """Période de validité qu'obtiendrait un achat maintenant (un renouvellement s'ajoute à la suite)."""
    t = today()
    start = max(t, latest_end + timedelta(days=1)) if latest_end else t
    return start, start + timedelta(days=plan.duration_days)
