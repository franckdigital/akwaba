"""Tableaux de bord, KPI, rentabilité et jeux de données exportables."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from datetime import timezone as dt_timezone
from django.utils import timezone

from apps.billing.models import Expense, Installment, Invoice, Payment
from apps.core.models import AuditLog
from apps.core.permissions import AKWABA_ADMIN, INSTRUCTOR, LEARNER, ORG_ROLES, SCHOOL_ROLES
from apps.core.viewsets import scope_queryset
from apps.exams.models import Certificate
from apps.learners.models import Learner
from apps.organizations.models import Cohort, Contract, Organization
from apps.pedagogy.models import Attempt
from apps.practice.models import Instructor, Lesson, Vehicle
from apps.schools.models import School, Subscription, Training


def scoped(qs, user, school="school", org=None, learner=None, instructor=None):
    view = SimpleNamespace(school_lookup=school, org_lookup=org, learner_lookup=learner,
                           instructor_lookup=instructor, include_global=False)
    return scope_queryset(qs, user, view)


def _num(v):
    return v or Decimal(0)


def _period(qs, field, params):
    if params.get("date_from"):
        qs = qs.filter(**{field + "__gte": params["date_from"]})
    if params.get("date_to"):
        qs = qs.filter(**{field + "__lte": params["date_to"]})
    return qs


def _school_filter(qs, user, params, field="school"):
    """L'admin Akwaba peut restreindre à une auto-école via ?school=."""
    if user.role == AKWABA_ADMIN and params.get("school"):
        qs = qs.filter(**{field + "_id" if field == "school" else field: params["school"]})
    return qs


# --------------------------------------------------------------------------- KPI
def kpis(user, params):
    pays = scoped(Payment.objects.filter(status="confirmed"), user)
    pays = _school_filter(_period(pays, "paid_at__date", params), user, params)
    revenue = _num(pays.aggregate(s=Sum("amount"))["s"])
    exps = _school_filter(_period(scoped(Expense.objects.all(), user), "date", params), user, params)
    expenses = _num(exps.aggregate(s=Sum("amount"))["s"])
    learners = _school_filter(scoped(Learner.objects.all(), user, learner="user"), user, params)
    n_learners = learners.count()
    invoices = _school_filter(scoped(Invoice.objects.filter(kind="invoice").exclude(status__in=["cancelled", "draft"]), user), user, params)
    invoiced = _num(invoices.aggregate(s=Sum("total"))["s"])
    paid = _num(invoices.aggregate(s=Sum("paid"))["s"])
    dropped = learners.filter(status="dropped").count()
    exam_att = _school_filter(scoped(Attempt.objects.filter(is_exam=True).exclude(status="in_progress"), user), user, params)
    quiz_att = _school_filter(scoped(Attempt.objects.filter(is_exam=False).exclude(status="in_progress"), user), user, params)
    lessons_done = _school_filter(scoped(Lesson.objects.filter(status="done"), user), user, params)
    hours = sum(l.duration_hours for l in lessons_done)
    n_exam = exam_att.count()
    return {
        "revenue": revenue, "expenses": expenses, "net_result": revenue - expenses,
        "learners": n_learners,
        "exam_pass_rate": round(exam_att.filter(passed=True).count() * 100 / n_exam, 1) if n_exam else 0,
        "dropout_rate": round(dropped * 100 / n_learners, 1) if n_learners else 0,
        "unpaid_rate": round(float((invoiced - paid) * 100 / invoiced), 1) if invoiced else 0,
        "unpaid_amount": invoiced - paid, "invoiced": invoiced,
        "hours_done": round(hours, 1),
        "trainings_completed": learners.filter(status__in=["training_done", "passed", "licensed"]).count(),
        "avg_quiz_score": round(float(quiz_att.aggregate(a=Avg("percent"))["a"] or 0), 1),
        "exam_attempts": n_exam,
    }


def profitability(user, params):
    by = params.get("by", "training")
    pays = _school_filter(_period(scoped(Payment.objects.filter(status="confirmed"), user), "paid_at__date", params), user, params)
    exps = _school_filter(_period(scoped(Expense.objects.all(), user), "date", params), user, params)
    rev, exp, labels = defaultdict(Decimal), defaultdict(Decimal), {}

    def key(obj, name):
        labels[obj if obj is not None else "-"] = name or "Non affecté"
        return obj if obj is not None else "-"

    pays = pays.select_related("invoice__learner__training", "invoice__learner__agency", "invoice__learner__cohort",
                               "invoice__organization", "invoice__learner__organization")
    for p in pays:
        inv, learner = p.invoice, p.invoice.learner
        if by == "training":
            k = key(learner.training_id if learner else None, learner.training.name if learner and learner.training else None)
        elif by == "category":
            k = key(learner.category if learner else None, f"Permis {learner.category}" if learner else None)
        elif by == "agency":
            k = key(learner.agency_id if learner else None, learner.agency.name if learner and learner.agency else None)
        elif by == "cohort":
            k = key(learner.cohort_id if learner else None, learner.cohort.name if learner and learner.cohort else None)
        elif by == "organization":
            org = inv.organization or (learner.organization if learner else None)
            k = key(org.id if org else None, org.name if org else "Particuliers")
        elif by == "period":
            d = timezone.localtime(p.paid_at) if p.paid_at else p.created_at
            k = key(f"{d:%Y-%m}", f"{d:%Y-%m}")
        else:
            k = key("all", "Total")
        rev[k] += p.amount
    for e in exps.select_related("agency", "vehicle", "instructor"):
        if by == "agency":
            k = key(e.agency_id, e.agency.name if e.agency else None)
        elif by == "vehicle":
            k = key(e.vehicle_id, e.vehicle.plate if e.vehicle else None)
        elif by == "instructor":
            k = key(e.instructor_id, str(e.instructor) if e.instructor else None)
        elif by == "period":
            k = key(f"{e.date:%Y-%m}", f"{e.date:%Y-%m}")
        else:
            k = key("all" if by not in ("training", "category", "cohort", "organization") else "-", "Charges non affectées")
            if by in ("training", "category", "cohort", "organization"):
                labels["-"] = "Charges non affectées"
        exp[k] += e.amount
    rows = []
    for k in sorted(set(rev) | set(exp), key=str):
        rows.append({"key": k, "label": labels.get(k, str(k)), "revenue": rev[k], "expenses": exp[k], "net": rev[k] - exp[k]})
    return {"by": by, "rows": rows, "total": {"revenue": sum(rev.values(), Decimal(0)),
                                              "expenses": sum(exp.values(), Decimal(0)),
                                              "net": sum(rev.values(), Decimal(0)) - sum(exp.values(), Decimal(0))}}


def cohort_stats(cohort):
    learners = cohort.learners.all()
    n = learners.count()
    attempts = Attempt.objects.filter(learner__cohort=cohort).exclude(status="in_progress")
    exam = attempts.filter(is_exam=True)
    quiz = attempts.filter(is_exam=False)
    lessons = Lesson.objects.filter(Q(cohort=cohort) | Q(learner__cohort=cohort))
    inv = Invoice.objects.filter(kind="invoice", learner__cohort=cohort).exclude(status__in=["cancelled", "draft"])
    return {
        "cohort": cohort.name, "learners": n, "capacity": cohort.capacity,
        "fill_rate": round(n * 100 / cohort.capacity, 1) if cohort.capacity else 0,
        "by_status": {r["status"]: r["c"] for r in learners.values("status").annotate(c=Count("id"))},
        "avg_quiz_score": round(float(quiz.aggregate(a=Avg("percent"))["a"] or 0), 1),
        "exam_pass_rate": round(exam.filter(passed=True).count() * 100 / exam.count(), 1) if exam.count() else 0,
        "certificates": Certificate.objects.filter(learner__cohort=cohort, status="valid").count(),
        "lessons_done": lessons.filter(status="done").count(), "lessons_absent": lessons.filter(status="absent").count(),
        "invoiced": _num(inv.aggregate(s=Sum("total"))["s"]), "paid": _num(inv.aggregate(s=Sum("paid"))["s"]),
    }


# --------------------------------------------------------------------------- dashboards
def dashboard(user, params):
    today = timezone.localdate()
    role = user.role
    if role == AKWABA_ADMIN:
        revenue = _num(Payment.objects.filter(status="confirmed").aggregate(s=Sum("amount"))["s"])
        return {"scope": "akwaba", "schools": School.objects.count(), "organizations": Organization.objects.count(),
                "learners": Learner.objects.count(), "instructors": Instructor.objects.count(),
                "trainings": Training.objects.count(), "exams": Attempt.objects.filter(is_exam=True).exclude(status="in_progress").count(),
                "certificates": Certificate.objects.filter(status="valid").count(), "revenue": revenue,
                "subscriptions_active": Subscription.objects.filter(status="active", end_date__gte=today).count(),
                "subscriptions_expiring": Subscription.objects.filter(status="active", end_date__gte=today,
                                                                      end_date__lte=today + timedelta(days=30)).count(),
                "payments_pending": Payment.objects.filter(status="pending").count(),
                "activity": [{"user": a.user_label, "action": a.action, "model": a.model, "at": a.created_at}
                             for a in AuditLog.objects.all()[:10]],
                "monthly_revenue": _monthly(Payment.objects.filter(status="confirmed"), "paid_at", "amount")}
    if role in SCHOOL_ROLES:
        data = kpis(user, params)
        late = scoped(Installment.objects.filter(paid_amount__lt=F("amount"), due_date__lt=today), user, school="invoice__school").count()
        lessons = scoped(Lesson.objects.filter(start__date=today), user).count()
        return {"scope": "school", **data, "late_installments": late, "lessons_today": lessons,
                "learners_by_status": {r["status"]: r["c"] for r in scoped(Learner.objects.all(), user, learner="user")
                                       .values("status").annotate(c=Count("id"))},
                "monthly_revenue": _monthly(scoped(Payment.objects.filter(status="confirmed"), user), "paid_at", "amount"),
                "vehicles_alerts": scoped(Vehicle.objects.filter(
                    Q(insurance_expiry__lte=today + timedelta(days=30)) | Q(technical_visit_expiry__lte=today + timedelta(days=30))),
                    user).count()}
    if role in ORG_ROLES:
        learners = scoped(Learner.objects.all(), user, org="organization")
        att = scoped(Attempt.objects.exclude(status="in_progress"), user, org="learner__organization")
        exam = att.filter(is_exam=True)
        inv = scoped(Invoice.objects.filter(kind="invoice").exclude(status__in=["cancelled", "draft"]), user, org="organization")
        lessons = scoped(Lesson.objects.all(), user, org="learner__organization")
        done, absent = lessons.filter(status="done").count(), lessons.filter(status="absent").count()
        return {"scope": "organization", "beneficiaries": learners.count(),
                "cohorts": scoped(Cohort.objects.all(), user, org="organization").count(),
                "contracts_active": scoped(Contract.objects.filter(status="active"), user, org="organization").count(),
                "invoiced": _num(inv.aggregate(s=Sum("total"))["s"]), "paid": _num(inv.aggregate(s=Sum("paid"))["s"]),
                "avg_quiz_score": round(float(att.filter(is_exam=False).aggregate(a=Avg("percent"))["a"] or 0), 1),
                "exam_pass_rate": round(exam.filter(passed=True).count() * 100 / exam.count(), 1) if exam.count() else 0,
                "certificates": scoped(Certificate.objects.filter(status="valid"), user, org="learner__organization").count(),
                "attendance_rate": round(done * 100 / (done + absent), 1) if done + absent else None,
                "by_status": {r["status"]: r["c"] for r in learners.values("status").annotate(c=Count("id"))}}
    if role == INSTRUCTOR:
        ins = Instructor.objects.filter(user=user).first()
        lessons = Lesson.objects.filter(instructor=ins) if ins else Lesson.objects.none()
        month = lessons.filter(status="done", start__year=today.year, start__month=today.month)
        return {"scope": "instructor", "lessons_today": lessons.filter(start__date=today).count(),
                "upcoming": [{"id": l.id, "start": l.start, "learner": l.learner.full_name if l.learner else None, "kind": l.kind}
                             for l in lessons.filter(start__gte=timezone.now(), status="planned").select_related("learner")[:5]],
                "learners": Learner.objects.filter(lessons__instructor=ins).distinct().count() if ins else 0,
                "hours_this_month": round(sum(l.duration_hours for l in month), 1)}
    learner = Learner.objects.filter(user=user).first()
    if not learner:
        return {"scope": "learner"}
    from apps.pedagogy.services import learner_progress
    from apps.practice.services import driving_log
    inv = Invoice.objects.filter(learner=learner, kind="invoice").exclude(status__in=["cancelled", "draft"])
    nxt = Installment.objects.filter(invoice__in=inv, paid_amount__lt=F("amount")).order_by("due_date").first()
    return {"scope": "learner", "learner": learner.full_name, "status": learner.status, "progress": {
        k: v for k, v in learner_progress(learner).items() if k not in ("history", "themes")},
        "driving": {k: v for k, v in driving_log(learner).items() if k in ("planned_hours", "done_hours", "remaining_hours", "progress_percent")},
        "balance": _num(inv.aggregate(t=Sum("total"))["t"]) - _num(inv.aggregate(p=Sum("paid"))["p"]),
        "next_installment": {"amount": nxt.balance, "due_date": nxt.due_date} if nxt else None,
        "next_lesson": next(({"start": l.start, "kind": l.kind} for l in Lesson.objects.filter(
            learner=learner, start__gte=timezone.now(), status="planned").order_by("start")[:1]), None),
        "certificates": Certificate.objects.filter(learner=learner, status="valid").count()}


def _monthly(qs, field, amount):
    since = timezone.now() - timedelta(days=365)
    rows = (qs.filter(**{field + "__gte": since}).annotate(m=TruncMonth(field, tzinfo=dt_timezone.utc)).values("m").annotate(t=Sum(amount)).order_by("m"))
    return [{"month": f"{r['m']:%Y-%m}", "amount": r["t"]} for r in rows]


# --------------------------------------------------------------------------- exports
def _learner_rows(user, params):
    qs = _school_filter(scoped(Learner.objects.select_related("training", "cohort", "organization"), user, org="organization",
                               learner="user"), user, params)
    qs = _period(qs, "registered_at", params)
    return (["Matricule", "Nom", "Prénom", "Téléphone", "E-mail", "Catégorie", "Formation", "Cohorte", "Organisation", "Statut", "Inscription"],
            [[l.matricule, l.last_name, l.first_name, l.phone, l.email, l.category, l.training.name if l.training else "",
              l.cohort.name if l.cohort else "", l.organization.name if l.organization else "", l.get_status_display(),
              l.registered_at] for l in qs])


def _payment_rows(user, params):
    qs = scoped(Payment.objects.filter(status="confirmed").select_related("invoice__learner", "invoice__organization"), user,
                org="invoice__organization", learner="invoice__learner__user")
    qs = _period(_school_filter(qs, user, params), "paid_at__date", params)
    return (["Reçu", "Facture", "Client", "Mode", "Montant (FCFA)", "Date"],
            [[p.receipt_number, p.invoice.number,
              p.invoice.learner.full_name if p.invoice.learner else (p.invoice.organization.name if p.invoice.organization else ""),
              p.get_method_display(), int(p.amount), p.paid_at.strftime("%d/%m/%Y %H:%M") if p.paid_at else ""] for p in qs])


def _unpaid_rows(user, params):
    qs = scoped(Invoice.objects.filter(kind="invoice").exclude(status__in=["paid", "cancelled", "draft"]).select_related("learner", "organization"),
                user, org="organization", learner="learner__user")
    qs = _school_filter(qs, user, params)
    return (["Facture", "Client", "Total", "Payé", "Reste", "Échéance"],
            [[i.number, i.learner.full_name if i.learner else (i.organization.name if i.organization else ""), int(i.total),
              int(i.paid), int(i.balance), i.due_date] for i in qs])


def _training_rows(user, params):
    qs = _school_filter(scoped(Training.objects.annotate(n=Count("learners")), user, org="school__organizations"), user, params)
    return (["Formation", "Permis", "Heures théorie", "Heures pratique", "Tarif", "Inscrits"],
            [[t.name, t.category, t.theory_hours, t.practical_hours, int(t.price), t.n] for t in qs])


def _attempt_rows(exam):
    def fn(user, params):
        qs = scoped(Attempt.objects.filter(is_exam=exam).exclude(status="in_progress").select_related("learner", "quiz"), user,
                    org="learner__organization", learner="learner__user")
        qs = _period(_school_filter(qs, user, params), "started_at__date", params)
        return (["Apprenant", "Matricule", "Test", "Tentative", "Bonnes", "Mauvaises", "Score %", "Résultat", "Date"],
                [[a.learner.full_name, a.learner.matricule, a.quiz.title, a.number, a.correct_count, a.wrong_count,
                  float(a.percent), a.result_label, a.finished_at.strftime("%d/%m/%Y %H:%M") if a.finished_at else ""] for a in qs])
    return fn


def _certificate_rows(user, params):
    qs = scoped(Certificate.objects.select_related("learner"), user, org="learner__organization", learner="learner__user")
    qs = _school_filter(qs, user, params)
    return (["N°", "Titulaire", "Formation", "Permis", "Score", "Taux %", "Date", "Statut"],
            [[c.number, c.learner.full_name, c.training_name, c.category, c.score, float(c.percent), c.issued_at,
              c.get_status_display()] for c in qs])


def _progress_rows(user, params):
    from apps.pedagogy.services import learner_progress
    qs = _school_filter(scoped(Learner.objects.select_related("school"), user, org="organization", learner="user"), user, params)
    rows = []
    for l in qs[:500]:
        p = learner_progress(l)
        rows.append([l.matricule, l.full_name, p["progress_percent"], p["quizzes_done"], p["average_percent"], p["success_rate"]])
    return (["Matricule", "Apprenant", "Progression %", "QCM réalisés", "Score moyen %", "Taux de réussite %"], rows)


def _expense_rows(user, params):
    qs = _period(_school_filter(scoped(Expense.objects.all(), user), user, params), "date", params)
    return (["Date", "Catégorie", "Description", "Montant"], [[e.date, e.get_category_display(), e.description, int(e.amount)] for e in qs])


def _kpi_rows(user, params):
    return (["Indicateur", "Valeur"], [[k, float(v) if isinstance(v, Decimal) else v] for k, v in kpis(user, params).items()])


def _profit_rows(user, params):
    d = profitability(user, params)
    return (["Élément", "Recettes", "Dépenses", "Résultat"], [[r["label"], int(r["revenue"]), int(r["expenses"]), int(r["net"])] for r in d["rows"]])


MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MONTHLY_HEADERS = ["Mois", "Factures émises (FCFA)", "Encaissements (FCFA)", "Paiements (nb)", "Dépenses (FCFA)", "Résultat net (FCFA)"]


def monthly_finance(user, params):
    """Situation financière mois par mois : facturé, encaissé, dépensé, résultat. Total en dernière ligne.

    Filtres : date_from / date_to (défaut : 12 derniers mois), school (admin Akwaba). Agrégation faite en Python (pas de dépendance
    aux tables de fuseaux MySQL)."""
    today = timezone.localdate()
    df = params.get("date_from") or (today.replace(day=1) - timedelta(days=335)).replace(day=1).isoformat()
    dt = params.get("date_to") or today.isoformat()
    p = {"date_from": df, "date_to": dt, "school": params.get("school")}
    inv = _school_filter(_period(scoped(Invoice.objects.filter(kind="invoice").exclude(status__in=["cancelled", "draft"]), user), "issue_date", p), user, p)
    pay = _school_filter(scoped(Payment.objects.filter(status="confirmed"), user), user, p)
    exp = _school_filter(_period(scoped(Expense.objects.all(), user), "date", p), user, p)
    billed, cashed, n_pay, spent = defaultdict(Decimal), defaultdict(Decimal), defaultdict(int), defaultdict(Decimal)
    for d, t in inv.values_list("issue_date", "total"):
        if d:
            billed[(d.year, d.month)] += t
    for at, created, a in pay.values_list("paid_at", "created_at", "amount"):
        at = at or created                      # paiement confirmé sans date de règlement : date de création
        if at:
            k = timezone.localtime(at)
            if not (df <= k.date().isoformat() <= dt):
                continue
            cashed[(k.year, k.month)] += a
            n_pay[(k.year, k.month)] += 1
    for d, a in exp.values_list("date", "amount"):
        spent[(d.year, d.month)] += a
    keys = sorted(set(billed) | set(cashed) | set(spent))
    rows = [[f"{MONTHS_FR[m - 1].capitalize()} {y}", int(billed[(y, m)]), int(cashed[(y, m)]), n_pay[(y, m)], int(spent[(y, m)]),
             int(cashed[(y, m)] - spent[(y, m)])] for y, m in keys]
    total = ["TOTAL", sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows), sum(r[4] for r in rows), sum(r[5] for r in rows)]
    return MONTHLY_HEADERS, rows + [total]


def _monthly_finance_rows(user, params):
    return monthly_finance(user, params)


REPORTS = {
    "monthly_finance": ("Situation financière par mois", _monthly_finance_rows, "reports"),
    "learners": ("Inscriptions / bénéficiaires", _learner_rows, "learners"),
    "payments": ("Paiements", _payment_rows, "payments"),
    "unpaid": ("Impayés", _unpaid_rows, "invoices"),
    "trainings": ("Formations", _training_rows, "trainings"),
    "exams": ("Examens", _attempt_rows(True), "attempts"),
    "quiz_results": ("Résultats QCM", _attempt_rows(False), "attempts"),
    "certificates": ("Certificats", _certificate_rows, "certificates"),
    "progress": ("Progression", _progress_rows, "learners"),
    "expenses": ("Dépenses", _expense_rows, "expenses"),
    "kpis": ("Indicateurs clés", _kpi_rows, "reports"),
    "profitability": ("Rentabilité", _profit_rows, "reports"),
}
