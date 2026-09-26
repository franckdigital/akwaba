import hashlib
import hmac
import json
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Invoice, Payment
from apps.core.models import Notification
from apps.exams.models import Certificate
from apps.learners.models import Learner
from apps.pedagogy.models import Attempt, Choice, Question, Quiz
from apps.practice.models import Instructor, Vehicle
from apps.schools.models import School, Training


def make_school(name):
    return School.objects.create(legal_name=name)


def make_user(email, role, school=None, **kw):
    return User.objects.create_user(email, "Passw0rd!x", role=role, school=school, first_name="T", last_name=role, **kw)


def make_question(school, code, correct=True, qtype="single"):
    q = Question.objects.create(school=school, code=code, category="B", theme="code", qtype=qtype, text=f"Question {code} ?",
                                explanation=f"Explication {code}")
    Choice.objects.create(question=q, label="A", text="Bonne", is_correct=True, order=0)
    Choice.objects.create(question=q, label="B", text="Mauvaise", is_correct=False, order=1)
    return q


class Base(TestCase):
    def setUp(self):
        self.school = make_school("École A")
        self.other = make_school("École B")
        self.training = Training.objects.create(school=self.school, category="B", name="Permis B", price=200000)
        self.director = make_user("dir@a.ci", "director", self.school)
        self.secretary = make_user("sec@a.ci", "secretary", self.school)
        self.lu = make_user("l@a.ci", "learner", self.school)
        self.learner = Learner.objects.create(user=self.lu, school=self.school, training=self.training, first_name="Awa",
                                              last_name="K", category="B", status="in_training")
        self.client = APIClient()

    def as_user(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class ScoringAndCertificateTests(Base):
    def _practice(self, percent):
        quiz = Quiz.objects.create(school=self.school, title="Entraînement", category="B", mode="manual")
        return Attempt.objects.create(quiz=quiz, learner=self.learner, school=self.school, status="finished", percent=percent, is_exam=False)

    def _exam_quiz(self):
        exam = Quiz.objects.create(school=self.school, title="Examen", category="B", mode="manual", is_exam=True, shuffle=False)
        exam.questions.set([make_question(self.school, "E1")])
        return exam

    def test_exam_locked_until_average_reached(self):
        exam = self._exam_quiz()
        c = self.as_user(self.lu)
        self.assertEqual(c.post(f"/api/exams/{exam.id}/start/").status_code, 403)          # aucun QCM terminé
        self._practice(50)
        r = c.post(f"/api/exams/{exam.id}/start/")
        self.assertEqual(r.status_code, 403)
        self.assertIn("verrouillés", r.json()["detail"])
        e = c.get("/api/quiz-attempts/progress/").json()["exam_eligibility"]
        self.assertEqual((e["eligible"], e["average"], e["required"]), (False, 50.0, 60))
        self._practice(70)                                                                   # moyenne 60 %
        self.assertEqual(c.post(f"/api/exams/{exam.id}/start/").status_code, 201)

    def test_monthly_finance_report_exports(self):
        c = self.as_user(self.director)
        j = c.get("/api/reports/monthly-finance/").json()
        self.assertEqual(j["rows"][-1][0], "TOTAL")
        x = c.get("/api/reports/export/?report=monthly_finance&format=xlsx")
        self.assertEqual((x.status_code, x.content[:2]), (200, b"PK"))
        d = c.get("/api/reports/export/?report=monthly_finance&format=pdf")
        self.assertEqual((d.status_code, d.content[:4]), (200, b"%PDF"))

    def _run_exam(self, n_questions, n_correct):
        self._practice(90)
        qs = [make_question(self.school, f"S{i}") for i in range(n_questions)]
        exam = Quiz.objects.create(school=self.school, training=self.training, title="Examen", category="B", mode="manual",
                                   is_exam=True, pass_threshold=70, duration_minutes=60, shuffle=False, max_attempts=3)
        exam.questions.set(qs)
        c = self.as_user(self.lu)
        r = c.post(f"/api/exams/{exam.id}/start/")
        self.assertEqual(r.status_code, 201, r.content)
        att = r.json()
        self.assertNotIn("is_correct", json.dumps(att["questions"]))  # aucune fuite de la bonne réponse
        for i, q in enumerate(att["questions"]):
            good = i < n_correct
            choice = next(ch["id"] for ch in q["choices"] if (ch["label"] == "A") == good)
            r = c.post(f"/api/quiz-attempts/{att['id']}/answer/", {"question": q["id"], "choices": [choice]}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        r = c.post(f"/api/quiz-attempts/{att['id']}/finish/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_35_of_50_is_admitted_and_certified(self):
        res = self._run_exam(50, 35)
        self.assertEqual(res["result"], "ADMIS")
        self.assertEqual(float(res["percent"]), 70.0)
        cert = Certificate.objects.get(learner=self.learner)
        self.assertTrue(cert.number.startswith("AKW-CERT-"))
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.status, "passed")
        # vérification publique par QR (jeton)
        pub = APIClient().get(f"/api/certificates/verify/{cert.verification_token}/")
        self.assertEqual(pub.status_code, 200)
        self.assertTrue(pub.json()["authentic"])
        self.assertEqual(pub.json()["number"], cert.number)
        # PDF
        pdf = self.as_user(self.lu).get(f"/api/certificates/{cert.id}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_34_of_50_is_not_admitted_and_no_certificate(self):
        res = self._run_exam(50, 34)
        self.assertEqual(res["result"], "NON ADMIS")
        self.assertEqual(float(res["percent"]), 68.0)
        self.assertFalse(Certificate.objects.exists())

    def test_correction_shown_for_wrong_and_right_answer(self):
        qs = [make_question(self.school, f"C{i}") for i in range(2)]
        quiz = Quiz.objects.create(school=self.school, title="QCM", category="B", mode="manual", shuffle=False)
        quiz.questions.set(qs)
        c = self.as_user(self.lu)
        att = c.post(f"/api/quizzes/{quiz.id}/start/").json()
        q1, q2 = att["questions"]
        wrong = next(ch["id"] for ch in q1["choices"] if ch["label"] == "B")
        r = c.post(f"/api/quiz-attempts/{att['id']}/answer/", {"question": q1["id"], "choices": [wrong]}, format="json").json()
        self.assertFalse(r["is_correct"])
        self.assertEqual(r["your_answer"], ["B"])
        self.assertEqual(r["correct_answer"], ["A"])
        self.assertIn("Explication", r["explanation"])
        good = next(ch["id"] for ch in q2["choices"] if ch["label"] == "A")
        r = c.post(f"/api/quiz-attempts/{att['id']}/answer/", {"question": q2["id"], "choices": [good]}, format="json").json()
        self.assertTrue(r["is_correct"])
        self.assertIn("Explication", r["explanation"])
        # double validation refusée
        r = c.post(f"/api/quiz-attempts/{att['id']}/answer/", {"question": q2["id"], "choices": [good]}, format="json")
        self.assertEqual(r.status_code, 400)
        done = c.post(f"/api/quiz-attempts/{att['id']}/finish/").json()
        self.assertEqual(done["score_label"], "1/2")
        self.assertEqual(float(done["percent"]), 50.0)
        self.assertEqual([row["result"] for row in done["review"]], ["incorrect", "correct"])

    def test_multiple_choice_requires_exact_set(self):
        q = Question.objects.create(school=self.school, code="M1", category="B", theme="code", qtype="multi", text="?")
        ids = [Choice.objects.create(question=q, label=l, text=l, is_correct=c, order=i).id
               for i, (l, c) in enumerate([("A", True), ("B", True), ("C", False)])]
        quiz = Quiz.objects.create(school=self.school, title="M", category="B", mode="manual")
        quiz.questions.set([q])
        c = self.as_user(self.lu)
        att = c.post(f"/api/quizzes/{quiz.id}/start/").json()
        r = c.post(f"/api/quiz-attempts/{att['id']}/answer/", {"question": q.id, "choices": [ids[0]]}, format="json").json()
        self.assertFalse(r["is_correct"])  # réponse partielle = incorrecte

    def test_max_attempts_enforced(self):
        q = make_question(self.school, "X1")
        quiz = Quiz.objects.create(school=self.school, title="T", category="B", mode="manual", max_attempts=1)
        quiz.questions.set([q])
        c = self.as_user(self.lu)
        a = c.post(f"/api/quizzes/{quiz.id}/start/").json()
        c.post(f"/api/quiz-attempts/{a['id']}/finish/")
        self.assertEqual(c.post(f"/api/quizzes/{quiz.id}/start/").status_code, 400)


class ImportTests(Base):
    def _xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.append(["Code", "Permis", "Thème", "Type", "Question", "A", "B", "C", "D", "Bonne réponse", "Explication"])
        for r in rows:
            ws.append(r)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "qcm.xlsx"
        return buf

    def test_import_report_duplicates_and_errors(self):
        make_question(self.school, "EXIST")
        rows = [
            ["N1", "B", "Signalisation", "Réponse unique", "Q1 ?", "a", "b", "", "", "B", "expl"],
            ["N2", "B", "Priorités", "Vrai/Faux", "Q2 ?", "", "", "", "", "Vrai", "expl"],
            ["N3", "B", "Sécurité routière", "Choix multiple", "Q3 ?", "a", "b", "c", "d", "A,C", "expl"],
            ["EXIST", "B", "Code de la route", "Réponse unique", "Doublon de code", "a", "b", "", "", "A", ""],
            ["N5", "Z", "Code de la route", "Réponse unique", "Permis invalide", "a", "b", "", "", "A", ""],
            ["N6", "B", "Code de la route", "Réponse unique", "Réponse hors options", "a", "b", "", "", "D", ""],
            ["N1", "B", "Signalisation", "Réponse unique", "Doublon dans le fichier", "a", "b", "", "", "A", ""],
        ]
        c = self.as_user(self.director)
        prev = c.post("/api/questions/import/", {"file": self._xlsx(rows)}, format="multipart").json()
        self.assertEqual((prev["total"], prev["valid"], prev["error_count"], prev["duplicates"]), (7, 3, 4, 2))
        self.assertEqual(Question.objects.filter(school=self.school).count(), 1)  # aperçu : rien n'est écrit
        done = c.post("/api/questions/import/", {"file": self._xlsx(rows), "dry_run": "false"}, format="multipart").json()
        self.assertEqual(done["imported"], 3)
        self.assertEqual(Question.objects.filter(school=self.school).count(), 4)
        multi = Question.objects.get(school=self.school, code="N3")
        self.assertEqual(sorted(multi.choices.filter(is_correct=True).values_list("label", flat=True)), ["A", "C"])
        err = c.get(f"/api/question-imports/{done['id']}/errors/")
        self.assertEqual(err.status_code, 200)
        self.assertEqual(c.get("/api/questions/import-template/").status_code, 200)

    def test_missing_columns_rejected(self):
        wb = Workbook()
        wb.active.append(["Foo", "Bar"])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "x.xlsx"
        r = self.as_user(self.director).post("/api/questions/import/", {"file": buf}, format="multipart")
        self.assertEqual(r.status_code, 400)


class PaymentTests(Base):
    def _invoice(self, total=100000):
        return Invoice.objects.create(school=self.school, learner=self.learner, total=total, title="Formation")

    def test_mobile_money_only_confirmed_by_signed_webhook(self):
        inv = self._invoice()
        c = self.as_user(self.lu)
        r = c.post("/api/payments/", {"invoice": inv.id, "method": "orange_money", "amount": 40000, "payer_phone": "0700"},
                   format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "pending")
        inv.refresh_from_db()
        self.assertEqual(inv.paid, 0)
        ref = r.json()["provider_ref"]
        body = json.dumps({"provider_ref": ref, "status": "success", "amount": "40000"}).encode()
        anon = APIClient()
        bad = anon.post("/api/payments/webhook/", body, content_type="application/json", HTTP_X_SIGNATURE="deadbeef")
        self.assertEqual(bad.status_code, 401)
        inv.refresh_from_db()
        self.assertEqual(inv.paid, 0)
        sig = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        ok = anon.post("/api/payments/webhook/", body, content_type="application/json", HTTP_X_SIGNATURE=sig)
        self.assertEqual(ok.status_code, 200, ok.content)
        inv.refresh_from_db()
        self.assertEqual((inv.paid, inv.status), (40000, "partial"))
        pay = Payment.objects.get()
        self.assertTrue(pay.receipt_number)
        # idempotence : rejeu du webhook
        anon.post("/api/payments/webhook/", body, content_type="application/json", HTTP_X_SIGNATURE=sig)
        inv.refresh_from_db()
        self.assertEqual(inv.paid, 40000)
        self.assertEqual(c.get(f"/api/payments/{pay.id}/receipt/").status_code, 200)

    def test_webhook_amount_mismatch_rejected(self):
        inv = self._invoice()
        r = self.as_user(self.lu).post("/api/payments/", {"invoice": inv.id, "method": "wave", "amount": 50000}, format="json")
        body = json.dumps({"provider_ref": r.json()["provider_ref"], "status": "success", "amount": "1"}).encode()
        sig = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        res = APIClient().post("/api/payments/webhook/", body, content_type="application/json", HTTP_X_SIGNATURE=sig)
        self.assertEqual(res.status_code, 422)
        self.assertEqual(Payment.objects.get().status, "pending")

    def test_installments_allocation_and_overpayment(self):
        inv = self._invoice(300000)
        c = self.as_user(self.secretary)
        r = c.post(f"/api/invoices/{inv.id}/installments/", {"count": 6, "first_due_date": str(timezone.localdate())}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual([int(i["amount"]) for i in r.json()], [50000] * 6)
        p = c.post("/api/payments/", {"invoice": inv.id, "method": "cash", "amount": 75000}, format="json")
        self.assertEqual(p.status_code, 201, p.content)
        self.assertEqual(p.json()["status"], "confirmed")  # espèces : encaissées par le caissier
        got = c.get(f"/api/invoices/{inv.id}/").json()
        self.assertEqual([int(i["paid_amount"]) for i in got["installments"]], [50000, 25000, 0, 0, 0, 0])
        self.assertEqual(got["installments"][1]["status"], "partial" if got["installments"][1]["due_date"] > str(timezone.localdate()) else "late")
        over = c.post("/api/payments/", {"invoice": inv.id, "method": "cash", "amount": 999999}, format="json")
        self.assertEqual(over.status_code, 400)

    def test_learner_cannot_pay_cash_or_other_invoice(self):
        inv = self._invoice()
        c = self.as_user(self.lu)
        self.assertEqual(c.post("/api/payments/", {"invoice": inv.id, "method": "cash", "amount": 1000}, format="json").status_code, 403)
        other = Learner.objects.create(school=self.school, first_name="B", last_name="B", category="B")
        inv2 = Invoice.objects.create(school=self.school, learner=other, total=1000)
        self.assertEqual(c.post("/api/payments/", {"invoice": inv2.id, "method": "wave", "amount": 1000}, format="json").status_code, 403)


class SecurityTests(Base):
    def test_tenant_isolation(self):
        other_dir = make_user("dir@b.ci", "director", self.other)
        Learner.objects.create(school=self.other, first_name="X", last_name="Y", category="B")
        ids = [l["id"] for l in self.as_user(self.director).get("/api/learners/").json()["results"]]
        self.assertEqual(set(ids), {self.learner.id})
        other_ids = [l["school"] for l in self.as_user(other_dir).get("/api/learners/").json()["results"]]
        self.assertEqual(set(other_ids), {self.other.id})
        self.assertEqual(self.as_user(other_dir).get(f"/api/learners/{self.learner.id}/").status_code, 404)

    def test_learner_cannot_access_question_bank_or_users(self):
        c = self.as_user(self.lu)
        self.assertEqual(c.get("/api/questions/").status_code, 403)
        self.assertEqual(c.post("/api/learners/", {"first_name": "a", "last_name": "b"}, format="json").status_code, 403)
        self.assertEqual(c.get("/api/audit-logs/").status_code, 403)

    def test_learner_only_sees_own_data(self):
        Learner.objects.create(school=self.school, first_name="Autre", last_name="Apprenant", category="B")
        rows = self.as_user(self.lu).get("/api/learners/").json()["results"]
        self.assertEqual([r["id"] for r in rows], [self.learner.id])

    def test_login_lockout_and_audit(self):
        c = APIClient()
        for _ in range(settings.MAX_LOGIN_ATTEMPTS):
            self.assertEqual(c.post("/api/auth/login/", {"email": "dir@a.ci", "password": "bad"}, format="json").status_code, 401)
        r = c.post("/api/auth/login/", {"email": "dir@a.ci", "password": "Passw0rd!x"}, format="json")
        self.assertEqual(r.status_code, 429)

    def test_login_success_returns_tokens_and_permissions(self):
        r = APIClient().post("/api/auth/login/", {"email": "dir@a.ci", "password": "Passw0rd!x"}, format="json").json()
        self.assertIn("access", r)
        self.assertIn("refresh", r)
        self.assertIn("create", r["permissions"]["learners"])
        me = APIClient()
        me.credentials(HTTP_AUTHORIZATION="Bearer " + r["access"])
        self.assertEqual(me.get("/api/auth/me/").status_code, 200)
        self.assertEqual(APIClient().get("/api/learners/").status_code, 401)

    def test_audit_log_records_changes(self):
        c = self.as_user(self.secretary)
        r = c.patch(f"/api/learners/{self.learner.id}/", {"phone": "0707070707"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        from apps.core.models import AuditLog
        log = AuditLog.objects.filter(action="update", model="learners.Learner").first()
        self.assertEqual(log.new_value["phone"], "0707070707")
        self.assertEqual(log.old_value["phone"], "")

    def test_sensitive_id_number_encrypted_at_rest(self):
        self.learner.id_document_no = "CI0012345678"
        self.learner.save()
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT id_document_no FROM learners_learner WHERE id=%s", [self.learner.id])
            raw = cur.fetchone()[0]
        self.assertTrue(raw.startswith("enc::"))
        self.assertNotIn("CI0012345678", raw)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.id_document_no, "CI0012345678")


class PlanningTests(Base):
    def test_double_booking_rejected(self):
        ins = Instructor.objects.create(school=self.school, first_name="I", last_name="K")
        veh = Vehicle.objects.create(school=self.school, plate="AA-1")
        c = self.as_user(self.secretary)
        start = timezone.now() + timedelta(days=1)
        payload = {"kind": "practical", "learner": self.learner.id, "instructor": ins.id, "vehicle": veh.id,
                   "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}
        self.assertEqual(c.post("/api/lessons/", payload, format="json").status_code, 201)
        clash = dict(payload, start=(start + timedelta(minutes=30)).isoformat(), end=(start + timedelta(hours=2)).isoformat())
        r = c.post("/api/lessons/", clash, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("conflicts", r.json())
        adjacent = dict(payload, start=(start + timedelta(hours=1)).isoformat(), end=(start + timedelta(hours=2)).isoformat())
        self.assertEqual(c.post("/api/lessons/", adjacent, format="json").status_code, 201)


class SaasLimitTests(Base):
    def test_plan_limit_blocks_extra_learners(self):
        from apps.schools.models import Plan, Subscription
        plan = Plan.objects.create(name="Mini", max_learners=1)
        Subscription.objects.create(school=self.school, plan=plan, start_date=timezone.localdate() - timedelta(days=1),
                                    end_date=timezone.localdate() + timedelta(days=30))
        r = self.as_user(self.secretary).post("/api/learners/", {"first_name": "N", "last_name": "N", "category": "B"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Limite", json.dumps(r.json()))


class OrgContractTests(Base):
    def test_contract_split_and_invoices(self):
        from apps.organizations.models import Cohort, Contract, Organization
        org = Organization.objects.create(school=self.school, name="ABC")
        contract = Contract.objects.create(school=self.school, organization=org, training=self.training, beneficiaries_count=2,
                                           unit_price=250000, organization_contribution=150000, installments_count=4, status="active")
        self.assertEqual(int(contract.learner_contribution), 100000)
        cohort = Cohort.objects.create(school=self.school, organization=org, contract=contract, training=self.training, name="C1")
        for n in "12":
            Learner.objects.create(school=self.school, organization=org, cohort=cohort, training=self.training, first_name=n,
                                   last_name="E", category="B")
        r = self.as_user(self.director).post(f"/api/contracts/{contract.id}/generate-invoices/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["learner_invoices"], 2)
        org_inv = Invoice.objects.get(organization=org)
        self.assertEqual(int(org_inv.total), 300000)
        learner_inv = Invoice.objects.filter(learner__organization=org).first()
        self.assertEqual([int(i.amount) for i in learner_inv.installments.all()], [25000] * 4)
        # l'organisation ne voit que sa propre facture, pas celles des apprenants
        hr = make_user("hr@abc.ci", "org_admin", self.school, organization=org)
        rows = self.as_user(hr).get("/api/invoices/").json()["results"]
        self.assertEqual([r["id"] for r in rows], [org_inv.id])
        # relancer ne duplique pas
        again = self.as_user(self.director).post(f"/api/contracts/{contract.id}/generate-invoices/", {}, format="json").json()
        self.assertEqual(again["learner_invoices"], 0)


class QcmAdminTests(Base):
    def _xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.append(["Code", "Permis", "Thème", "Type", "Question", "A", "B", "C", "D", "Bonne réponse", "Explication"])
        for r in rows:
            ws.append(r)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "qcm.xlsx"
        return buf

    ROWS = [["Z1", "B", "Signalisation", "Réponse unique", "Question Z1 ?", "a", "b", "", "", "A", "e1"],
            ["Z2", "B", "Priorités", "Vrai/Faux", "Question Z2 ?", "", "", "", "", "Faux", "e2"]]

    def test_import_into_new_and_existing_quiz(self):
        c = self.as_user(self.director)
        r = c.post("/api/questions/import/", {"file": self._xlsx(self.ROWS), "dry_run": "false", "new_quiz_title": "Série 1"}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        quiz = Quiz.objects.get(title="Série 1")
        self.assertEqual((quiz.mode, quiz.questions.count(), quiz.num_questions), ("manual", 2, 2))
        # ré-import dans un questionnaire existant : les doublons de code rejoignent quand même le questionnaire
        q2 = Quiz.objects.create(school=self.school, title="Série 2", category="B")
        r = c.post("/api/questions/import/", {"file": self._xlsx(self.ROWS), "dry_run": "false", "quiz": q2.id}, format="multipart").json()
        self.assertEqual((r["imported"], r["duplicates"]), (0, 2))
        self.assertEqual(Quiz.objects.get(pk=q2.id).questions.count(), 2)
        self.assertEqual(Question.objects.filter(school=self.school).count(), 2)

    def _png(self, color="red"):
        from PIL import Image
        b = BytesIO()
        Image.new("RGB", (12, 12), color).save(b, "PNG")
        return b.getvalue()

    def _xlsx_img(self, rows, embed_row=None):
        from openpyxl.drawing.image import Image as XlImage
        wb = Workbook()
        ws = wb.active
        ws.title = "QCM"
        ws.append(["Code", "Permis", "Thème", "Type", "Question", "A", "B", "C", "D", "Bonne réponse", "Explication", "Sous-thème", "Difficulté", "Image"])
        for r in rows:
            ws.append(r)
        if embed_row:
            img = XlImage(BytesIO(self._png("blue")))
            ws.add_image(img, f"N{embed_row}")
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "qcm.xlsx"
        return buf

    def test_import_with_referenced_and_embedded_images(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        c = self.as_user(self.director)
        rows = [["I1", "B", "Signalisation", "Réponse unique", "Panneau stop ?", "a", "b", "", "", "A", "", "", "", "stop.png"],
                ["I2", "B", "Signalisation", "Réponse unique", "Panneau embarqué ?", "a", "b", "", "", "B", "", "", "", ""],
                ["I3", "B", "Signalisation", "Réponse unique", "Image absente ?", "a", "b", "", "", "B", "", "", "", "manque.png"]]
        img = SimpleUploadedFile("stop.png", self._png(), content_type="image/png")
        r = c.post("/api/questions/import/", {"file": self._xlsx_img(rows, embed_row=3), "images": [img], "dry_run": "false"}, format="multipart").json()
        self.assertEqual((r["imported"], r["error_count"]), (2, 1), r)
        self.assertIn("manque.png", r["errors"][0]["message"])
        self.assertTrue(Question.objects.get(school=self.school, code="I1").image)
        self.assertTrue(Question.objects.get(school=self.school, code="I2").image)
        self.assertFalse(Question.objects.filter(school=self.school, code="I3").exists())

    def test_invalid_image_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        rows = [["I1", "B", "Signalisation", "Réponse unique", "Q ?", "a", "b", "", "", "A", "", "", "", "x.png"]]
        bad = SimpleUploadedFile("x.png", b"pas une image", content_type="image/png")
        r = self.as_user(self.director).post("/api/questions/import/", {"file": self._xlsx_img(rows), "images": [bad], "dry_run": "false"}, format="multipart").json()
        self.assertEqual((r["imported"], r["error_count"]), (0, 1))

    def test_create_question_via_api_then_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        c = self.as_user(self.director)
        body = {"code": "API1", "category": "B", "theme": "signs", "qtype": "single", "text": "Panneau ?", "difficulty": "easy", "explanation": "",
                "choices": [{"label": "A", "text": "x", "is_correct": True, "order": 0}, {"label": "B", "text": "y", "is_correct": False, "order": 1}]}
        r = c.post("/api/questions/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        qid = r.json()["id"]
        self.assertEqual(c.post("/api/questions/", body, format="json").status_code, 400)  # code déjà pris
        img = SimpleUploadedFile("p.png", self._png(), content_type="image/png")
        r = c.post(f"/api/questions/{qid}/image/", {"image": img}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["image"])
        self.assertEqual(c.delete(f"/api/questions/{qid}/image/").status_code, 200)
        Question.objects.get(pk=qid).image.delete(save=False)

    def test_quiz_of_other_school_rejected(self):
        other_quiz = Quiz.objects.create(school=self.other, title="Autre", category="B")
        r = self.as_user(self.director).post("/api/questions/import/", {"file": self._xlsx(self.ROWS), "quiz": other_quiz.id}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_update_existing_by_code(self):
        c = self.as_user(self.director)
        c.post("/api/questions/import/", {"file": self._xlsx(self.ROWS), "dry_run": "false"}, format="multipart")
        rows = [["Z1", "B", "Signalisation", "Réponse unique", "Énoncé modifié ?", "x", "y", "", "", "B", "nouvelle explication"]]
        r = c.post("/api/questions/import/", {"file": self._xlsx(rows), "dry_run": "false", "update_existing": "true"}, format="multipart").json()
        self.assertEqual((r["imported"], r["updated"], r["error_count"]), (0, 1, 0))
        q = Question.objects.get(school=self.school, code="Z1")
        self.assertEqual((q.text, q.explanation), ("Énoncé modifié ?", "nouvelle explication"))
        self.assertEqual([c.label for c in q.choices.filter(is_correct=True)], ["B"])

    def test_export_roundtrip_and_bulk_actions(self):
        c = self.as_user(self.director)
        c.post("/api/questions/import/", {"file": self._xlsx(self.ROWS), "dry_run": "false"}, format="multipart")
        exp = c.get("/api/questions/export/")
        self.assertEqual(exp.status_code, 200)
        buf = BytesIO(exp.content)
        buf.name = "e.xlsx"
        prev = c.post("/api/questions/import/", {"file": buf, "update_existing": "true"}, format="multipart").json()
        self.assertEqual((prev["total"], prev["valid"], prev["error_count"]), (2, 2, 0))  # le fichier exporté est ré-importable
        ids = list(Question.objects.filter(school=self.school).values_list("id", flat=True))
        self.assertEqual(c.post("/api/questions/bulk/", {"action": "deactivate", "ids": ids}, format="json").json()["count"], 2)
        self.assertFalse(Question.objects.filter(school=self.school, is_active=True).exists())
        self.assertEqual(c.post("/api/questions/bulk/", {"action": "duplicate", "ids": ids[:1]}, format="json").json()["count"], 1)
        self.assertEqual(Question.objects.filter(school=self.school).count(), 3)
        self.assertEqual(c.post("/api/questions/bulk/", {"action": "delete", "ids": ids}, format="json").json()["count"], 2)
        self.assertEqual(Question.objects.filter(school=self.school).count(), 1)

    def test_secretary_cannot_bulk_delete_and_central_bank_protected(self):
        q = Question.objects.create(school=None, code="CENT1", category="B", theme="code", text="?")
        r = self.as_user(self.director).post("/api/questions/bulk/", {"action": "delete", "ids": [q.id]}, format="json").json()
        self.assertEqual(r["count"], 0)
        self.assertTrue(Question.objects.filter(pk=q.id).exists())
        self.assertEqual(self.as_user(self.secretary).post("/api/questions/bulk/", {"action": "delete", "ids": [q.id]}, format="json").status_code, 403)

    def test_compose_duplicate_stats_and_answers_hidden_from_learners(self):
        qs = [make_question(self.school, f"K{i}") for i in range(3)]
        quiz = Quiz.objects.create(school=self.school, title="Manuel", category="B", mode="random", shuffle=False)
        c = self.as_user(self.director)
        r = c.post(f"/api/quizzes/{quiz.id}/compose/", {"add": [q.id for q in qs]}, format="json").json()
        self.assertEqual(r["question_count"], 3)
        c.post(f"/api/quizzes/{quiz.id}/compose/", {"remove": [qs[0].id]}, format="json")
        self.assertEqual(c.get(f"/api/quizzes/{quiz.id}/questions/").json()["count"], 2)
        dup = c.post(f"/api/quizzes/{quiz.id}/duplicate/").json()
        self.assertEqual(Quiz.objects.get(pk=dup["id"]).questions.count(), 2)
        self.assertEqual(c.get(f"/api/quizzes/{quiz.id}/stats/").json()["attempts"], 0)
        learner = self.as_user(self.lu)
        self.assertEqual(learner.get(f"/api/quizzes/{quiz.id}/questions/").status_code, 403)  # les bonnes réponses ne fuient pas
        self.assertEqual(learner.post(f"/api/quizzes/{quiz.id}/compose/", {"add": [qs[0].id]}, format="json").status_code, 403)

    def test_analytics_and_attempt_reset(self):
        q = make_question(self.school, "AN1")
        quiz = Quiz.objects.create(school=self.school, title="T", category="B", mode="manual")
        quiz.questions.set([q])
        lc = self.as_user(self.lu)
        att = lc.post(f"/api/quizzes/{quiz.id}/start/").json()
        good = next(ch["id"] for ch in att["questions"][0]["choices"] if ch["label"] == "A")
        lc.post(f"/api/quiz-attempts/{att['id']}/answer/", {"question": q.id, "choices": [good]}, format="json")
        lc.post(f"/api/quiz-attempts/{att['id']}/finish/")
        c = self.as_user(self.director)
        a = c.get("/api/questions/analytics/").json()
        self.assertEqual((a["total"], a["never_answered"]), (1, 0))
        self.assertEqual(c.get(f"/api/questions/{q.id}/stats/").json()["success_rate"], 100.0)
        rows = c.get("/api/quiz-attempts/?search=Awa").json()["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.as_user(self.secretary).post(f"/api/quiz-attempts/{att['id']}/reset/").status_code, 403)
        self.assertEqual(c.post(f"/api/quiz-attempts/{att['id']}/reset/").status_code, 204)
        self.assertEqual(Attempt.objects.count(), 0)
        self.assertEqual(lc.post(f"/api/quizzes/{quiz.id}/start/").status_code, 201)  # l'apprenant peut recommencer

    def test_central_bank_code_is_duplicate_but_joins_quiz(self):
        central = Question.objects.create(school=None, code="Z1", category="B", theme="code", text="Question centrale ?")
        Choice.objects.create(question=central, label="A", text="x", is_correct=True, order=0)
        Choice.objects.create(question=central, label="B", text="y", is_correct=False, order=1)
        c = self.as_user(self.director)
        r = c.post("/api/questions/import/", {"file": self._xlsx(self.ROWS), "dry_run": "false", "new_quiz_title": "Mix", "update_existing": "true"},
                   format="multipart").json()
        self.assertEqual((r["imported"], r["duplicates"]), (1, 1))  # Z2 créée ; Z1 refusée car code central (jamais écrasé)
        central.refresh_from_db()
        self.assertEqual(central.text, "Question centrale ?")
        self.assertIn(central.id, list(Quiz.objects.get(title="Mix").questions.values_list("id", flat=True)))


    def test_template_is_valid_and_reimportable(self):
        c = self.as_user(self.director)
        for url, expected in (("/api/questions/import-template/", 6), ("/api/questions/import-template/?blank=1", 0)):
            r = c.get(url)
            self.assertEqual(r.status_code, 200)
            buf = BytesIO(r.content)
            buf.name = "t.xlsx"
            from openpyxl import load_workbook
            self.assertEqual(load_workbook(BytesIO(r.content)).sheetnames, ["QCM", "Valeurs autorisées", "Mode d'emploi"])
            if expected:
                rep = c.post("/api/questions/import/", {"file": buf}, format="multipart").json()
                self.assertEqual((rep["total"], rep["valid"], rep["error_count"]), (expected, expected, 0))  # les exemples sont tous valides


from unittest import mock

from django.test import override_settings

from apps.organizations.models import Cohort, Organization
from apps.schools.models import Plan
from apps.subscriptions.models import LearnerSubscription, OrganizationSubscription, SubscriptionOrder


@override_settings(DEBUG=True, CINETPAY_MOCK=True)
class SubscriptionTests(Base):
    def setUp(self):
        super().setUp()
        self.school.subscription_required = True
        self.school.save()
        self.quiz = Quiz.objects.create(school=self.school, title="QCM", category="B", mode="manual", is_published=True)
        self.quiz.questions.set([make_question(self.school, "SUB1")])
        self.ip = Plan.objects.create(audience="individual", school=self.school, name="Mensuel", price=5000, billing_cycle="monthly")
        self.op = Plan.objects.create(audience="organization", school=None, name="Équipe", price=90000, billing_cycle="quarterly",
                                      max_cohorts=1, included_beneficiaries=2, extra_beneficiary_price=4000)
        self.org = Organization.objects.create(school=self.school, name="ABC")
        self.orgadmin = make_user("oa@abc.ci", "org_admin", self.school, organization=self.org)
        self.cohort = Cohort.objects.create(school=self.school, organization=self.org, training=self.training, name="C1")
        self.cohort2 = Cohort.objects.create(school=self.school, organization=self.org, training=self.training, name="C2")

    def _buy(self, client, plan, **extra):
        return client.post("/api/subscription-orders/", {"plan": plan.id, "method": "cinetpay", "phone": "0707070707", **extra}, format="json")

    def test_access_blocked_then_granted_after_confirmed_payment(self):
        lc = self.as_user(self.lu)
        r = lc.post(f"/api/quizzes/{self.quiz.id}/start/")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Abonnement requis", r.json()["detail"])
        res = self._buy(lc, self.ip)
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertIn("/checkout/cinetpay-mock", body["redirect_url"])
        self.assertEqual(body["order"]["status"], "pending")
        # le retour navigateur ne suffit pas : sans confirmation du fournisseur, rien n'est activé
        self.assertEqual(lc.post(f"/api/subscription-orders/{body['order']['id']}/verify/").json()["status"], "pending")
        self.assertEqual(lc.post(f"/api/quizzes/{self.quiz.id}/start/").status_code, 403)
        ok = lc.post(f"/api/subscription-orders/{body['order']['id']}/mock-confirm/", {"success": True}, format="json").json()
        self.assertEqual(ok["status"], "paid")
        sub = LearnerSubscription.objects.get(learner=self.learner)
        self.assertTrue(sub.is_current)
        self.assertEqual((sub.end_date - sub.start_date).days, 30)
        inv = Invoice.objects.get(learner=self.learner)
        self.assertEqual((inv.status, int(inv.paid)), ("paid", 5000))   # la recette apparaît dans la facturation de l'auto-école
        self.assertEqual(lc.post(f"/api/quizzes/{self.quiz.id}/start/").status_code, 201)

    def test_renewal_stacks_after_current_period(self):
        lc = self.as_user(self.lu)
        for _ in range(2):
            oid = self._buy(lc, self.ip).json()["order"]["id"]
            lc.post(f"/api/subscription-orders/{oid}/mock-confirm/", {"success": True}, format="json")
        first, second = LearnerSubscription.objects.order_by("start_date")
        self.assertEqual(second.start_date, first.end_date + timedelta(days=1))

    def test_failed_payment_does_not_activate(self):
        lc = self.as_user(self.lu)
        oid = self._buy(lc, self.ip).json()["order"]["id"]
        r = lc.post(f"/api/subscription-orders/{oid}/mock-confirm/", {"success": False}, format="json").json()
        self.assertEqual(r["status"], "failed")
        self.assertFalse(LearnerSubscription.objects.exists())

    @override_settings(CINETPAY_MOCK=False, CINETPAY_API_KEY="sk_live_dummy", CINETPAY_API_PASSWORD="x")
    def test_live_key_refused_and_no_orphan_order(self):
        r = self._buy(self.as_user(self.lu), self.ip)
        self.assertEqual(r.status_code, 400)
        self.assertIn("LIVE", json.dumps(r.json()))
        self.assertFalse(SubscriptionOrder.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_finalize_reverifies_with_provider_and_webhook_is_not_trusted(self):
        lc = self.as_user(self.lu)
        order = SubscriptionOrder.objects.get(pk=self._buy(lc, self.ip).json()["order"]["id"])
        anon = APIClient()
        hook = lambda ref: anon.post("/api/subscriptions/cinetpay-webhook/", {"merchant_transaction_id": ref}, format="json")
        with mock.patch("apps.subscriptions.providers.verify_payment", return_value=("pending", {})):
            self.assertEqual(hook(order.provider_ref).json()["result"], "pending")
        self.assertEqual(hook("nope").status_code, 404)
        self.assertFalse(LearnerSubscription.objects.exists())
        with mock.patch("apps.subscriptions.providers.verify_payment", return_value=("succeeded", {"status": "SUCCESS"})):
            self.assertEqual(hook(order.provider_ref).json()["result"], "paid")
            hook(order.provider_ref)  # rejeu
        self.assertEqual(LearnerSubscription.objects.count(), 1)

    def test_organization_plan_takes_cohorts_and_seats_into_account(self):
        for i in range(3):
            Learner.objects.create(school=self.school, organization=self.org, cohort=self.cohort, training=self.training,
                                   first_name=f"E{i}", last_name="X", category="B")
        oc = self.as_user(self.orgadmin)
        # aucune cohorte / trop de cohortes / pas assez de places : refus explicites
        self.assertEqual(self._buy(oc, self.op).status_code, 400)
        self.assertEqual(self._buy(oc, self.op, cohorts=[self.cohort.id, self.cohort2.id]).status_code, 400)
        r = self._buy(oc, self.op, cohorts=[self.cohort.id])          # 3 bénéficiaires pour 2 places incluses
        self.assertEqual(r.status_code, 400)
        self.assertIn("place", json.dumps(r.json()))
        r = self._buy(oc, self.op, cohorts=[self.cohort.id], extra_seats=2)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(int(r.json()["order"]["amount"]), 90000 + 2 * 4000)
        oid = r.json()["order"]["id"]
        oc.post(f"/api/subscription-orders/{oid}/mock-confirm/", {"success": True}, format="json")
        sub = OrganizationSubscription.objects.get()
        self.assertEqual((sub.seats, list(sub.cohorts.values_list("id", flat=True))), (4, [self.cohort.id]))
        self.assertEqual(Invoice.objects.get(organization=self.org).status, "paid")   # facture adressée à l'organisation
        # les bénéficiaires de la cohorte couverte accèdent aux QCM sans abonnement individuel
        member = Learner.objects.filter(cohort=self.cohort).first()
        member.user = make_user("m@abc.ci", "learner", self.school)
        member.save()
        self.assertEqual(self.as_user(member.user).post(f"/api/quizzes/{self.quiz.id}/start/").status_code, 201)
        # 4 places : la 4e bénéficiaire est acceptée, la 5e refusée
        sec = self.as_user(self.secretary)
        payload = {"first_name": "N", "last_name": "N", "category": "B", "cohort": self.cohort.id}
        self.assertEqual(sec.post("/api/learners/", payload, format="json").status_code, 201)
        self.assertEqual(sec.post("/api/learners/", payload, format="json").status_code, 400)
        # changement de cohortes couvertes : plafond du plan (1 cohorte)
        self.assertEqual(oc.post(f"/api/organization-subscriptions/{sub.id}/cohorts/", {"cohorts": [self.cohort.id, self.cohort2.id]}, format="json").status_code, 400)

    def test_role_and_scope_rules_on_plans(self):
        lc, oc, dc = self.as_user(self.lu), self.as_user(self.orgadmin), self.as_user(self.director)
        self.assertEqual(self._buy(lc, self.op, cohorts=[self.cohort.id]).status_code, 403)     # un apprenant n'achète pas un plan d'organisation
        self.assertEqual(self._buy(oc, self.ip).status_code, 403)                                # ni l'inverse
        self.assertEqual([p["name"] for p in lc.get("/api/plans/").json()["results"]], ["Mensuel"])
        self.assertEqual([p["name"] for p in oc.get("/api/plans/").json()["results"]], ["Équipe"])
        r = dc.post("/api/plans/", {"audience": "individual", "name": "Sur mesure", "price": 1000, "billing_cycle": "monthly"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["school"], self.school.id)
        self.assertEqual(dc.patch(f"/api/plans/{self.op.id}/", {"price": 1}, format="json").status_code, 403)   # plan global Akwaba
        self.assertEqual(dc.post("/api/plans/", {"audience": "school", "name": "X", "price": 1}, format="json").status_code, 400)
        other_dir = self.as_user(make_user("d2@b.ci", "director", self.other))
        self.assertNotIn("Mensuel", [p["name"] for p in other_dir.get("/api/plans/").json()["results"]])

    def test_manual_cash_by_staff_and_free_grant(self):
        sc = self.as_user(self.secretary)
        r = sc.post("/api/subscription-orders/", {"plan": self.ip.id, "method": "cash", "learner": self.learner.id}, format="json")
        self.assertEqual(r.status_code, 400)                             # preuve de paiement obligatoire
        proof = SimpleUploadedFile("recu.png", b"PNGDATA", content_type="image/png")
        r = sc.post("/api/subscription-orders/", {"plan": self.ip.id, "method": "cash", "learner": self.learner.id, "proof": proof}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["order"]["status"], "paid")
        self.assertTrue(LearnerSubscription.objects.get(learner=self.learner).is_current)
        self.assertEqual(self.as_user(self.lu).post("/api/subscription-orders/", {"plan": self.ip.id, "method": "cash"}, format="json").status_code, 403)
        LearnerSubscription.objects.all().delete()
        self.assertEqual(sc.post("/api/subscription-orders/grant/", {"plan": self.ip.id, "learner": self.learner.id}, format="json").status_code, 403)
        self.assertEqual(self.as_user(self.director).post("/api/subscription-orders/grant/", {"plan": self.ip.id, "learner": self.learner.id}, format="json").status_code, 201)

    def test_school_saas_plan_and_my_subscription_and_expiry(self):
        from apps.schools.models import Subscription
        from apps.subscriptions.services import expire_subscriptions
        saas = Plan.objects.create(audience="school", school=None, name="Pro", price=50000, billing_cycle="monthly", max_learners=10)
        dc = self.as_user(self.director)
        oid = self._buy(dc, saas).json()["order"]["id"]
        self.assertFalse(Invoice.objects.exists())                       # l'abonnement SaaS ne pollue pas la facturation de l'auto-école
        dc.post(f"/api/subscription-orders/{oid}/mock-confirm/", {"success": True}, format="json")
        self.assertEqual(Subscription.objects.get(school=self.school).plan_id, saas.id)
        me = dc.get("/api/subscriptions/me/").json()
        self.assertEqual((me["audience"], me["current"]["plan_name"]), ("school", "Pro"))
        lm = self.as_user(self.lu).get("/api/subscriptions/me/").json()
        self.assertEqual((lm["audience"], lm["required"], lm["current"]), ("individual", True, None))
        Subscription.objects.update(end_date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(expire_subscriptions(), 1)


from django.core.files.uploadedfile import SimpleUploadedFile


@override_settings(DEBUG=True, CINETPAY_MOCK=True)
class SubscriptionAdvancedTests(Base):
    def setUp(self):
        super().setUp()
        self.school.subscription_required = True
        self.school.save()
        self.quiz = Quiz.objects.create(school=self.school, title="QCM", category="B", mode="manual", is_published=True)
        self.quiz.questions.set([make_question(self.school, "ADV1")])
        self.org = Organization.objects.create(school=self.school, name="ABC")
        self.org2 = Organization.objects.create(school=self.school, name="XYZ")
        self.cohort = Cohort.objects.create(school=self.school, organization=self.org, training=self.training, name="Cohorte B")
        self.cohort2 = Cohort.objects.create(school=self.school, organization=self.org, training=self.training, name="Cohorte C")
        self.orgadmin = make_user("oa@abc.ci", "org_admin", self.school, organization=self.org)
        self.accountant = make_user("acc@a.ci", "accountant", self.school)
        self.op = Plan.objects.create(audience="organization", school=None, name="Équipe", price=90000, billing_cycle="quarterly",
                                      max_cohorts=2, included_beneficiaries=10, extra_beneficiary_price=1000)

    def _pdf(self):
        return SimpleUploadedFile("recu.pdf", b"%PDF-1.4 test", content_type="application/pdf")

    def _cash_org(self, client, plan=None, **extra):
        return client.post("/api/subscription-orders/", {"plan": (plan or self.op).id, "method": "cash", "organization": self.org.id,
                                                       "cohorts": [self.cohort.id], "proof": self._pdf(), "proof_reference": "REC-001", **extra},
                           format="multipart")

    def _member(self, email="m@abc.ci"):
        u = make_user(email, "learner", self.school, organization=self.org)
        Learner.objects.create(user=u, school=self.school, organization=self.org, cohort=self.cohort, training=self.training,
                               first_name="M", last_name="M", category="B")
        return u

    # ---------------------------------------------------------------- preuve de paiement
    def test_cash_payment_requires_proof_and_proof_download_is_protected(self):
        sec = self.as_user(self.secretary)
        r = sec.post("/api/subscription-orders/", {"plan": self.op.id, "method": "cash", "organization": self.org.id, "cohorts": [self.cohort.id]},
                     format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("proof", r.json())
        self.assertFalse(SubscriptionOrder.objects.exists())
        bad = sec.post("/api/subscription-orders/", {"plan": self.op.id, "method": "cash", "organization": self.org.id, "cohorts": [self.cohort.id],
                                                     "proof": SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")}, format="multipart")
        self.assertEqual(bad.status_code, 400)
        ok = self._cash_org(sec)
        self.assertEqual(ok.status_code, 201, ok.content)
        order = SubscriptionOrder.objects.get()
        self.assertEqual((order.status, order.proof_reference), ("paid", "REC-001"))
        self.assertTrue(order.proof.name.startswith("payment_proofs/"))
        self.assertTrue(OrganizationSubscription.objects.get().is_current)
        self.assertEqual(Payment.objects.get().reference, "REC-001")     # référence reportée sur le paiement / reçu
        self.assertEqual(sec.get(f"/api/subscription-orders/{order.id}/proof/").status_code, 200)
        self.assertEqual(self.as_user(self._member()).get(f"/api/subscription-orders/{order.id}/proof/").status_code, 404)
        self.assertNotIn("proof", ok.json()["order"])                     # jamais d'URL publique du fichier
        self.assertTrue(ok.json()["order"]["has_proof"])
        # un bénéficiaire ne peut pas s'encaisser lui-même
        self.assertEqual(self.as_user(self.orgadmin).post("/api/subscription-orders/", {"plan": self.op.id, "method": "cash", "cohorts": [self.cohort.id],
                                                                                       "proof": self._pdf()}, format="multipart").status_code, 403)

    # ---------------------------------------------------------------- suspension pour défaut de paiement
    def test_suspend_and_reactivate_all_plans_of_an_organization(self):
        sec = self.as_user(self.secretary)
        self._cash_org(sec)
        self._cash_org(sec, plan=Plan.objects.create(audience="organization", name="Autre", price=1000, max_cohorts=1, included_beneficiaries=10),
                       )
        member = self._member()
        mc = self.as_user(member)
        self.assertEqual(mc.post(f"/api/quizzes/{self.quiz.id}/start/").status_code, 201)
        self.assertEqual(OrganizationSubscription.objects.filter(status="active").count(), 2)
        self.assertEqual(self.as_user(self.orgadmin).post("/api/organization-subscriptions/suspend-all/", {"organization": self.org.id}, format="json").status_code, 403)
        self.assertEqual(sec.post("/api/organization-subscriptions/suspend-all/", {"organization": self.org.id}, format="json").status_code, 403)
        r = self.as_user(self.accountant).post("/api/organization-subscriptions/suspend-all/", {"organization": self.org.id, "reason": "Facture impayée"}, format="json")
        self.assertEqual((r.status_code, r.json()["suspended"]), (200, 2))
        blocked = mc.post(f"/api/quizzes/{self.quiz.id}/start/")
        self.assertEqual(blocked.status_code, 403)
        self.assertIn("suspendu", blocked.json()["detail"])
        me = self.as_user(self.orgadmin).get("/api/subscriptions/me/").json()
        self.assertEqual((me["current"], len(me["suspended"]), me["suspended"][0]["reason"]), (None, 2, "Facture impayée"))
        cohorts = self.as_user(self.director).get(f"/api/cohorts/{self.cohort.id}/").json()
        self.assertEqual(cohorts["subscription"]["status"], "suspended")
        self.assertTrue(Notification.objects.filter(user=self.orgadmin, event="subscription_suspended").exists())
        r = self.as_user(self.director).post("/api/organization-subscriptions/reactivate-all/", {"organization": self.org.id}, format="json")
        self.assertEqual(r.json()["reactivated"], 2)
        self.assertEqual(mc.post(f"/api/quizzes/{self.quiz.id}/start/").status_code, 201)
        # une autre entreprise n'est pas touchée / inaccessible pour un autre directeur
        other_dir = self.as_user(make_user("d2@b.ci", "director", self.other))
        self.assertEqual(other_dir.post("/api/organization-subscriptions/suspend-all/", {"organization": self.org.id}, format="json").status_code, 400)

    # ---------------------------------------------------------------- plans réservés à une entreprise / cohorte + périodes de validité
    def test_dedicated_plans_sale_window_and_custom_validity(self):
        dc = self.as_user(self.director)
        r = dc.post("/api/plans/", {"audience": "organization", "name": "Négocié ABC", "price": 50000, "billing_cycle": "custom", "custom_days": 45,
                                    "organization": self.org.id, "cohort": self.cohort.id, "included_beneficiaries": 5}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        plan = Plan.objects.get(pk=r.json()["id"])
        self.assertEqual((plan.school_id, plan.duration_days), (self.school.id, 45))
        self.assertEqual(dc.post("/api/plans/", {"audience": "organization", "name": "X", "billing_cycle": "custom"}, format="json").status_code, 400)  # durée manquante
        self.assertEqual(dc.post("/api/plans/", {"audience": "individual", "name": "X", "organization": self.org.id}, format="json").status_code, 400)
        # visible / achetable uniquement par l'entreprise concernée, cohorte imposée
        other_org_admin = self.as_user(make_user("oa2@xyz.ci", "org_admin", self.school, organization=self.org2))
        self.assertNotIn("Négocié ABC", [p["name"] for p in other_org_admin.get("/api/plans/").json()["results"]])
        self.assertIn("Négocié ABC", [p["name"] for p in self.as_user(self.orgadmin).get("/api/plans/").json()["results"]])
        buy = other_org_admin.post("/api/subscription-orders/", {"plan": plan.id, "method": "cinetpay", "cohorts": [1]}, format="json")
        self.assertEqual(buy.status_code, 400)
        oc = self.as_user(self.orgadmin)
        res = oc.post("/api/subscription-orders/", {"plan": plan.id, "method": "cinetpay", "phone": "0707070707", "cohorts": [self.cohort2.id]}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(SubscriptionOrder.objects.get().cohort_ids, [self.cohort.id])   # la cohorte du plan est imposée
        oc.post(f"/api/subscription-orders/{res.json()['order']['id']}/mock-confirm/", {"success": True}, format="json")
        sub = OrganizationSubscription.objects.get()
        self.assertEqual((sub.end_date - sub.start_date).days, 45)
        me = oc.get("/api/subscriptions/me/").json()
        self.assertTrue(all("starts_on" in p and "ends_on" in p for p in me["plans"]))
        # fenêtre de vente dépassée : plus achetable, plus proposé
        plan.available_until = timezone.localdate() - timedelta(days=1)
        plan.save()
        self.assertNotIn("Négocié ABC", [p["name"] for p in oc.get("/api/subscriptions/me/").json()["plans"]])
        self.assertEqual(oc.post("/api/subscription-orders/", {"plan": plan.id, "method": "cinetpay"}, format="json").status_code, 400)

    # ---------------------------------------------------------------- URL de retour = origine réelle du front
    def test_return_url_uses_the_real_frontend_origin(self):
        lu_plan = Plan.objects.create(audience="individual", school=self.school, name="Mensuel", price=5000)
        lc = self.as_user(self.lu)
        r = lc.post("/api/subscription-orders/", {"plan": lu_plan.id, "method": "cinetpay", "origin": "http://localhost:5181"}, format="json")
        self.assertTrue(r.json()["redirect_url"].startswith("http://localhost:5181/checkout/cinetpay-mock"), r.json())
        evil = lc.post("/api/subscription-orders/", {"plan": lu_plan.id, "method": "cinetpay", "origin": "https://evil.example"}, format="json")
        self.assertTrue(evil.json()["redirect_url"].startswith(settings.PUBLIC_WEB_URL))

    # ---------------------------------------------------------------- rattachement dynamique utilisateur -> entreprise / cohorte
    def test_link_users_to_organization_and_cohort_dynamically(self):
        dc = self.as_user(self.director)
        r = dc.post("/api/users/", {"first_name": "Ali", "last_name": "B", "email": "ali@abc.ci", "role": "learner", "password": "Passw0rd!xx",
                                    "organization": self.org.id, "cohort": self.cohort.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual((body["organization_name"], body["cohort_name"]), ("ABC", "Cohorte B"))
        learner = Learner.objects.get(user__email="ali@abc.ci")
        self.assertEqual((learner.cohort_id, learner.organization_id, learner.training_id), (self.cohort.id, self.org.id, self.training.id))
        # changement de cohorte / d'entreprise à chaud
        r = dc.patch(f"/api/users/{body['id']}/", {"cohort": self.cohort2.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        learner.refresh_from_db()
        self.assertEqual(learner.cohort_id, self.cohort2.id)
        bad = dc.patch(f"/api/users/{body['id']}/", {"organization": self.org2.id, "cohort": self.cohort2.id}, format="json")
        self.assertEqual(bad.status_code, 400)                                       # cohorte d'une autre entreprise
        # rattachement en lot
        u2 = make_user("bob@a.ci", "learner", self.school)
        Learner.objects.create(user=u2, school=self.school, first_name="B", last_name="B", category="B")
        res = dc.post("/api/users/assign/", {"ids": [u2.id], "organization": self.org.id, "cohort": self.cohort.id}, format="json").json()
        self.assertEqual((res["assigned"], res["errors"]), (1, []))
        self.assertEqual(Learner.objects.get(user=u2).cohort_id, self.cohort.id)
        # l'admin d'entreprise ne peut pas rattacher à la cohorte d'une autre entreprise
        oth = Cohort.objects.create(school=self.school, organization=self.org2, training=self.training, name="Autre")
        self.assertEqual(self.as_user(self.orgadmin).post("/api/users/", {"first_name": "C", "last_name": "C", "email": "c@abc.ci", "role": "learner",
                                                                       "password": "Passw0rd!xx", "cohort": oth.id}, format="json").status_code, 403)
        # le nouveau bénéficiaire profite du plan souscrit pour sa cohorte
        self._cash_org(self.as_user(self.secretary))
        self.assertEqual(self.as_user(u2).post(f"/api/quizzes/{self.quiz.id}/start/").status_code, 201)

    # ---------------------------------------------------------------- import Excel des utilisateurs
    def _users_xlsx(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.append(["Prénom", "Nom", "E-mail", "Téléphone", "Rôle", "Mot de passe", "Organisation", "Cohorte", "Matricule employeur", "Permis"])
        for r in rows:
            ws.append(r)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        buf.name = "users.xlsx"
        return buf

    def test_users_excel_import_analysis_and_commit(self):
        rows = [
            ["Awa", "K", "awa@x.ci", "0707", "Apprenant", "", "ABC", "Cohorte B", "EMP-1", "B"],
            ["Yves", "K", "yves@x.ci", "", "Apprenant", "Secret#2026x", "ABC", "Cohorte B", "", ""],
            ["Fatou", "D", "fatou@x.ci", "", "RH", "", "ABC", "", "", ""],
            ["Dup", "D", "awa@x.ci", "", "Apprenant", "", "", "", "", ""],                       # doublon dans le fichier
            ["Inc", "I", "inc@x.ci", "", "Apprenant", "", "Inconnue", "", "", ""],               # organisation inconnue
            ["Coh", "C", "coh@x.ci", "", "Apprenant", "", "ABC", "Nope", "", ""],                # cohorte inconnue
            ["Mon", "M", "mon@x.ci", "", "Moniteur", "", "", "", "", ""],                        # rôle non importable
            ["Rh", "R", "rh2@x.ci", "", "RH", "", "", "", "", ""],                               # entreprise obligatoire
            ["Bad", "B", "not-an-email", "", "Apprenant", "", "", "", "", ""],
            ["Cohorte", "Wrong", "w@x.ci", "", "Apprenant", "", "XYZ", "Cohorte B", "", ""],     # cohorte d'une autre entreprise
        ]
        dc = self.as_user(self.director)
        prev = dc.post("/api/users/import/", {"file": self._users_xlsx(rows)}, format="multipart").json()
        self.assertEqual((prev["total"], prev["valid"], prev["error_count"], prev["created"]), (10, 3, 7, 0))
        self.assertFalse(User.objects.filter(email="awa@x.ci").exists())                           # analyse : rien d'écrit
        msgs = {e["email"]: e["message"] for e in prev["errors"]}
        self.assertIn("déjà utilisé", msgs["awa@x.ci"])
        self.assertIn("introuvable", msgs["inc@x.ci"])
        self.assertIn("non autorisé", msgs["mon@x.ci"])
        self.assertIn("Organisation obligatoire", msgs["rh2@x.ci"])
        done = dc.post("/api/users/import/", {"file": self._users_xlsx(rows), "dry_run": "false"}, format="multipart").json()
        self.assertEqual(done["created"], 3)
        creds = {c["email"]: c for c in done["credentials"]}
        self.assertTrue(creds["awa@x.ci"]["generated"] and len(creds["awa@x.ci"]["password"]) >= 8)
        self.assertFalse(creds["yves@x.ci"]["generated"])
        awa = Learner.objects.get(user__email="awa@x.ci")
        self.assertEqual((awa.cohort_id, awa.organization_id, awa.employee_ref), (self.cohort.id, self.org.id, "EMP-1"))
        self.assertEqual(User.objects.get(email="fatou@x.ci").organization_id, self.org.id)
        # les identifiants générés fonctionnent
        self.assertEqual(APIClient().post("/api/auth/login/", {"email": "awa@x.ci", "password": creds["awa@x.ci"]["password"]}, format="json").status_code, 200)
        self.assertEqual(self.as_user(self.secretary).post("/api/users/import/", {"file": self._users_xlsx(rows)}, format="multipart").status_code, 403)
        self.assertEqual(dc.get("/api/users/import-template/").status_code, 200)

    def test_users_import_respects_seats_of_covered_cohort_and_org_admin_scope(self):
        plan = Plan.objects.create(audience="organization", name="Mini", price=1000, max_cohorts=1, included_beneficiaries=1)
        sec = self.as_user(self.secretary)
        self._cash_org(sec, plan=plan)
        rows = [["A", "A", "a@x.ci", "", "Apprenant", "", "ABC", "Cohorte B", "", ""], ["B", "B", "b@x.ci", "", "Apprenant", "", "ABC", "Cohorte B", "", ""]]
        rep = self.as_user(self.director).post("/api/users/import/", {"file": self._users_xlsx(rows), "dry_run": "false"}, format="multipart").json()
        self.assertEqual((rep["created"], rep["error_count"]), (1, 1))
        self.assertIn("places", rep["errors"][0]["message"])
        # l'admin d'entreprise n'importe que pour SA structure
        oa_rows = [["N", "N", "n@x.ci", "", "Apprenant", "", "XYZ", "", "", ""]]
        rep = self.as_user(self.orgadmin).post("/api/users/import/", {"file": self._users_xlsx(oa_rows), "dry_run": "false"}, format="multipart").json()
        self.assertEqual(rep["created"], 1)
        self.assertEqual(User.objects.get(email="n@x.ci").organization_id, self.org.id)


class VoiceLoginTests(Base):
    def setUp(self):
        super().setUp()
        self.lu.phone = "+225 07 07 07 07 07"
        self.lu.save()

    def _enable(self, pin="4827", client=None):
        return (client or self.as_user(self.lu)).post("/api/auth/voice/enable/", {"pin": pin, "password": "Passw0rd!x"}, format="json")

    def test_enable_requires_password_valid_pin_and_phone(self):
        c = self.as_user(self.lu)
        self.assertEqual(c.post("/api/auth/voice/enable/", {"pin": "4827", "password": "mauvais"}, format="json").status_code, 400)
        for weak in ("1111", "1234", "9876", "12", "abcd", "0707"):        # identiques, suites, trop court, non numérique, fin du n° de téléphone
            self.assertEqual(self._enable(weak).status_code, 400, weak)
        self.assertEqual(self._enable("4827").status_code, 200)
        self.lu.refresh_from_db()
        self.assertTrue(self.lu.voice_enabled)
        self.assertNotIn("4827", self.lu.voice_pin_hash)                    # haché, jamais en clair
        self.assertNotIn("voice_pin_hash", json.dumps(c.get("/api/auth/me/").json()))
        self.assertEqual(c.get("/api/auth/voice/status/").json()["enabled"], True)
        nophone = make_user("np@a.ci", "learner", self.school)
        self.assertEqual(self._enable(client=self.as_user(nophone)).status_code, 400)
        self.assertEqual(self._enable(client=self.as_user(self.director)).status_code, 403)   # réservé apprenants / moniteurs

    def test_voice_login_success_and_formats(self):
        self._enable()
        anon = APIClient()
        for phone in ("0707070707", "+2250707070707", "07 07 07 07 07", "225 07 07 07 07 07"):
            r = anon.post("/api/auth/voice-login/", {"phone": phone, "pin": "4827"}, format="json")
            self.assertEqual(r.status_code, 200, (phone, r.content))
            self.assertIn("access", r.json())
            self.assertEqual(r.json()["user"]["email"], "l@a.ci")

    def test_voice_login_lockout_and_generic_errors(self):
        self._enable()
        anon = APIClient()
        self.assertEqual(anon.post("/api/auth/voice-login/", {"phone": "0101010101", "pin": "4827"}, format="json").status_code, 401)  # inconnu
        for _ in range(settings.MAX_LOGIN_ATTEMPTS):
            self.assertEqual(anon.post("/api/auth/voice-login/", {"phone": "0707070707", "pin": "9999"}, format="json").status_code, 401)
        r = anon.post("/api/auth/voice-login/", {"phone": "0707070707", "pin": "4827"}, format="json")
        self.assertEqual(r.status_code, 429)                                  # même avec le bon code : verrouillé

    def test_disabled_or_non_voice_account_cannot_voice_login(self):
        anon = APIClient()
        self.assertEqual(anon.post("/api/auth/voice-login/", {"phone": "0707070707", "pin": "4827"}, format="json").status_code, 401)
        self._enable()
        self.as_user(self.lu).post("/api/auth/voice/disable/")
        self.assertEqual(anon.post("/api/auth/voice-login/", {"phone": "0707070707", "pin": "4827"}, format="json").status_code, 401)

    def test_phone_number_cannot_be_shared_between_voice_accounts(self):
        self._enable()
        other = make_user("o@a.ci", "learner", self.school, phone="0707070707")
        r = self._enable("5938", client=self.as_user(other))
        self.assertEqual(r.status_code, 400)
        self.assertIn("compte vocal", r.json()["detail"])

    def test_password_login_by_phone(self):
        anon = APIClient()
        ok = anon.post("/api/auth/login/", {"identifier": "07 07 07 07 07", "password": "Passw0rd!x"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        make_user("dup@a.ci", "learner", self.school, phone="0707070707")
        amb = anon.post("/api/auth/login/", {"identifier": "0707070707", "password": "Passw0rd!x"}, format="json")
        self.assertEqual(amb.status_code, 400)                                # numéro partagé : e-mail exigé
        self.assertEqual(anon.post("/api/auth/login/", {"identifier": "l@a.ci", "password": "Passw0rd!x"}, format="json").status_code, 200)

    def test_server_side_transcription_optional(self):
        anon = APIClient()
        audio = SimpleUploadedFile("v.m4a", b"audio", content_type="audio/m4a")
        self.assertEqual(anon.post("/api/auth/voice/transcribe/", {"audio": audio}, format="multipart").status_code, 501)   # non configuré
        with override_settings(VOICE_STT_URL="https://stt.example/v1/audio/transcriptions", VOICE_STT_KEY="k"):
            fake = mock.Mock(ok=True)
            fake.json.return_value = {"text": "zéro sept zéro sept"}
            with mock.patch("requests.post", return_value=fake) as post:
                audio = SimpleUploadedFile("v.m4a", b"audio", content_type="audio/m4a")
                r = anon.post("/api/auth/voice/transcribe/", {"audio": audio}, format="multipart")
                self.assertEqual((r.status_code, r.json()["text"]), (200, "zéro sept zéro sept"))
                self.assertEqual(post.call_args.kwargs["data"]["language"], "fr")


class InstructorPlanningTests(Base):
    def setUp(self):
        super().setUp()
        self.iu = make_user("mon@a.ci", "instructor", self.school)
        self.ins = Instructor.objects.create(school=self.school, user=self.iu, first_name="Ismaël", last_name="K")
        self.other_ins = Instructor.objects.create(school=self.school, first_name="Autre", last_name="M")
        self.veh = Vehicle.objects.create(school=self.school, plate="1234 AB 01", brand="T", model="Y", category="B")
        self.t0 = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=2)

    def _body(self, **kw):
        b = {"kind": "practical", "learner": self.learner.id, "vehicle": self.veh.id, "start": self.t0.isoformat(),
             "end": (self.t0 + timedelta(hours=2)).isoformat(), "location": "Circuit", "status": "planned"}
        b.update(kw)
        return b

    def test_instructor_plans_own_lesson_and_conflicts_are_blocked(self):
        c = self.as_user(self.iu)
        r = c.post("/api/lessons/", self._body(instructor=self.other_ins.id), format="json")   # tentative d'usurpation : ignorée
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["instructor"], self.ins.id)
        self.assertEqual(r.json()["duration_hours"], 2.0)
        r2 = c.post("/api/lessons/", self._body(start=(self.t0 + timedelta(hours=1)).isoformat(), end=(self.t0 + timedelta(hours=3)).isoformat()), format="json")
        self.assertEqual(r2.status_code, 400)                                                     # chevauchement : moniteur/apprenant/véhicule
        self.assertIn("conflicts", r2.json())
        # déplacement puis annulation
        lid = r.json()["id"]
        moved = c.patch(f"/api/lessons/{lid}/", {"start": (self.t0 + timedelta(hours=4)).isoformat(), "end": (self.t0 + timedelta(hours=5)).isoformat()}, format="json")
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(c.patch(f"/api/lessons/{lid}/", {"status": "cancelled"}, format="json").status_code, 200)
        self.assertEqual(c.delete(f"/api/lessons/{lid}/").status_code, 403)                       # pas de suppression pour un moniteur

    def test_one_evaluation_per_lesson(self):
        c = self.as_user(self.iu)
        lid = c.post("/api/lessons/", self._body(), format="json").json()["id"]
        self.assertIsNone(c.get(f"/api/lessons/{lid}/").json()["evaluation"])
        ev = {"learner": self.learner.id, "lesson": lid, "date": "2026-09-20", "scores": {"braking": 7}, "comments": ""}
        r = c.post("/api/evaluations/", ev, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(c.get(f"/api/lessons/{lid}/").json()["evaluation"]["average"], 7.0)
        again = c.post("/api/evaluations/", ev, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertIn("déjà été évaluée", json.dumps(again.json(), ensure_ascii=False))
        # un moniteur ne peut pas évaluer hors séance
        self.assertEqual(c.post("/api/evaluations/", {**ev, "lesson": None}, format="json").status_code, 400)


class CourseTests(Base):
    def _pdf(self, name="c.pdf", size=1200):
        return SimpleUploadedFile(name, b"%PDF-1.4\n" + b"0" * size, content_type="application/pdf")

    def test_director_builds_multiformat_course_and_learner_follows_progress(self):
        d = self.as_user(self.director)
        r = d.post("/api/courses/", {"title": "Priorités", "theme": "priority", "kind": "theory", "summary": "Résumé", "duration_minutes": 20, "is_published": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cid = r.json()["id"]
        # PDF, texte, lien, vidéo en ligne, image, audio
        ok = [("pdf", {"file": self._pdf()}), ("text", {"text": "À retenir : cédez le passage."}), ("link", {"url": "https://exemple.ci/regles"}),
              ("embed", {"url": "https://www.youtube.com/watch?v=abc"}), ("audio", {"file": SimpleUploadedFile("a.mp3", b"ID3" + b"0" * 100, content_type="audio/mpeg")})]
        for i, (t, extra) in enumerate(ok):
            r = d.post("/api/course-materials/", {"course": cid, "material_type": t, "title": f"M{i}", "order": i, **extra}, format="multipart")
            self.assertEqual(r.status_code, 201, (t, r.content))
        pdf = d.get(f"/api/courses/{cid}/").json()["materials"][0]
        self.assertTrue(pdf["file_url"].endswith(".pdf") or ".pdf" in pdf["file_url"])
        self.assertGreater(pdf["file_size"], 0)
        # validations : mauvais format, contenu manquant
        bad = d.post("/api/course-materials/", {"course": cid, "material_type": "pdf", "title": "x", "file": SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")}, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(d.post("/api/course-materials/", {"course": cid, "material_type": "text", "title": "vide"}, format="multipart").status_code, 400)
        self.assertEqual(d.post("/api/course-materials/", {"course": cid, "material_type": "pdf", "title": "sans fichier"}, format="multipart").status_code, 400)
        # un contenu non publié est invisible de l'apprenant
        d.post("/api/course-materials/", {"course": cid, "material_type": "text", "title": "Brouillon", "text": "x", "is_published": "false"}, format="multipart")
        L = self.as_user(self.lu)
        det = L.get(f"/api/courses/{cid}/").json()
        self.assertEqual(len(det["materials"]), 5)
        self.assertEqual(det["progress"]["total"], 5)
        first = det["materials"][0]["id"]
        r = L.post(f"/api/course-materials/{first}/complete/").json()
        self.assertEqual((r["completed"], r["progress"]["done"], r["progress"]["percent"]), (True, 1, 20))
        self.assertEqual(L.get(f"/api/courses/{cid}/").json()["materials"][0]["completed"], True)
        self.assertEqual(L.delete(f"/api/course-materials/{first}/complete/").json()["progress"]["done"], 0)
        # un apprenant ne modifie rien
        self.assertEqual(L.post("/api/course-materials/", {"course": cid, "material_type": "text", "title": "x", "text": "y"}, format="multipart").status_code, 403)

    def test_central_courses_are_read_only_for_schools_and_drafts_hidden(self):
        from apps.pedagogy.models import Course
        central = Course.objects.create(school=None, title="Banque centrale", is_published=True)
        Course.objects.create(school=self.school, title="Brouillon", is_published=False)
        d = self.as_user(self.director)
        self.assertEqual(d.patch(f"/api/courses/{central.id}/", {"title": "hack"}, format="json").status_code, 403)
        self.assertEqual(d.post("/api/course-materials/", {"course": central.id, "material_type": "text", "title": "x", "text": "y"}, format="multipart").status_code, 400)
        titles = [c["title"] for c in self.as_user(self.lu).get("/api/courses/").json()["results"]]
        self.assertEqual(titles, ["Banque centrale"])
