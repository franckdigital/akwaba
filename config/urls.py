import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts import views as acc
from apps.admissions import views as admissions
from apps.billing import views as billing
from apps.core import views as core
from apps.exams import views as exams
from apps.learners import views as learners
from apps.organizations import views as orgs
from apps.pedagogy import views as ped
from apps.practice import views as practice
from apps.reports import views as reports
from apps.schools import views as schools
from apps.subscriptions import views as subs

router = DefaultRouter()
r = router.register
r("users", acc.UserViewSet, basename="user")
r("driving-schools", schools.SchoolViewSet, basename="school")
r("agencies", schools.AgencyViewSet, basename="agency")
r("trainings", schools.TrainingViewSet, basename="training")
r("plans", schools.PlanViewSet, basename="plan")
r("subscriptions", schools.SubscriptionViewSet, basename="subscription")
r("learners", learners.LearnerViewSet, basename="learner")
r("documents", learners.DocumentViewSet, basename="document")
r("courses", ped.CourseViewSet, basename="course")
r("course-materials", ped.MaterialViewSet, basename="course-material")
r("questions", ped.QuestionViewSet, basename="question")
r("question-imports", ped.ImportJobViewSet, basename="question-import")
r("quizzes", ped.QuizViewSet, basename="quiz")
r("quiz-attempts", ped.AttemptViewSet, basename="quiz-attempt")
r("instructors", practice.InstructorViewSet, basename="instructor")
r("vehicles", practice.VehicleViewSet, basename="vehicle")
r("maintenance", practice.MaintenanceViewSet, basename="maintenance")
r("fuel", practice.FuelViewSet, basename="fuel")
r("rooms", practice.RoomViewSet, basename="room")
r("lessons", practice.LessonViewSet, basename="lesson")
r("schedules", practice.LessonViewSet, basename="schedule")
r("evaluations", practice.EvaluationViewSet, basename="evaluation")
r("organizations", orgs.OrganizationViewSet, basename="organization")
r("contracts", orgs.ContractViewSet, basename="contract")
r("cohorts", orgs.CohortViewSet, basename="cohort")
r("groups", orgs.GroupViewSet, basename="group")
r("quote-requests", orgs.QuoteRequestViewSet, basename="quote-request")
r("individual-quotes", admissions.IndividualQuoteViewSet, basename="individual-quote")
r("recycling-items", admissions.RecyclingItemViewSet, basename="recycling-item")
r("recycling-reminder-settings", admissions.RecyclingReminderSettingsViewSet, basename="recycling-reminder-settings")
r("subscription-orders", subs.OrderViewSet, basename="subscription-order")
r("learner-subscriptions", subs.LearnerSubscriptionViewSet, basename="learner-subscription")
r("organization-subscriptions", subs.OrganizationSubscriptionViewSet, basename="organization-subscription")
r("invoices", billing.InvoiceViewSet, basename="invoice")
r("payments", billing.PaymentViewSet, basename="payment")
r("installments", billing.InstallmentViewSet, basename="installment")
r("expenses", billing.ExpenseViewSet, basename="expense")
r("exams", exams.ExamViewSet, basename="exam")
r("certificates", exams.CertificateViewSet, basename="certificate")
r("audit-logs", core.AuditLogViewSet, basename="audit-log")
r("notifications", core.NotificationViewSet, basename="notification")
r("alert-settings", core.AlertSettingViewSet, basename="alert-setting")

auth_patterns = [
    path("login/", acc.LoginView.as_view()),
    path("register/", acc.RegisterView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("logout/", acc.LogoutView.as_view()),
    path("me/", acc.MeView.as_view()),
    path("change-password/", acc.ChangePasswordView.as_view()),
    path("forgot-password/", acc.ForgotPasswordView.as_view()),
    path("reset-password/", acc.ResetPasswordView.as_view()),
    path("verify/request/", acc.RequestVerificationView.as_view()),
    path("verify/confirm/", acc.ConfirmVerificationView.as_view()),
    path("sessions/", acc.SessionsView.as_view()),
    path("voice/status/", acc.VoiceStatusView.as_view()),
    path("voice/enable/", acc.VoiceEnableView.as_view()),
    path("voice/disable/", acc.VoiceDisableView.as_view()),
    path("voice/transcribe/", acc.VoiceTranscribeView.as_view()),
    path("voice-login/", acc.VoiceLoginView.as_view()),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include(auth_patterns)),
    path("api/public/schools/", schools.public_schools),
    path("api/public/organizations/", orgs.public_organizations),
    path("api/public/quotes/", orgs.PublicQuoteView.as_view()),
    path("api/public/individual-quotes/", admissions.PublicIndividualQuoteView.as_view()),
    path("api/public/recycling-items/", admissions.public_recycling_items),
    path("api/certificates/verify/<str:code>/", exams.verify_certificate),
    path("api/payments/webhook/", billing.payment_webhook),
    path("api/subscriptions/me/", subs.MySubscriptionView.as_view()),
    path("api/subscriptions/cinetpay-webhook/", subs.CinetPayWebhookView.as_view()),
    path("api/reports/dashboard/", reports.DashboardView.as_view()),
    path("api/reports/kpis/", reports.KpiView.as_view()),
    path("api/reports/profitability/", reports.ProfitabilityView.as_view()),
    path("api/reports/export/", reports.ExportView.as_view()),
    path("api/reports/monthly-finance/", reports.MonthlyFinanceView.as_view()),
    path("api/reports/", reports.ReportListView.as_view()),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    # Médias publics uniquement (logos, images de questions, photos). Les documents restent protégés par /api/documents/<id>/download/.
    urlpatterns += [re_path(r"^media/(?P<path>(logos|questions|courses|learners/photos)/.*)$", serve,
                            {"document_root": settings.MEDIA_ROOT})]
